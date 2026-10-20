"""The JSON extraction that lets any LiteLLM provider answer with a schema."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from ridewise.llm import LLMError, chat_json, extract_json


class _Shape(BaseModel):
    name: str
    size: int


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 2}\n```', {"a": 2}),
        ('```\n{"a": 3}\n```', {"a": 3}),
        ('Here you go:\n```json\n{"a": 4}\n```\nhope that helps', {"a": 4}),
        ('{"s": "a } brace in a string"}', {"s": "a } brace in a string"}),
        ('{"s": "an escaped \\" quote"}', {"s": 'an escaped " quote'}),
        ('[{"i": 1}, {"i": 2}]', [{"i": 1}, {"i": 2}]),
        ("Sure! [1, 2, 3]", [1, 2, 3]),
        # Prose brackets before the real payload must not fool the scanner.
        ('I think [a, b] is wrong, use {"right": true}', {"right": True}),
        ('{"nested": {"deep": [1, {"x": "}"}]}}', {"nested": {"deep": [1, {"x": "}"}]}}),
    ],
)
def test_extract_json_finds_the_payload(reply, expected):
    assert json.loads(extract_json(reply)) == expected


def test_extract_json_returns_input_when_there_is_no_json():
    assert extract_json("no json here at all") == "no json here at all"


def test_chat_json_validates_into_the_schema(monkeypatch):
    monkeypatch.setattr("ridewise.llm.chat", lambda *a, **k: 'Sure: {"name": "gloves", "size": 9}')
    result = chat_json([{"role": "user", "content": "hi"}], _Shape)
    assert result == _Shape(name="gloves", size=9)


def test_chat_json_retries_with_the_validation_error(monkeypatch):
    replies = iter(['{"name": "gloves"}', '{"name": "gloves", "size": 9}'])
    seen: list[int] = []

    def fake_chat(messages, **kwargs):
        seen.append(len(messages))
        return next(replies)

    monkeypatch.setattr("ridewise.llm.chat", fake_chat)
    result = chat_json([{"role": "user", "content": "hi"}], _Shape)

    assert result.size == 9
    # The retry must carry the failed attempt and the error back to the model.
    assert len(seen) == 2
    assert seen[1] > seen[0]


def test_chat_json_gives_up_with_a_clear_error(monkeypatch):
    monkeypatch.setattr("ridewise.llm.chat", lambda *a, **k: "not json")
    with pytest.raises(LLMError, match="_Shape"):
        chat_json([{"role": "user", "content": "hi"}], _Shape, attempts=2)


def test_no_sampling_params_are_sent_by_default():
    """Opus 5.5 and Sonnet 5.5 reject temperature with a 400, so it must be absent."""
    from ridewise.llm import _completion_kwargs

    assert "temperature" not in _completion_kwargs()
