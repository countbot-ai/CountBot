"""原生能力支持矩阵与能力元数据。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DEEPSEEK_PROVIDER_ID = "deepseek"

PROTOCOL_CHAT = "openai-chat-completions"
PROTOCOL_RESPONSES = "openai-responses"
PROTOCOL_ANTHROPIC = "anthropic-messages"


def supports_native_capabilities(provider_id: Optional[str], model: Optional[str] = None) -> bool:
    """原生能力由模型勾选启用，与供应商来源无关。"""
    _ = model
    return bool(str(provider_id or "").strip())


def normalize_deepseek_api_base(api_base: Optional[str]) -> str:
    """统一 DeepSeek API 根地址（不带 /v1 与 /anthropic）。"""
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        return "https://api.deepseek.com"
    if "deepseek.com" in base:
        return "https://api.deepseek.com"
    for suffix in ("/v1", "/anthropic"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base or "https://api.deepseek.com"


def resolve_anthropic_base(api_base: Optional[str]) -> str:
    """DeepSeek Anthropic 兼容端点根地址。"""
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        return "https://api.deepseek.com/anthropic"
    if base.endswith("/anthropic"):
        return base
    if "deepseek.com" in base:
        return "https://api.deepseek.com/anthropic"
    return base


def capability_catalog() -> List[Dict[str, Any]]:
    """前端高级设置使用的能力清单（顺序即展示顺序）。"""
    return [
        {
            "key": "web_search",
            "label": "联网搜索",
            "description": "非思考模式联网搜索；思考模式自动升级为深度思考搜索",
        },
        {
            "key": "read_url",
            "label": "阅读链接",
            "description": "自动识别消息中的链接并抓取正文作答",
        },
        {
            "key": "document_parsing",
            "label": "文档解析",
            "description": "PDF / Office / 图片由服务端解析后拼入上下文",
            "mode": True,
        },
        {
            "key": "safety_check",
            "label": "内容安全",
            "description": "开启服务端基础风控，命中风险时返回拒答",
        },
        {
            "key": "asr",
            "label": "语音输入",
            "description": "把录音转写为文字后发送",
        },
        {
            "key": "tts",
            "label": "语音朗读",
            "description": "朗读助手回答",
        },
    ]
