"""从上游拉取供应商的可用模型清单（含上下文窗口）。"""

from typing import Dict, List, Optional, Tuple

import httpx
from loguru import logger

from backend.modules.compression.model_meta import extract_context_length, parse_models_payload
from backend.modules.providers.factory import (
    API_TYPE_ANTHROPIC_MESSAGES,
    API_TYPE_OPENAI_CHAT,
    API_TYPE_OPENAI_RESPONSES,
)

CATALOG_TIMEOUT_SECONDS = 15.0

ANTHROPIC_VERSION = "2023-06-01"


class ModelCatalogError(Exception):
    """拉取模型清单失败，message 已是面向用户的文案。"""


def _normalize_base_url(api_base: Optional[str]) -> str:
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        raise ModelCatalogError("请先填写 Base URL，再获取模型列表。")
    return base


def _strip_version_suffix(base: str) -> str:
    """去掉末尾的 /v1，用于按需拼接版本段。"""
    if base.endswith("/v1"):
        return base[: -len("/v1")]
    return base


def resolve_models_endpoint(api_base: Optional[str], api_type: str) -> str:
    """按协议推导模型列表地址。"""
    base = _normalize_base_url(api_base)

    if api_type == API_TYPE_ANTHROPIC_MESSAGES:
        # Anthropic 的模型接口不在 /v1 下再套一层
        return f"{_strip_version_suffix(base)}/v1/models"

    if api_type == API_TYPE_OPENAI_RESPONSES:
        # Responses 与 chat 共用同一份模型清单
        return f"{base}/models"

    if api_type == API_TYPE_OPENAI_CHAT:
        return f"{base}/models"

    raise ModelCatalogError(f"不支持的协议: {api_type}")


def build_catalog_headers(api_key: Optional[str], api_type: str) -> Dict[str, str]:
    """按协议构造鉴权头；没有 key 时留空（本地模型服务可能不校验）。"""
    key = str(api_key or "").strip()
    headers: Dict[str, str] = {"Accept": "application/json"}

    if api_type == API_TYPE_ANTHROPIC_MESSAGES:
        if key:
            headers["x-api-key"] = key
        headers["anthropic-version"] = ANTHROPIC_VERSION
        return headers

    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def parse_catalog_payload(
    payload: object, api_type: str
) -> List[Tuple[str, Optional[str], Optional[str], Optional[int]]]:
    """把上游响应解析成 (id, display_name, owned_by, context_window) 列表。

    OpenAI / Anthropic 都用 {"data": [...]}，个别自建网关直接返回数组，
    两种形态都接受；非字符串 id 的条目直接跳过而不是报错。

    窗口字段的提取规则见 ``compression.model_meta.extract_context_length``：
    只读顶层、按别名集合匹配，避免嵌套段落里的同名字段污染。
    """
    raw_items: List[object] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            raw_items = data
        elif isinstance(payload.get("models"), list):
            raw_items = payload["models"]  # type: ignore[assignment]
    elif isinstance(payload, list):
        raw_items = payload

    seen: set[str] = set()
    result: List[Tuple[str, Optional[str], Optional[str], Optional[int]]] = []
    for item in raw_items:
        if isinstance(item, str):
            model_id, display_name, owned_by, context_window = item.strip(), None, None, None
        elif isinstance(item, dict):
            model_id = str(
                item.get("id") or item.get("name") or item.get("model") or ""
            ).strip()
            display_name = str(
                item.get("display_name") or item.get("displayName") or ""
            ).strip() or None
            owned_by = str(item.get("owned_by") or item.get("ownedBy") or "").strip() or None
            context_window = extract_context_length(item)
        else:
            continue

        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        result.append((model_id, display_name, owned_by, context_window))

    return result


def _normalize_error(status_code: int, body: str) -> str:
    snippet = " ".join((body or "").split())[:200]
    if status_code in (401, 403):
        return "API 密钥无效或无权限，请检查密钥后重试。"
    if status_code == 404:
        return "该地址没有模型列表接口，请检查 Base URL 是否填写正确。"
    if status_code == 429:
        return "请求过于频繁或配额不足，请稍后重试。"
    return f"获取模型列表失败（HTTP {status_code}）: {snippet}"


async def fetch_provider_models(
    *,
    api_base: Optional[str],
    api_key: Optional[str],
    api_type: str,
) -> List[Tuple[str, Optional[str], Optional[str], Optional[int]]]:
    """请求上游模型清单。失败抛 ModelCatalogError（含用户可读文案）。"""
    endpoint = resolve_models_endpoint(api_base, api_type)
    headers = build_catalog_headers(api_key, api_type)

    logger.info(f"Fetching provider model catalog: {endpoint} (api_type={api_type})")

    try:
        async with httpx.AsyncClient(timeout=CATALOG_TIMEOUT_SECONDS) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.TimeoutException as exc:
        raise ModelCatalogError("获取模型列表超时，请检查网络或 Base URL。") from exc
    except httpx.HTTPError as exc:
        raise ModelCatalogError(f"无法连接模型服务: {exc}") from exc

    if response.status_code >= 400:
        raise ModelCatalogError(_normalize_error(response.status_code, response.text))

    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelCatalogError("模型列表返回的不是合法 JSON。") from exc

    models = parse_catalog_payload(payload, api_type)
    if not models:
        raise ModelCatalogError("上游没有返回任何模型。")
    return models
