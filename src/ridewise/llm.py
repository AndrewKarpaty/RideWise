"""LLM access through LiteLLM, with JSON that survives provider differences."""

from __future__ import annotations

import json
import logging

import litellm
from pydantic import BaseModel, ValidationError

from ridewise.config import get_settings
from ridewise.observability import configure_observability

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The model could not be reached, or would not return usable output."""


def _completion_kwargs() -> dict:
    settings = get_settings()
    kwargs: dict = {"model": settings.llm_model, "max_tokens": settings.llm_max_tokens}
    # Claude Opus 5.5 and Sonnet 5.5 reject temperature/top_p with a 400, so the
    # setting stays None unless the user points RideWise at an older model.
    if settings.llm_temperature is not None:
        kwargs["temperature"] = settings.llm_temperature
    return kwargs


def chat(
    messages: list[dict[str, str]],
    *,
    metadata: dict | None = None,
    max_tokens: int | None = None,
) -> str:
    """One completion, returned as text."""
    configure_observability()
    kwargs = _completion_kwargs()
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if metadata:
        kwargs["metadata"] = metadata

    try:
        response = litellm.completion(messages=messages, **kwargs)
    except Exception as exc:
        raise LLMError(f"LLM call failed: {exc}") from exc

    choices = getattr(response, "choices", None)
    if not choices:
        raise LLMError("LLM returned no choices")
    content = choices[0].message.content
    if not content:
        raise LLMError("LLM returned empty content")
    return content.strip()


def extract_json(text: str) -> str:
    """Pull the JSON value out of a reply that may be fenced or prefaced.

    Models wrap JSON in ```json fences or a sentence of preamble often enough
    that parsing has to tolerate it.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:]  # drop the opening fence (with or without a language)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Scan every bracket that could open a JSON value and return the first
    # balanced span that actually parses. Position alone is not enough: prose
    # like "see [below] then {...}" opens with a bracket that is not JSON, and
    # a top-level array must not be mistaken for its first element.
    for start, char in enumerate(cleaned):
        if char not in "{[":
            continue
        closer = "}" if char == "{" else "]"
        span = _balanced_span(cleaned, start, char, closer)
        if span is None:
            continue
        try:
            json.loads(span)
        except ValueError:
            continue
        return span
    return cleaned


def _balanced_span(text: str, start: int, opener: str, closer: str) -> str | None:
    """The substring from `start` to its matching bracket, ignoring strings."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def chat_json[T: BaseModel](
    messages: list[dict[str, str]],
    schema: type[T],
    *,
    metadata: dict | None = None,
    attempts: int = 2,
) -> T:
    """A completion validated into `schema`.

    This asks for JSON in the prompt rather than using LiteLLM's
    `response_format`, because LiteLLM implements JSON schema for Anthropic by
    forcing a tool call - and `tool_choice: tool|any` is rejected with a 400 on
    Claude Opus 5.5 and Sonnet 5.5. Prompt-and-validate works on every provider
    LiteLLM can reach, which is the point of routing through it.
    """
    schema_text = json.dumps(schema.model_json_schema(), indent=2)
    instruction = (
        "Reply with a single JSON value and nothing else - no prose, no code "
        f"fences. It must validate against this JSON Schema:\n{schema_text}"
    )
    conversation = [*messages, {"role": "user", "content": instruction}]
    last_error: Exception | None = None

    for attempt in range(attempts):
        raw = chat(conversation, metadata=metadata)
        candidate = extract_json(raw)
        try:
            return schema.model_validate_json(candidate)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning("JSON attempt %d did not validate: %s", attempt + 1, exc)
            conversation = [
                *conversation,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"That did not validate against the schema: {exc}\n"
                        "Return corrected JSON only."
                    ),
                },
            ]

    raise LLMError(f"model never produced valid {schema.__name__}: {last_error}")
