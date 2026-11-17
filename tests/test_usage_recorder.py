"""模型用量记录测试

覆盖各供应商字段归一化、空值容错、落库与汇总查询。
"""

import pytest

from backend.modules.session.usage_recorder import (
    has_usage,
    normalize_usage,
    record_usage,
    summarize_usage,
)


def test_normalize_openai_style():
    result = normalize_usage(
        {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    )
    assert result["prompt_tokens"] == 120
    assert result["completion_tokens"] == 30
    assert result["total_tokens"] == 150


def test_normalize_anthropic_style_with_cache():
    result = normalize_usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 100,
        }
    )
    assert result["cache_read_tokens"] == 800
    assert result["cache_write_tokens"] == 100


def test_normalize_input_output_alias():
    """部分供应商用 input/output 命名。"""
    result = normalize_usage({"input_tokens": 40, "output_tokens": 10})
    assert result["prompt_tokens"] == 40
    assert result["completion_tokens"] == 10
    assert result["total_tokens"] == 50


def test_normalize_total_falls_back_to_sum():
    result = normalize_usage({"prompt_tokens": 7, "completion_tokens": 3})
    assert result["total_tokens"] == 10


def test_normalize_nested_reasoning_details():
    result = normalize_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 15},
        }
    )
    assert result["reasoning_tokens"] == 15


def test_normalize_handles_none_and_garbage():
    assert has_usage(normalize_usage(None)) is False
    assert has_usage(normalize_usage({})) is False
    assert has_usage(normalize_usage({"prompt_tokens": "abc"})) is False


def test_normalize_string_numbers():
    result = normalize_usage({"prompt_tokens": "12", "completion_tokens": "8"})
    assert result["prompt_tokens"] == 12
    assert result["total_tokens"] == 20


@pytest.mark.asyncio
async def test_record_and_summarize(tmp_path, monkeypatch):
    """落库后能在汇总结果里看到对应数字。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.database as database
    from backend.database import Base

    db_path = tmp_path / "usage_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)

    record = await record_usage(
        session_id="s-usage-1",
        provider="openai",
        model="gpt-test",
        turn_index=1,
        raw_usage={"prompt_tokens": 100, "completion_tokens": 50},
    )
    assert record is not None
    assert record.total_tokens == 150

    summary = await summarize_usage(session_id="s-usage-1", days=1)
    assert summary["total_requests"] == 1
    assert summary["prompt_tokens"] == 100
    assert summary["completion_tokens"] == 50
    assert summary["total_tokens"] == 150
    assert any(item["model"] == "gpt-test" for item in summary["by_model"])

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_skips_empty_usage(tmp_path, monkeypatch):
    """供应商未上报用量时不应写空记录。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.database as database
    from backend.database import Base

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(
        database, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False)
    )

    assert await record_usage(session_id="s", raw_usage=None) is None
    assert await record_usage(session_id="s", raw_usage={}) is None

    await engine.dispose()

# ---------------------------------------------------------------------------
# 嵌套明细字段（OpenAI 系把缓存/推理放在 *_details 子对象里）
# ---------------------------------------------------------------------------


def test_normalize_openai_cached_tokens_detail():
    """prompt_tokens_details.cached_tokens 必须被计入缓存命中。

    该字段是 OpenAI 官方上报缓存命中的形式；早期实现只查顶层别名，
    所有缓存命中都被算成 0，导致成本统计系统性偏高。
    """
    result = normalize_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 80},
        }
    )
    assert result["cache_read_tokens"] == 80
    assert result["prompt_tokens"] == 100


def test_normalize_reasoning_in_completion_details():
    result = normalize_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 15},
        }
    )
    assert result["reasoning_tokens"] == 15


def test_normalize_both_details_together():
    result = normalize_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 80},
            "completion_tokens_details": {"reasoning_tokens": 15},
        }
    )
    assert result["cache_read_tokens"] == 80
    assert result["reasoning_tokens"] == 15


def test_normalize_deepseek_cache_keys():
    """DeepSeek 用 prompt_cache_hit/miss_tokens 表达缓存。"""
    result = normalize_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_cache_hit_tokens": 60,
            "prompt_cache_miss_tokens": 40,
        }
    )
    assert result["cache_read_tokens"] == 60
    assert result["cache_write_tokens"] == 40
