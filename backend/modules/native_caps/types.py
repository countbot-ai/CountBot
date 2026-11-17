"""原生能力配置类型与归一化。"""

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

DOCUMENT_PARSING_MODES = ("off", "text", "rich")
DocumentParsingMode = Literal["off", "text", "rich"]


class NativeCapabilities(BaseModel):
    """模型条目上的原生能力开关；全部默认关闭，保证存量行为不变。"""

    web_search: bool = Field(False, description="联网搜索 / 深度思考搜索")
    read_url: bool = Field(False, description="自动阅读用户消息中的链接")
    document_parsing: DocumentParsingMode = Field(
        "off", description="文档解析：off / text（纯文本）/ rich（图文混排）"
    )
    safety_check: bool = Field(False, description="服务端基础风控（safety_check=high）")
    asr: bool = Field(False, description="语音输入（ASR）")
    tts: bool = Field(False, description="朗读回答（TTS）")

    def enabled_keys(self) -> list[str]:
        keys: list[str] = []
        if self.web_search:
            keys.append("web_search")
        if self.read_url:
            keys.append("read_url")
        if self.document_parsing != "off":
            keys.append("document_parsing")
        if self.safety_check:
            keys.append("safety_check")
        if self.asr:
            keys.append("asr")
        if self.tts:
            keys.append("tts")
        return keys

    def any_enabled(self) -> bool:
        return bool(self.enabled_keys())


DEFAULT_CAPABILITIES = NativeCapabilities()


def normalize_native_capabilities(raw: Any) -> NativeCapabilities:
    """把任意来源（配置、接口、历史）的字段收敛成合法能力配置。"""
    if isinstance(raw, NativeCapabilities):
        return raw
    if not isinstance(raw, dict):
        return NativeCapabilities()

    mode = str(raw.get("document_parsing") or "off").strip().lower()
    if mode not in DOCUMENT_PARSING_MODES:
        mode = "off"

    return NativeCapabilities(
        web_search=bool(raw.get("web_search")),
        read_url=bool(raw.get("read_url")),
        document_parsing=mode,  # type: ignore[arg-type]
        safety_check=bool(raw.get("safety_check")),
        asr=bool(raw.get("asr")),
        tts=bool(raw.get("tts")),
    )


def capability_enabled(caps: Any, key: str) -> bool:
    normalized = normalize_native_capabilities(caps)
    return key in normalized.enabled_keys()


def dump_capabilities(caps: Any) -> Dict[str, Any]:
    return normalize_native_capabilities(caps).model_dump()
