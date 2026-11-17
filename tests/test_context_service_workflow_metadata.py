import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.session.context_service import ConversationContextService


@pytest.mark.asyncio
async def test_build_model_context_strips_workflow_exec_metadata_from_history():
    service = ConversationContextService(db=None)

    async def fake_get_session(session_id: str):
        return SimpleNamespace(
            summary=None,
            short_context_summary=None,
            short_context_summary_msg_id=None,
            short_context_summary_window_size=None,
        )

    async def fake_load_messages(session_id: str, limit=None, after_message_id=None):
        return [
            SimpleNamespace(
                role="assistant",
                content=(
                    "# Pipeline Workflow Results\n\nVisible result"
                    "\n\n<!--WORKFLOW_EXEC:{\"reviewer\":{\"label\":\"Reviewer\"}}:WORKFLOW_EXEC-->"
                ),
            )
        ]

    service.get_session = fake_get_session  # type: ignore[method-assign]
    service._load_messages = fake_load_messages  # type: ignore[method-assign]

    context = await service.build_model_context(
        session_id="session-1",
        max_history_messages=10,
    )

    assert len(context.history) == 1
    assert context.history[0]["role"] == "assistant"
    assert context.history[0]["content"] == "# Pipeline Workflow Results\n\nVisible result"
    assert "WORKFLOW_EXEC" not in context.history[0]["content"]
