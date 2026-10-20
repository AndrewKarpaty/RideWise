"""Test isolation: a throwaway database, a fake ORS key, and no tracing."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RIDEWISE_ORS_API_KEY", "test-key")
    monkeypatch.setenv("RIDEWISE_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    import ridewise.db as db
    from ridewise.agent.graph import build_graph
    from ridewise.config import get_settings
    from ridewise.observability import configure_observability

    get_settings.cache_clear()
    configure_observability.cache_clear()
    build_graph.cache_clear()
    db._engine = None

    yield

    get_settings.cache_clear()
    configure_observability.cache_clear()
    build_graph.cache_clear()
    db._engine = None
