"""回归测试：#113 系统提示词混入动态内容会破坏 prompt caching 前缀稳定性。

覆盖点（对应 issue 验收标准）：
1. build_system_prompt() 返回的 system 提示词不含任何信息类动态内容
   （无“当前时间”、无用户称呼/地址/输出语言）。
2. build_messages()[0] 是纯静态 system 消息；动态内容
   （now / 用户信息 / session_summary / channel / chat_id / account_id）
   全部出现在 user 消息中。
3. team_reminder（@ 团队提醒）维持注入 system 消息的既有行为（本次未动，独立议题）。
4. 历史消息顺序、附件路径提示、人格切换默认值等既有行为不回归。

测试通过子类覆盖 DB 相关私有方法，运行无需数据库与环境变量。
"""
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.agent.context import ContextBuilder  # noqa: E402

SESSION_SUMMARY = "S1-summary-会话摘要"
CHANNEL = "feishu"
CHAT_ID = "oc_12345"
ACCOUNT_ID = "acc-999"
PERSONA = SimpleNamespace(
    ai_name="小智",
    user_name="张总",
    user_address="上海",
    output_language="英文",
    personality="professional",
    custom_personality="",
)


class NoDBContextBuilder(ContextBuilder):
    """绕过 DB 访问的 ContextBuilder（数据库相关私有方法在单测中打桩）"""

    def _get_personality_from_db(self, personality_id: str, custom_text: str = "") -> str:
        return f"性格描述:{personality_id}"

    def _get_active_teams_section(self) -> str:
        return ""

    def _get_active_team_names(self):
        return []


def make_builder(tmp_path, **kwargs) -> NoDBContextBuilder:
    return NoDBContextBuilder(workspace=Path(tmp_path), **kwargs)


def full_kwargs(tmp_path):
    return dict(
        history=[
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
        ],
        current_message="帮我总结本周工作进展",
        session_summary=SESSION_SUMMARY,
        media=["/tmp/ctx-attachment-notes.txt"],
        channel=CHANNEL,
        chat_id=CHAT_ID,
        account_id=ACCOUNT_ID,
        persona_config=PERSONA,
    )


# ---------------------------------------------------------------------------
# 1) build_system_prompt() 为纯静态
# ---------------------------------------------------------------------------

def test_build_system_prompt_has_no_dynamic_content(tmp_path):
    builder = make_builder(tmp_path)

    for persona in (None, PERSONA):
        sys_prompt = builder.build_system_prompt(persona_config=persona)
        assert "当前时间" not in sys_prompt
        assert "用户称呼" not in sys_prompt
        assert "用户常用地址" not in sys_prompt
        assert "默认输出语言" not in sys_prompt
        # 静态锚点仍应保留
        assert "# 核心身份" in sys_prompt
        assert "运行环境: " in sys_prompt


# ---------------------------------------------------------------------------
# 2) messages[0] 纯静态，动态内容全部落在 user 消息
# ---------------------------------------------------------------------------

def test_messages_system_static_and_dynamic_in_user(tmp_path):
    builder = make_builder(tmp_path)
    messages = builder.build_messages(**full_kwargs(tmp_path))

    assert messages[0]["role"] == "system"
    system_content = messages[0]["content"]
    user_content = messages[-1]["content"]

    # system 消息不含任何动态内容
    assert "当前时间" not in system_content
    assert "用户称呼" not in system_content
    assert SESSION_SUMMARY not in system_content
    assert CHAT_ID not in system_content
    assert ACCOUNT_ID not in system_content

    # 动态内容全部出现在 user 消息
    assert "## 当前会话上下文" in user_content
    assert "当前时间" in user_content
    assert "用户称呼: 张总" in user_content
    assert "用户常用地址: 上海" in user_content
    assert "默认输出语言: 英文" in user_content
    assert f"## Current Session Context\n{SESSION_SUMMARY}" in user_content
    assert f"Channel: {CHANNEL}" in user_content
    assert f"Chat ID: {CHAT_ID}" in user_content
    assert f"Account ID: {ACCOUNT_ID}" in user_content


def test_system_message_stable_across_time(monkeypatch, tmp_path):
    """相隔一段时间的两次构建：system 完全一致、user 消息中的时间随之更新。

    用固定时间打桩替代真实 sleep，保持单测快速且确定性；
    真实环境下的跨分钟稳定性在 PR 报告中以 61 秒实测补充说明。
    """
    import backend.modules.agent.context as ctx_mod

    t0 = datetime(2026, 9, 3, 10, 30, 5)
    t1 = datetime(2026, 9, 3, 10, 35, 5)
    fixed_times = iter([t0, t1])

    monkeypatch.setattr(
        ctx_mod,
        "datetime",
        SimpleNamespace(now=lambda: next(fixed_times)),
    )

    builder = make_builder(tmp_path)
    kwargs = full_kwargs(tmp_path)

    first = builder.build_messages(**kwargs)
    second = builder.build_messages(**kwargs)

    assert first[0]["role"] == "system" and second[0]["role"] == "system"
    assert first[0]["content"] == second[0]["content"]

    user_first = first[-1]["content"]
    user_second = second[-1]["content"]
    time_first = t0.strftime("%Y-%m-%d %H:%M (%A)")
    time_second = t1.strftime("%Y-%m-%d %H:%M (%A)")
    assert time_first != time_second
    assert f"- 当前时间: {time_first}" in user_first
    assert f"- 当前时间: {time_second}" in user_second


def test_default_persona_user_info_in_user_message(tmp_path):
    """无 persona 配置时，用户资料回退默认值且不泄漏进 system 消息。"""
    builder = make_builder(tmp_path)
    messages = builder.build_messages(
        history=[], current_message="hi", persona_config=None
    )
    user_content = messages[-1]["content"]
    assert "用户称呼: 老板" in user_content
    assert "默认输出语言: 中文" in user_content
    assert "用户称呼: 老板" not in messages[0]["content"]


# ---------------------------------------------------------------------------
# 3) team_reminder 维持既有行为（本次未动，独立议题）
# ---------------------------------------------------------------------------

def test_team_reminder_still_injected_into_system_message(tmp_path):
    builder = make_builder(tmp_path)
    messages = builder.build_messages(
        history=[],
        current_message="大家看看 @数据分析 这个需求怎么拆",
        persona_config=PERSONA,
    )
    assert "检测到 @ 符号" in messages[0]["content"]
    assert "可用团队" not in messages[-1]["content"]


# ---------------------------------------------------------------------------
# 4) 历史顺序 / 附件路径 / 人格切换等行为不回归
# ---------------------------------------------------------------------------

def test_history_order_and_attachment_path_preserved(tmp_path):
    builder = make_builder(tmp_path)
    messages = builder.build_messages(**full_kwargs(tmp_path))

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "上一轮问题"
    assert messages[2]["content"] == "上一轮回答"
    user_content = messages[-1]["content"]
    assert "帮我总结本周工作进展" in user_content
    assert "/tmp/ctx-attachment-notes.txt" in user_content
    # system 中不应出现工作空间附件路径提示
    assert "ctx-attachment-notes.txt" not in messages[0]["content"]


def test_empty_current_message_falls_back_to_dynamic_context_only(tmp_path):
    builder = make_builder(tmp_path)
    messages = builder.build_messages(
        history=[], current_message="", persona_config=None
    )
    user_content = messages[-1]["content"]
    assert user_content.startswith("## 当前会话上下文")
    assert "当前时间" in user_content
