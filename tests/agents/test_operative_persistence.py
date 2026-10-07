from __future__ import annotations

import pytest

from openjarvis.agents.operative import OperativeAgent
from openjarvis.sessions.session import SessionStore


def test_operative_session_round_trip(tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    try:
        agent = OperativeAgent(
            object(),
            "test-model",
            operator_id="jarvis-auto",
            session_store=store,
        )
        agent._save_session("objective one", "checkpoint one")

        messages = agent._load_session()

        assert [message.content for message in messages] == [
            "objective one",
            "checkpoint one",
        ]
    finally:
        store.close()


def test_new_autonomous_objective_skips_stale_state_and_session(monkeypatch) -> None:
    agent = OperativeAgent(object(), "test-model")

    def fail_state():
        pytest.fail("stale state must not be loaded for a new objective")

    def fail_session():
        pytest.fail("stale session must not be loaded for a new objective")

    monkeypatch.setattr(agent, "_recall_state", fail_state)
    monkeypatch.setattr(agent, "_load_session", fail_session)
    monkeypatch.setattr(
        agent,
        "_generate",
        lambda messages, **kwargs: {
            "content": "checkpoint",
            "tool_calls": [],
            "usage": {},
            "finish_reason": "stop",
        },
    )

    result = agent.run("NEW AUTONOMOUS OBJECTIVE. validate runtime")

    assert result.content == "checkpoint"
