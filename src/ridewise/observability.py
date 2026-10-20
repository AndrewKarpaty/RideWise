"""Langfuse tracing, wired so that a missing key degrades to a no-op.

Langfuse 5.x is OpenTelemetry-based, so LiteLLM's `langfuse_otel` callback is
the right one: its generation spans nest inside whatever `@observe` span is
active, giving one trace per ride plan with a child span per node and per LLM
call. The legacy `langfuse` callback targets the v2 SDK and would emit a
separate, parentless trace.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import litellm

logger = logging.getLogger(__name__)

REQUIRED_ENV = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def langfuse_configured() -> bool:
    return all(os.environ.get(name) for name in REQUIRED_ENV)


@lru_cache(maxsize=1)
def configure_observability() -> object | None:
    """Initialise tracing once per process. Returns the client, or None if off."""
    if not langfuse_configured():
        logger.info("Langfuse keys not set - running without tracing.")
        return None

    try:
        from langfuse import Langfuse

        client = Langfuse()
        litellm.success_callback = ["langfuse_otel"]
        litellm.failure_callback = ["langfuse_otel"]
        logger.info("Langfuse tracing enabled.")
        return client
    except Exception as exc:  # pragma: no cover - depends on network/credentials
        logger.warning("Langfuse setup failed, continuing untraced: %s", exc)
        return None


def flush() -> None:
    """Push buffered spans. Streamlit processes are long-lived, so call this at
    the end of a plan rather than relying on interpreter shutdown."""
    client = configure_observability()
    if client is not None:
        try:
            client.flush()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            logger.debug("Langfuse flush failed: %s", exc)


def trace_url() -> str | None:
    client = configure_observability()
    if client is None:
        return None
    try:
        return client.get_trace_url()  # type: ignore[attr-defined]
    except Exception:
        return None
