"""Provider 注册表"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ProviderMetadata:
    """Provider 元数据"""
    id: str
    name: str
    default_api_base: Optional[str] = None
    default_model: Optional[str] = None
    env_key: str = ""
    env_extras: Tuple[Tuple[str, str], ...] = ()


PROVIDER_REGISTRY = {
    "openrouter": ProviderMetadata(
        id="openrouter",
        name="OpenRouter",
        default_api_base="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-4.5-sonnet",
        env_key="OPENROUTER_API_KEY",
    ),
    "anthropic": ProviderMetadata(
        id="anthropic",
        name="Anthropic",
        default_api_base="https://api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        env_key="ANTHROPIC_API_KEY",
    ),
    "openai": ProviderMetadata(
        id="openai",
        name="OpenAI",
        default_api_base="https://api.openai.com/v1",
        default_model="gpt-5.3",
        env_key="OPENAI_API_KEY",
    ),
    "deepseek": ProviderMetadata(
        id="deepseek",
        name="DeepSeek",
        default_api_base="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        env_key="DEEPSEEK_API_KEY",
    ),
    "moonshot": ProviderMetadata(
        id="moonshot",
        name="Moonshot AI / Kimi",
        default_api_base="https://api.moonshot.cn/v1",
        default_model="kimi-k2.5",
        env_key="MOONSHOT_API_KEY",
        env_extras=(("MOONSHOT_API_BASE", "{api_base}"),),
    ),
    "zhipu": ProviderMetadata(
        id="zhipu",
        name="Zhipu AI (GLM)",
        default_api_base="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4.7-flash",
        env_key="OPENAI_API_KEY",
        env_extras=(("ZHIPUAI_API_KEY", "{api_key}"),),
    ),
    "groq": ProviderMetadata(
        id="groq",
        name="Groq",
        default_api_base="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        env_key="GROQ_API_KEY",
    ),
    "mistral": ProviderMetadata(
        id="mistral",
        name="Mistral AI",
        default_api_base="https://api.mistral.ai/v1",
        default_model="mistral-large-latest",
        env_key="MISTRAL_API_KEY",
    ),
    "cohere": ProviderMetadata(
        id="cohere",
        name="Cohere",
        default_api_base="https://api.cohere.com/v2",
        default_model="command-r-plus",
        env_key="COHERE_API_KEY",
    ),
    "together_ai": ProviderMetadata(
        id="together_ai",
        name="Together AI",
        default_api_base="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        env_key="TOGETHERAI_API_KEY",
    ),
    "qwen": ProviderMetadata(
        id="qwen",
        name="Alibaba Cloud Bailian (阿里云百炼)",
        default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3.5-plus",
        env_key="DASHSCOPE_API_KEY",
    ),
    "hunyuan": ProviderMetadata(
        id="hunyuan",
        name="Tencent Cloud (腾讯云)",
        default_api_base="https://hunyuan.tencentcloudapi.com",
        default_model="hunyuan-lite",
        env_key="HUNYUAN_API_KEY",
    ),
    "ernie": ProviderMetadata(
        id="ernie",
        name="Baidu Qianfan (百度智能云千帆)",
        default_api_base="https://qianfan.baidubce.com/v2",
        default_model="ernie-4.0-8k",
        env_key="QIANFAN_API_KEY",
    ),
    "doubao": ProviderMetadata(
        id="doubao",
        name="Volcengine (字节火山引擎)",
        default_api_base="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-pro-32k",
        env_key="ARK_API_KEY",
    ),
    "yi": ProviderMetadata(
        id="yi",
        name="01.AI (Yi)",
        default_api_base="https://api.lingyiwanwu.com/v1",
        default_model="yi-large",
        env_key="YI_API_KEY",
    ),
    "baichuan": ProviderMetadata(
        id="baichuan",
        name="Baichuan AI",
        default_api_base="https://api.baichuan-ai.com/v1",
        default_model="Baichuan4",
        env_key="BAICHUAN_API_KEY",
    ),
    "minimax": ProviderMetadata(
        id="minimax",
        name="MiniMax",
        default_api_base="https://api.minimaxi.com/anthropic",
        default_model="MiniMax-M2.5",
        env_key="ANTHROPIC_API_KEY",
        env_extras=(("ANTHROPIC_BASE_URL", "{api_base}"),),
    ),
    "vllm": ProviderMetadata(
        id="vllm",
        name="vLLM",
        default_api_base="http://localhost:8000/v1",
        default_model="your-model-name",
        env_key="OPENAI_API_KEY",
    ),
    "ollama": ProviderMetadata(
        id="ollama",
        name="Ollama",
        default_api_base="http://localhost:11434/v1",
        default_model="llama3.2",
        env_key="OLLAMA_API_KEY",
    ),
    "lm_studio": ProviderMetadata(
        id="lm_studio",
        name="LM Studio",
        default_api_base="http://localhost:1234/v1",
        default_model="your-model-name",
        env_key="OPENAI_API_KEY",
    ),
    "custom_openai": ProviderMetadata(
        id="custom_openai",
        name="自定义接口 (OpenAI 兼容)",
        default_api_base="",
        default_model="",
        env_key="OPENAI_API_KEY",
    ),
    "custom_anthropic": ProviderMetadata(
        id="custom_anthropic",
        name="自定义接口 (Anthropic 兼容)",
        default_api_base="",
        default_model="",
        env_key="ANTHROPIC_API_KEY",
        env_extras=(("ANTHROPIC_BASE_URL", "{api_base}"),),
    ),
}


def get_provider_metadata(provider_id: str) -> Optional[ProviderMetadata]:
    """获取 provider 元数据"""
    return PROVIDER_REGISTRY.get(provider_id)


def get_all_providers() -> Dict[str, ProviderMetadata]:
    """获取所有 provider"""
    return PROVIDER_REGISTRY.copy()


def get_provider_ids() -> List[str]:
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
