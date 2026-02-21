"""Provider 注册表"""

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class ProviderMetadata:
    """Provider 元数据"""
    id: str
    name: str
    default_api_base: Optional[str] = None
    default_model: Optional[str] = None
    litellm_prefix: str = ""
    skip_prefixes: tuple[str, ...] = ()
    env_key: str = ""
    env_extras: tuple[tuple[str, str], ...] = ()
    model_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


PROVIDER_REGISTRY = {
    "openrouter": ProviderMetadata(
        id="openrouter",
        name="OpenRouter",
        default_api_base="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-4.5-sonnet",
        litellm_prefix="openrouter",
        skip_prefixes=("openrouter/",),
        env_key="OPENROUTER_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "anthropic": ProviderMetadata(
        id="anthropic",
        name="Anthropic",
        default_api_base="https://api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        litellm_prefix="",
        skip_prefixes=(),
        env_key="ANTHROPIC_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "openai": ProviderMetadata(
        id="openai",
        name="OpenAI",
        default_api_base="https://api.openai.com/v1",
        default_model="gpt-5.3",
        litellm_prefix="",
        skip_prefixes=(),
        env_key="OPENAI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "deepseek": ProviderMetadata(
        id="deepseek",
        name="DeepSeek",
        default_api_base="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        litellm_prefix="deepseek",
        skip_prefixes=("deepseek/",),
        env_key="DEEPSEEK_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "gemini": ProviderMetadata(
        id="gemini",
        name="Google Gemini",
        default_api_base="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-2.0-flash",
        litellm_prefix="gemini",
        skip_prefixes=("gemini/",),
        env_key="GEMINI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "moonshot": ProviderMetadata(
        id="moonshot",
        name="Moonshot AI / Kimi",
        default_api_base="https://api.moonshot.cn/v1",
        default_model="kimi-k2.5",
        litellm_prefix="moonshot",
        skip_prefixes=("moonshot/", "openrouter/"),
        env_key="MOONSHOT_API_KEY",
        env_extras=(("MOONSHOT_API_BASE", "{api_base}"),),
        model_overrides={"kimi-k2.5": {"temperature": 1.0}},
    ),
    "zhipu": ProviderMetadata(
        id="zhipu",
        name="Zhipu AI (GLM)",
        default_api_base="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4.7-flash",
        litellm_prefix="openai",
        skip_prefixes=("openai/", "zhipu/", "openrouter/"),
        env_key="OPENAI_API_KEY",
        env_extras=(("ZHIPUAI_API_KEY", "{api_key}"),),
        model_overrides={},
    ),
    "groq": ProviderMetadata(
        id="groq",
        name="Groq",
        default_api_base="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        litellm_prefix="groq",
        skip_prefixes=("groq/",),
        env_key="GROQ_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "mistral": ProviderMetadata(
        id="mistral",
        name="Mistral AI",
        default_api_base="https://api.mistral.ai/v1",
        default_model="mistral-large-latest",
        litellm_prefix="mistral",
        skip_prefixes=("mistral/",),
        env_key="MISTRAL_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "cohere": ProviderMetadata(
        id="cohere",
        name="Cohere",
        default_api_base="https://api.cohere.com/v2",
        default_model="command-r-plus",
        litellm_prefix="cohere_chat",
        skip_prefixes=("cohere_chat/",),
        env_key="COHERE_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "together_ai": ProviderMetadata(
        id="together_ai",
        name="Together AI",
        default_api_base="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        litellm_prefix="together_ai",
        skip_prefixes=("together_ai/",),
        env_key="TOGETHERAI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "qwen": ProviderMetadata(
        id="qwen",
        name="Alibaba Cloud Bailian (阿里云百炼)",
        default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3.5-plus",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="DASHSCOPE_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "hunyuan": ProviderMetadata(
        id="hunyuan",
        name="Tencent Cloud (腾讯云)",
        default_api_base="https://hunyuan.tencentcloudapi.com",
        default_model="hunyuan-lite",
        litellm_prefix="hunyuan",
        skip_prefixes=("hunyuan/",),
        env_key="HUNYUAN_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "ernie": ProviderMetadata(
        id="ernie",
        name="Baidu Qianfan (百度智能云千帆)",
        default_api_base="https://qianfan.baidubce.com/v2",
        default_model="ernie-4.0-8k",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="QIANFAN_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "doubao": ProviderMetadata(
        id="doubao",
        name="Volcengine (字节火山引擎)",
        default_api_base="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-pro-32k",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="ARK_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "yi": ProviderMetadata(
        id="yi",
        name="01.AI (Yi)",
        default_api_base="https://api.lingyiwanwu.com/v1",
        default_model="yi-large",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="YI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "baichuan": ProviderMetadata(
        id="baichuan",
        name="Baichuan AI",
        default_api_base="https://api.baichuan-ai.com/v1",
        default_model="Baichuan4",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="BAICHUAN_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "minimax": ProviderMetadata(
        id="minimax",
        name="MiniMax",
        default_api_base="https://api.minimaxi.com/anthropic",
        default_model="MiniMax-M2.5",
        litellm_prefix="anthropic",
        skip_prefixes=("anthropic/",),
        env_key="ANTHROPIC_API_KEY",
        env_extras=(("ANTHROPIC_BASE_URL", "{api_base}"),),
        model_overrides={},
    ),
    "vllm": ProviderMetadata(
        id="vllm",
        name="vLLM",
        default_api_base="http://localhost:8000/v1",
        default_model="your-model-name",
        litellm_prefix="hosted_vllm",
        skip_prefixes=("hosted_vllm/",),
        env_key="HOSTED_VLLM_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "ollama": ProviderMetadata(
        id="ollama",
        name="Ollama",
        default_api_base="http://localhost:11434",
        default_model="llama3.2",
        litellm_prefix="ollama",
        skip_prefixes=("ollama/",),
        env_key="OLLAMA_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "lm_studio": ProviderMetadata(
        id="lm_studio",
        name="LM Studio",
        default_api_base="http://localhost:1234/v1",
        default_model="your-model-name",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="OPENAI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "custom_openai": ProviderMetadata(
        id="custom_openai",
        name="Custom API (OpenAI)",
        default_api_base="",
        default_model="",
        litellm_prefix="openai",
        skip_prefixes=("openai/",),
        env_key="OPENAI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "custom_gemini": ProviderMetadata(
        id="custom_gemini",
        name="Custom API (Gemini)",
        default_api_base="",
        default_model="",
        litellm_prefix="gemini",
        skip_prefixes=("gemini/",),
        env_key="GEMINI_API_KEY",
        env_extras=(),
        model_overrides={},
    ),
    "custom_anthropic": ProviderMetadata(
        id="custom_anthropic",
        name="Custom API (Anthropic)",
        default_api_base="",
        default_model="",
        litellm_prefix="anthropic",
        skip_prefixes=("anthropic/",),
        env_key="ANTHROPIC_API_KEY",
        env_extras=(("ANTHROPIC_BASE_URL", "{api_base}"),),
        model_overrides={},
    ),
}


def get_provider_metadata(provider_id: str) -> Optional[ProviderMetadata]:
    """获取 provider 元数据"""
    return PROVIDER_REGISTRY.get(provider_id)


def get_all_providers() -> dict[str, ProviderMetadata]:
    """获取所有 provider"""
    return PROVIDER_REGISTRY.copy()


def get_provider_ids() -> list[str]:
    """获取所有 provider ID"""
    return list(PROVIDER_REGISTRY.keys())


def find_provider_by_api_base(api_base: str) -> Optional[ProviderMetadata]:
    """根据 API base URL 查找 provider"""
    if not api_base:
        return None
    
    api_base_lower = api_base.lower().rstrip("/")
    
    # 特殊域名匹配
    if "moonshot.cn" in api_base_lower or "moonshot.ai" in api_base_lower:
        return PROVIDER_REGISTRY.get("moonshot")
    elif "bigmodel.cn" in api_base_lower:
        return PROVIDER_REGISTRY.get("zhipu")
    elif "openrouter" in api_base_lower:
        return PROVIDER_REGISTRY.get("openrouter")
    
    # 通用匹配：遍历注册表，比较 default_api_base
    for provider_id, metadata in PROVIDER_REGISTRY.items():
        if metadata.default_api_base:
            default_lower = metadata.default_api_base.lower().rstrip("/")
            if api_base_lower == default_lower or api_base_lower.startswith(default_lower):
                return metadata
    
    return None
