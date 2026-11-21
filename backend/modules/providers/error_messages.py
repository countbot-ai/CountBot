"""Provider 错误解析与用户文案。"""

import json
import re
from typing import Any, Dict, Optional

from loguru import logger

from .base import (
    _TOOL_ARGUMENT_PARSE_ERROR_KEY,
    _TOOL_ARGUMENT_RAW_KEY,
    append_upstream_detail,
)
from .registry import (
    ZHIPU_CODING_API_BASE,
    ZHIPU_STANDARD_API_BASE,
)


def parse_json_arguments(raw: str) -> Dict[str, Any]:
    """解析工具调用参数；失败时返回带哨兵 key 的字典供上层识别。"""
    args_str = (raw or "").strip()
    if not args_str:
        return {}

    try:
        parsed = json.loads(args_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed: {e}, raw: {repr(args_str)}")
        return {
            _TOOL_ARGUMENT_PARSE_ERROR_KEY: f"{type(e).__name__}: {e}",
            _TOOL_ARGUMENT_RAW_KEY: args_str,
        }

    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def is_timeout_exception(error: Exception) -> bool:
    """检测超时类失败，兼容 str(error) 为空的上游实现。"""
    try:
        import httpx

        if isinstance(error, httpx.TimeoutException):
            return True
    except Exception:
        pass

    err_type = type(error).__name__.lower()
    err_text = f"{str(error)} {repr(error)}".lower()
    timeout_hints = (
        "timeout",
        "timed out",
        "readtimeout",
        "connecttimeout",
        "read error",
        "socket",
    )
    return any(hint in err_type or hint in err_text for hint in timeout_hints)


def extract_error_text(error: Exception) -> str:
    response = getattr(error, "response", None)
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    return str(error) or repr(error)


def extract_status_code(error: Exception) -> Optional[int]:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None


def is_expected_upstream_error(error: Exception) -> bool:
    """上游预期内的拒绝/超时/HTML 错误页，日志按 warn 级别记录即可。"""
    status_code = extract_status_code(error)
    if status_code is not None and status_code >= 400:
        return True

    if is_timeout_exception(error):
        return True

    raw = extract_error_text(error).lower()
    return "<html" in raw or "<!doctype html" in raw


def is_invalid_params_error(error: Exception) -> bool:
    status_code = extract_status_code(error)
    raw = extract_error_text(error).lower()
    return (
        status_code == 400
        or "invalid params" in raw
        or "invalid parameter" in raw
        or "invalid_request_error" in raw
        or "requestparamserror" in raw
    )


def summarize_error_for_log(error: Exception) -> str:
    """chat.completions 侧日志摘要：HTML 错误页提取 title/ray id。"""
    status_code = extract_status_code(error)
    raw = extract_error_text(error)
    compact = " ".join((raw or "").split())
    lower = compact.lower()

    if "<html" in lower or "<!doctype html" in lower:
        title_match = re.search(r"<title>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
        ray_match = re.search(r"Cloudflare Ray ID:\s*([A-Za-z0-9-]+)", raw, flags=re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else "HTML error page"
        parts = []
        if status_code is not None:
            parts.append(f"status={status_code}")
        parts.append(title)
        if ray_match:
            parts.append(f"ray_id={ray_match.group(1)}")
        return ", ".join(parts)

    if status_code is not None:
        compact = f"status={status_code}, {compact}"

    return compact[:300]


def summarize_responses_error_for_log(error: Exception) -> str:
    """Responses API 侧日志摘要：脱敏 api_key 后带状态码。"""
    status_code = getattr(error, "status_code", None)
    message = str(error) or repr(error)
    compact = " ".join(message.split())
    if "api_key" in compact.lower() or "apikey" in compact.lower():
        compact = "<redacted>"
    prefix = f"[{status_code}] " if status_code else ""
    return f"{prefix}{type(error).__name__}: {compact[:300]}"


def _zhipu_coding_plan_hint(
    raw: str,
    *,
    provider_id: Optional[str],
    api_base: Optional[str],
) -> str:
    """识别智谱 Coding Plan Key 误用标准端点的情况。

    智谱对两种额度体系共用 Key，但标准开放平台端点不认 Coding Plan 资源包，
    会返回 429/1113（“余额不足或无可用资源包”）。仅凭错误文本无法区分
    “真的没余额”和“端点不匹配”，所以只在标准 bigmodel 端点上给切换提示。
    """
    if "1113" not in raw:
        return ""

    normalized_provider = str(provider_id or "").strip().lower()
    normalized_base = str(api_base or "").strip().rstrip("/").lower()

    if normalized_base and not normalized_base.startswith(
        ZHIPU_STANDARD_API_BASE.lower()
    ):
        return ""
    elif not normalized_base and normalized_provider not in {
        "zhipu",
        "zhipu_coding",
    }:
        return ""

    return (
        "API 返回 1113：账户余额不足或没有可用资源包。"
        "如果这是 GLM Coding Plan 的 Key，请改用 “Zhipu AI (GLM Coding Plan)” "
        f"提供商，或将 Base URL 改为 {ZHIPU_CODING_API_BASE} 后重试。"
    )


def format_openai_error(
    raw: str,
    *,
    provider_id: Optional[str] = None,
    api_base: Optional[str] = None,
) -> str:
    """将 OpenAI 原始错误转换为用户友好提示，并附上上游原始返回。"""
    return append_upstream_detail(
        friendly_openai_error(raw, provider_id=provider_id, api_base=api_base),
        raw,
    )


def friendly_openai_error(
    raw: str,
    *,
    provider_id: Optional[str] = None,
    api_base: Optional[str] = None,
) -> str:
    lower = raw.lower()

    if "image_url" in lower and any(
        token in lower
        for token in (
            "unknown variant",
            "expected `text`",
            "expected text",
            "failed to deserialize",
            "deserialize the json body",
            "does not support image",
            "image input is not supported",
        )
    ):
        return "当前模型或接口不支持图片输入，请切换支持视觉的模型后重试。"

    zhipu_hint = _zhipu_coding_plan_hint(
        raw,
        provider_id=provider_id,
        api_base=api_base,
    )
    if zhipu_hint:
        return zhipu_hint

    # 余额/欠费类：403 或明确提到余额、充值、资源包的场景（优先于限流判定，
    # 因为这类响应里常同时带 quota 字样）
    if any(
        k in lower
        for k in ("余额", "资源包", "充值", "欠费", "insufficient balance",
                  "insufficient_quota", "insufficient_quota_exceeded", "no credit")
    ) or ("403" in lower and any(k in lower for k in ("quota", "balance", "额度"))):
        return "API 账户余额不足或额度已用尽，请前往服务商控制台充值后重试。"

    # 429 / rate limit 类：限流，不是余额问题
    if any(
        k in lower
        for k in ("429", "rate limit", "rate_limit", "too many requests",
                  "overloaded", "负载已饱和", "capacity")
    ):
        return "请求过于频繁，上游限流，请稍后重试。"

    if any(k in lower for k in ("401", "unauthorized", "invalid.*api.*key", "authentication", "token is unusable", "invalid token", "api key")):
        return "API 密钥无效或已过期，请在设置中检查并更新密钥。"

    if any(k in lower for k in ("404", "model not found", "model_not_found", "does not exist")):
        return "所选模型不可用，请在设置中确认模型名称是否正确。"

    if any(k in lower for k in ("context length", "max.*token", "too long", "context_length_exceeded")):
        return "对话上下文过长，请尝试新建会话或清除历史消息。"

    if any(k in lower for k in ("500", "502", "503", "504", "internal server error", "service unavailable")):
        return "AI 服务暂时不可用，请稍后重试。"

    if any(k in lower for k in ("timeout", "connection", "network", "ssl", "timed out")):
        return "网络连接异常，请检查网络设置后重试。"

    # 兜底不再重复拼接原始文本，统一由 append_upstream_detail 附在提示后面
    return "AI 调用出错"


def format_responses_error(raw: str) -> str:
    """将上游原始错误转换为用户友好提示（Responses 侧口径），并附上原始返回。"""
    return append_upstream_detail(friendly_responses_error(raw), raw)


def friendly_responses_error(raw: str) -> str:
    lower = raw.lower()

    if any(
        k in lower
        for k in ("401", "unauthorized", "invalid api key", "invalid_api_key",
                  "authentication", "invalid token", "api key")
    ):
        return "API 密钥无效或已过期，请在设置中检查并更新密钥。"

    # 余额/欠费类优先：这类响应常同时带 quota 字样，先判余额再判限流
    if any(
        k in lower
        for k in ("余额", "资源包", "充值", "欠费", "insufficient balance",
                  "insufficient_quota", "no credit")
    ) or ("403" in lower and any(k in lower for k in ("quota", "balance", "额度"))):
        return "API 账户余额不足或额度已用尽，请前往服务商控制台充值后重试。"

    if any(
        k in lower
        for k in ("429", "rate limit", "rate_limit", "too many requests",
                  "overloaded", "负载已饱和", "capacity")
    ):
        return "请求过于频繁，上游限流，请稍后重试。"

    if any(
        k in lower
        for k in ("404", "model not found", "model_not_found", "does not exist")
    ):
        return "所选模型不可用，请在设置中确认模型名称是否正确。"

    if any(
        k in lower
        for k in ("/responses", "responses api", "unknown url", "not supported")
    ):
        return (
            "该供应商不支持 Responses API，请在供应商设置中把 API 格式"
            "改为 chat.completions 后重试。"
        )

    if any(
        k in lower
        for k in ("context length", "max_output_tokens", "max.*token",
                  "too long", "context_length_exceeded")
    ):
        return "对话上下文或输出长度超出限制，请尝试新建会话或减少输出长度。"

    if any(k in lower for k in ("timeout", "timed out", "readtimeout")):
        return "请求超时，请稍后重试或检查网络连接。"

    for hint in ("connection error", "network", "ssl", "connection refused"):
        if hint in lower:
            return "网络连接异常，请检查网络设置后重试。"

    # 兜底不再重复拼接原始文本，统一由 append_upstream_detail 附在提示后面
    return "AI 调用出错"


def format_anthropic_error(raw: str) -> str:
    """Anthropic 原始错误转为用户提示，并附上游原始返回。"""
    return append_upstream_detail(friendly_anthropic_error(raw), raw)


def friendly_anthropic_error(raw: str) -> str:
    lower = raw.lower()

    if lower in {"", "readtimeout", "timeoutexception"}:
        return "请求超时，请检查 Base URL 是否正确，或稍后重试。"

    if "no module named 'anthropic'" in lower or 'no module named "anthropic"' in lower:
        return "未安装 anthropic Python 依赖，或当前运行环境未打包该模块。"

    # 余额/欠费类优先：这类响应常同时带 quota 字样，先判余额再判限流
    if any(
        k in lower
        for k in ("余额", "资源包", "充值", "欠费", "insufficient balance",
                  "insufficient_quota", "no credit", "credit balance")
    ) or ("403" in lower and any(k in lower for k in ("quota", "balance", "额度"))):
        return "API 账户余额不足或额度已用尽，请前往服务商控制台充值后重试。"

    if any(
        k in lower
        for k in ("429", "rate limit", "rate_limit", "too many requests",
                  "overloaded", "负载已饱和", "capacity")
    ):
        return "请求过于频繁，上游限流，请稍后重试。"

    if any(k in lower for k in ("401", "unauthorized", "invalid api key", "authentication")):
        return "API 密钥无效或已过期，请检查并更新。"

    if "http 404: not found" in lower:
        return "接口地址不存在，请检查 Base URL 是否为 Anthropic 兼容入口。"

    if any(k in lower for k in ("404", "model not found", "model_not_found")):
        return "所选模型不可用，请确认模型名称是否正确。"

    if any(k in lower for k in ("context length", "max token", "too long")):
        return "上下文过长，请减少历史消息或缩短输入。"

    if any(k in lower for k in ("500", "502", "503", "504", "internal server error")):
        return "AI 服务暂时不可用，请稍后重试。"

    if any(k in lower for k in ("timeout", "connection", "network", "ssl")):
        return "网络连接异常，请检查网络或代理设置。"

    # 兜底不再重复拼接原始文本，统一由 append_upstream_detail 附在提示后面
    return "AI 调用出错"
