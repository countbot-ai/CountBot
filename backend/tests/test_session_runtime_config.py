"""回归测试：会话级运行时配置解析保持一致。"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.config.schema import AppConfig, ModelConfig, PersonaConfig, ProviderConfig
from backend.modules.session import resolve_session_runtime_config


def build_config() -> AppConfig:
    return AppConfig(
        providers={
            "zhipu": ProviderConfig(
                api_key="global-zhipu-key",
                api_base="https://global.zhipu.example/v1",
                enabled=True,
            ),
            "openai": ProviderConfig(
                api_key="global-openai-key",
                api_base="https://global.openai.example/v1",
                enabled=True,
            ),
        },
        model=ModelConfig(
            provider="zhipu",
            model="glm-5",
            temperature=0.7,
            max_tokens=4096,
            max_iterations=25,
        ),
        persona=PersonaConfig(
            ai_name="小C",
            user_name="主人",
            user_address="上海",
            output_language="中文",
            personality="grumpy",
            custom_personality="",
            max_history_messages=100,
        ),
    )


def build_session(*, model=None, persona=None, use_custom=True):
    return SimpleNamespace(
        id="session-runtime-test",
        use_custom_config=use_custom,
        session_model_config=json.dumps(model, ensure_ascii=False) if model is not None else None,
        session_persona_config=json.dumps(persona, ensure_ascii=False) if persona is not None else None,
    )


async def test_provider_switch_uses_global_key_fallback() -> bool:
    config = build_config()
    session = build_session(model={"provider": "openai", "model": "gpt-5-mini", "api_key": "", "api_base": ""})
    runtime = resolve_session_runtime_config(config, session)

    checks = [
        (runtime.provider_name == "openai", f"provider={runtime.provider_name}"),
        (runtime.model_name == "gpt-5-mini", f"model={runtime.model_name}"),
        (runtime.api_key == "global-openai-key", f"api_key={runtime.api_key}"),
        (runtime.api_base == "https://global.openai.example/v1", f"api_base={runtime.api_base}"),
        (runtime.model_response["api_key"] == "", f"response.api_key={runtime.model_response['api_key']}"),
        (runtime.model_response["api_base"] == "", f"response.api_base={runtime.model_response['api_base']}"),
    ]
    failed = [detail for ok, detail in checks if not ok]
    if failed:
        print("❌ provider 全局回退失败:", "; ".join(failed))
        return False
    print("✅ provider/model 可切换，并回退全局 key")
    return True


async def test_session_api_overrides_take_priority() -> bool:
    config = build_config()
    session = build_session(model={
        "provider": "openai",
        "model": "gpt-5-pro",
        "temperature": 0.2,
        "max_tokens": 2048,
        "max_iterations": 8,
        "api_key": "session-openai-key",
        "api_base": "https://session.openai.example/v1",
    })
    runtime = resolve_session_runtime_config(config, session)

    checks = [
        (runtime.api_key == "session-openai-key", f"api_key={runtime.api_key}"),
        (runtime.api_base == "https://session.openai.example/v1", f"api_base={runtime.api_base}"),
        (runtime.temperature == 0.2, f"temperature={runtime.temperature}"),
        (runtime.max_tokens == 2048, f"max_tokens={runtime.max_tokens}"),
        (runtime.max_iterations == 8, f"max_iterations={runtime.max_iterations}"),
    ]
    failed = [detail for ok, detail in checks if not ok]
    if failed:
        print("❌ session API 覆盖失败:", "; ".join(failed))
        return False
    print("✅ session api_key/api_base 与模型参数覆盖优先生效")
    return True


async def test_persona_override_merges_global_defaults() -> bool:
    config = build_config()
    session = build_session(persona={
        "ai_name": "会话助手",
        "personality": "custom",
        "custom_personality": "请使用简洁语气回复。",
    })
    runtime = resolve_session_runtime_config(config, session)

    checks = [
        (runtime.persona_config.ai_name == "会话助手", f"ai_name={runtime.persona_config.ai_name}"),
        (runtime.persona_config.user_name == "主人", f"user_name={runtime.persona_config.user_name}"),
        (runtime.persona_config.user_address == "上海", f"user_address={runtime.persona_config.user_address}"),
        (runtime.persona_config.output_language == "中文", f"output_language={runtime.persona_config.output_language}"),
        (runtime.persona_config.custom_personality == "请使用简洁语气回复。", f"custom_personality={runtime.persona_config.custom_personality}"),
        (runtime.persona_response.get("output_language") == "中文", f"persona_response.output_language={runtime.persona_response.get('output_language')}"),
    ]
    failed = [detail for ok, detail in checks if not ok]
    if failed:
        print("❌ persona 合并失败:", "; ".join(failed))
        return False
    print("✅ session persona 覆盖会合并全局默认字段")
    return True


async def main() -> int:
    results = [
        await test_provider_switch_uses_global_key_fallback(),
        await test_session_api_overrides_take_priority(),
        await test_persona_override_merges_global_defaults(),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))