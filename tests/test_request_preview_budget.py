"""请求预览的额度口径测试：显式额度优先，0/None 表示不限制。"""

import json
from pathlib import Path

from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.request_preview import build_request_preview


class _NoDBContextBuilder(ContextBuilder):
    """绕过数据库访问的 ContextBuilder。"""

    def _get_personality_from_db(
        self, personality_id: str, custom_text: str = "", **kwargs
    ) -> str:
        return "性格描述:测试"

    def _get_active_teams_section(self) -> str:
        return ""

    def _get_active_team_names(self):
        return []


def _builder() -> _NoDBContextBuilder:
    return _NoDBContextBuilder(workspace=Path(__file__).resolve().parent, skills=None)


def _dump(**kwargs) -> str:
    preview = build_request_preview(_builder(), message="你好", **kwargs)
    return json.dumps(preview, ensure_ascii=False)


def test_explicit_budget_is_declared():
    text = _dump(tool_budget=25)
    assert "at most 25 tool calls in total" in text


def test_unlimited_budget_is_not_declared():
    text = _dump(tool_budget=0)
    assert "tool calls in total" not in text
