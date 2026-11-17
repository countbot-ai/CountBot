"""模型级原生能力适配层。

把「供应商在服务端执行的对话能力」（联网搜索、阅读链接、文档解析、安全校验）
与「独立工具能力」（ASR/TTS）收敛到同一套配置与事件协议里，供各 Provider
按需注入请求、解析流式结果；未启用时完全不改变现有请求。
"""

from .types import (
    DOCUMENT_PARSING_MODES,
    NativeCapabilities,
    capability_enabled,
    normalize_native_capabilities,
)
from .registry import (
    DEEPSEEK_PROVIDER_ID,
    capability_catalog,
    normalize_deepseek_api_base,
    supports_native_capabilities,
)
from .service import (
    build_provider_overrides,
    capabilities_for_provider,
    load_model_capabilities,
    resolve_native_capabilities,
)

__all__ = [
    "DOCUMENT_PARSING_MODES",
    "DEEPSEEK_PROVIDER_ID",
    "NativeCapabilities",
    "build_provider_overrides",
    "capabilities_for_provider",
    "capability_catalog",
    "capability_enabled",
    "load_model_capabilities",
    "normalize_deepseek_api_base",
    "normalize_native_capabilities",
    "resolve_native_capabilities",
    "supports_native_capabilities",
]
