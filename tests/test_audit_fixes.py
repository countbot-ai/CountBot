"""审计修复项回归测试

覆盖：Anthropic 消息净化、模板渲染兜底、记忆空标记判定、会话名精确匹配、
技能名称校验与注入上限、队列去重与哈希、cron 任务占用互斥、工作区校验参数优先级。
"""

import asyncio
import time

import pytest


# ---------------------------------------------------------------------------
# Anthropic 消息净化
# ---------------------------------------------------------------------------


def test_anthropic_strips_non_schema_fields():
    """assistant 消息只保留 role/content，reasoning_content 不得进入请求体。"""
    from backend.modules.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    _, messages = provider._normalize_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "answer",
                "reasoning_content": "internal thoughts",
            },
        ]
    )

    assistant = [m for m in messages if m["role"] == "assistant"][0]
    assert set(assistant) == {"role", "content"}
    assert "reasoning_content" not in assistant


def test_anthropic_keeps_tool_flow_intact():
    """净化不能破坏工具调用与结果的配对结构。"""
    from backend.modules.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    _, messages = provider._normalize_messages(
        [
            {"role": "user", "content": "read it"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "body"},
        ]
    )

    assert messages[1]["content"][0]["type"] == "tool_use"
    assert messages[2]["content"][0]["type"] == "tool_result"


# ---------------------------------------------------------------------------
# 模板渲染
# ---------------------------------------------------------------------------


def test_render_prompt_keeps_missing_placeholder():
    from backend.modules.agent.prompts import render_prompt

    assert render_prompt("a {x} b {y}", x=1) == "a 1 b {y}"


def test_render_prompt_survives_literal_braces():
    from backend.modules.agent.prompts import render_prompt

    template = '示例 {"k": 1} 与 {value}'
    result = render_prompt(template, value="ok")
    assert "ok" in result


def test_render_prompt_empty_template():
    from backend.modules.agent.prompts import render_prompt

    assert render_prompt("") == ""


# ---------------------------------------------------------------------------
# 记忆空标记
# ---------------------------------------------------------------------------


def test_memory_noop_only_matches_whole_output():
    """正常总结里出现哨兵词不应被判为无内容。"""
    from backend.modules.agent.prompts import is_memory_noop

    assert is_memory_noop("NOTHING_TO_RECORD") is True
    assert is_memory_noop("无需记录") is True
    assert is_memory_noop("无需记录。") is True
    assert is_memory_noop("") is True
    # 关键回归：包含哨兵词但有实际内容
    assert is_memory_noop("用户要求日志无需记录级别设为 WARN") is False
    assert is_memory_noop("记录了三条偏好，NOTHING_TO_RECORD 不适用") is False


# ---------------------------------------------------------------------------
# 会话名精确匹配
# ---------------------------------------------------------------------------


def test_session_name_matches_requires_boundary():
    """前缀匹配必须要求分隔符，避免 chat_id 前缀碰撞。"""
    from backend.modules.session.manager import session_name_matches

    condition = str(session_name_matches("telegram:default:123").compile(
        compile_kwargs={"literal_binds": True}
    ))
    # 生成的 SQL 里前缀后必须紧跟冒号，而不是裸 %
    assert "telegram:default:123:%" in condition
    assert "telegram:default:123%" not in condition.replace("telegram:default:123:%", "")


def test_session_name_matches_escapes_wildcards():
    from backend.modules.session.manager import session_name_matches

    condition = str(session_name_matches("a_b%c").compile(
        compile_kwargs={"literal_binds": True}
    ))
    assert "a\\_b\\%c" in condition


# ---------------------------------------------------------------------------
# 技能名称校验与注入上限
# ---------------------------------------------------------------------------


def test_add_skill_rejects_path_traversal(tmp_path):
    from backend.modules.agent.skills import SkillsLoader

    loader = SkillsLoader(skills_dir=tmp_path / "skills")
    before = set(p.name for p in tmp_path.iterdir()) if tmp_path.exists() else set()

    assert loader.add_skill("../../evil", "---\nname: evil\n---\n") is False
    assert loader.add_skill("a/b", "---\nname: ab\n---\n") is False
    assert loader.add_skill("..", "x") is False

    after = set(p.name for p in tmp_path.iterdir()) if tmp_path.exists() else set()
    assert after == before, "rejected names must not create directories outside skills dir"


def test_add_skill_accepts_normal_name(tmp_path):
    from backend.modules.agent.skills import SkillsLoader

    loader = SkillsLoader(skills_dir=tmp_path / "skills")
    assert loader.add_skill("my-skill", "---\nname: my-skill\ndescription: d\n---\nbody") is True


def test_skill_summary_truncates_description(tmp_path):
    from backend.modules.agent.skills import (
        MAX_SKILL_SUMMARY_DESC_CHARS,
        SkillsLoader,
    )

    skills_dir = tmp_path / "skills" / "long-desc"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: long-desc\ndescription: " + "x" * 5000 + "\n---\nbody\n",
        encoding="utf-8",
    )

    loader = SkillsLoader(
        skills_dir=skills_dir.parent,
        builtin_skills_dir=tmp_path / "nonexistent-builtin",
        external_skills_dirs=[],
    )
    summary = loader.build_skills_summary()

    line = next(l for l in summary.splitlines() if l.startswith("- long-desc"))
    # 单条描述被截断到上限附近，而不是把 5000 字原样带入
    assert len(line) < MAX_SKILL_SUMMARY_DESC_CHARS + 100


def test_skill_summary_caps_total_length(tmp_path):
    """技能数量多时摘要总量受控。"""
    from backend.modules.agent.skills import MAX_SKILL_SUMMARY_CHARS, SkillsLoader

    skills_root = tmp_path / "skills"
    for i in range(120):
        d = skills_root / f"skill-{i:03d}"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: skill-{i:03d}\ndescription: {'d' * 300}\n---\nbody\n",
            encoding="utf-8",
        )

    loader = SkillsLoader(
        skills_dir=skills_root,
        builtin_skills_dir=tmp_path / "nonexistent-builtin",
        external_skills_dirs=[],
    )
    summary = loader.build_skills_summary()
    assert len(summary) <= MAX_SKILL_SUMMARY_CHARS + 200
    assert "未列出" in summary


def test_always_skill_content_truncated(tmp_path):
    from backend.modules.agent.skills import (
        MAX_ALWAYS_SKILL_CHARS,
        SkillsLoader,
    )

    skills_dir = tmp_path / "skills" / "huge"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: huge\ndescription: d\nalways: true\n---\n" + "y" * 50000,
        encoding="utf-8",
    )

    loader = SkillsLoader(skills_dir=tmp_path / "skills")
    content = loader.load_skills_for_context(["huge"])
    assert len(content) < MAX_ALWAYS_SKILL_CHARS + 500
    assert "read_file" in content


# ---------------------------------------------------------------------------
# 队列去重
# ---------------------------------------------------------------------------


def _inbound(content="hi", media=None):
    from backend.modules.channels.base import InboundMessage

    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content=content,
        media=media or [],
    )


def test_hash_includes_media():
    """同一文案配不同图片必须视为不同消息。"""
    from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue

    queue = EnterpriseMessageQueue()
    h1 = queue._hash_message(_inbound("看这个", ["a.png"]))
    h2 = queue._hash_message(_inbound("看这个", ["b.png"]))
    h3 = queue._hash_message(_inbound("看这个", []))

    assert h1 != h2
    assert h1 != h3
    assert h3 == queue._hash_message(_inbound("看这个", []))


def test_dedup_sweeps_expired_entries():
    """过期条目应被周期清扫，避免字典无限增长。"""
    from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue

    queue = EnterpriseMessageQueue(dedup_window=1)
    queue._message_hashes["stale"] = time.time() - 10

    # 达到清扫间隔后触发一次全表扫描
    queue._dedup_checks = queue._DEDUP_SWEEP_INTERVAL - 1
    queue._is_duplicate("probe")

    assert "stale" not in queue._message_hashes


# ---------------------------------------------------------------------------
# cron 任务占用互斥
# ---------------------------------------------------------------------------


def test_try_acquire_job_is_atomic():
    from backend.modules.cron.scheduler import CronScheduler

    scheduler = CronScheduler.__new__(CronScheduler)
    scheduler._active_jobs = set()

    assert scheduler.try_acquire_job("job-1") is True
    # 第二次必须失败，否则并发触发会重复执行
    assert scheduler.try_acquire_job("job-1") is False
    assert scheduler.is_job_active("job-1") is True

    scheduler.release_job("job-1")
    assert scheduler.is_job_active("job-1") is False
    assert scheduler.try_acquire_job("job-1") is True


def test_cron_execution_uses_session_gate():
    """cron 执行必须与 IM/WS 共用闸门，避免并发写同一会话历史。"""
    import inspect

    from backend.modules.cron import executor as executor_module

    source = inspect.getsource(executor_module.CronExecutor.execute)
    assert "get_session_gate" in source
    assert "gate.acquire" in source
    assert "gate.release" in source


# ---------------------------------------------------------------------------
# 工作区校验参数优先级
# ---------------------------------------------------------------------------


def test_validator_explicit_workspace_wins(tmp_path):
    """显式传入的 workspace 不能被全局配置覆盖。"""
    from backend.modules.tools.filesystem import WorkspaceValidator

    validator = WorkspaceValidator(tmp_path, restrict_to_workspace=False)
    assert validator.workspace == tmp_path.resolve()
    assert validator.restrict_to_workspace is False


def test_validator_accepts_outside_path_when_unrestricted(tmp_path):
    from backend.modules.tools.filesystem import WorkspaceValidator

    validator = WorkspaceValidator(tmp_path, restrict_to_workspace=False)
    outside = tmp_path.parent / "outside.txt"
    resolved = validator.validate_path(str(outside))
    assert resolved == outside.resolve() or str(resolved).endswith("outside.txt")
