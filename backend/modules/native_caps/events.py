"""把各协议的服务端工具块归一化成前端可用的事件。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

SEARCH_KINDS = {"search", "deep_search", "image_search", "deep_image_search"}
FETCH_KINDS = {"read_link", "deep_search"}


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            data = dump()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_object(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _public_search_result(item: Any) -> Optional[Dict[str, Any]]:
    data = _as_dict(item)
    if data.get("type") == "web_search_tool_result_error":
        return {"error": _text(data.get("error_code") or "unavailable")}
    if data.get("type") != "web_search_result":
        return None
    url = _text(data.get("url"))
    if not url:
        return None
    return {
        "title": _text(data.get("title")),
        "url": url,
        "snippet": _text(data.get("snippet")),
        "site_name": _text(data.get("site_name")) or None,
        "site_icon": _text(data.get("site_icon")) or None,
        "page_age": _text(data.get("page_age")) or None,
        "image_url": _text(data.get("image_url")) or None,
    }


def _flatten_server_tool_calls(payload: Any) -> List[Dict[str, Any]]:
    """Chat Completions 的 server_tool_calls 是 [{index, calls:[...]}] 的分步结构。"""
    flattened: List[Dict[str, Any]] = []
    for step in payload or []:
        step_data = _as_dict(step)
        calls = step_data.get("calls")
        if isinstance(calls, list):
            flattened.extend(_as_dict(call) for call in calls if _as_dict(call))
        elif step_data:
            flattened.append(step_data)
    return flattened


def _search_sources(call: Dict[str, Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for source in call.get("sources") or []:
        data = _as_dict(source)
        url = _text(data.get("url"))
        if not url:
            continue
        results.append(
            {
                "title": _text(data.get("title")),
                "url": url,
                "snippet": _text(data.get("snippet")),
                "site_name": _text(data.get("site_name")) or None,
                "site_icon": _text(data.get("site_icon")) or None,
                "page_age": _text(data.get("published_at")) or None,
                "image_url": None,
            }
        )
    return results


def _server_tool_event(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """server_tool_use / server_tool_calls 里的一项。"""
    tool_name = _text(payload.get("name") or payload.get("tool") or payload.get("type"))
    action_payload = payload.get("action")
    if isinstance(action_payload, dict):
        input_data = action_payload
    else:
        raw_input = payload.get("input")
        input_data = _json_object(raw_input)
        if not input_data:
            function = _as_dict(payload.get("function"))
            input_data = _json_object(function.get("arguments") or payload.get("arguments"))
    action = _text(input_data.get("type") or input_data.get("action"))
    kind = _text(payload.get("kind"))
    sources = _search_sources(payload)

    # call_completed 只带 id/status/sources（或 page），不再重复 action/type
    if not action and sources:
        return [
            {
                "kind": "search_results",
                "id": _text(payload.get("id")),
                "results": sources,
            }
        ]
    page = _as_dict(payload.get("page"))
    if not action and (page.get("url") or payload.get("signature")):
        return [
            {
                "kind": "fetch_result",
                "id": _text(payload.get("id")),
                "url": _text(page.get("url")),
                "title": _text(page.get("title")) or None,
                "published_at": _text(page.get("published_at")) or None,
                "ok": True,
                "error": None,
            }
        ]

    if "read_url" in tool_name or action == "read_link":
        url = _text(input_data.get("url"))
        events: List[Dict[str, Any]] = [
            {
                "kind": "read_url_start",
                "id": _text(payload.get("id")),
                "url": url,
                "action": "read_link",
            }
        ]
        page = _as_dict(payload.get("page"))
        if page.get("url") or payload.get("signature"):
            events.append(
                {
                    "kind": "fetch_result",
                    "id": _text(payload.get("id")),
                    "url": _text(page.get("url")) or url,
                    "title": _text(page.get("title")) or None,
                    "published_at": _text(page.get("published_at")) or None,
                    "ok": True,
                    "error": None,
                }
            )
        return events

    # 深度思考搜索里的打开网页 / 页内查找，仍属于 deepseek_web_search，
    # 必须在通用搜索分支之前判断，否则会被误报成一次空查询搜索。
    url = _text(input_data.get("url"))
    if action in ("open_page", "find_in_page") and url:
        return [
            {
                "kind": "read_url_start",
                "id": _text(payload.get("id")),
                "url": url,
                "action": action,
                "pattern": _text(input_data.get("pattern")) or None,
            }
        ]

    queries = input_data.get("queries")
    if action == "search" or isinstance(queries, list) or "web_search" in tool_name:
        normalized_queries = [
            _text(item) for item in (queries or []) if _text(item)
        ]
        if not normalized_queries:
            single = _text(input_data.get("query"))
            normalized_queries = [single] if single else []
        events = [
            {
                "kind": "search_start",
                "id": _text(payload.get("id")),
                "queries": normalized_queries,
                "image": kind in ("image_search", "deep_image_search"),
                "deep": kind in ("deep_search", "search_while_thinking"),
            }
        ]
        sources = _search_sources(payload)
        if sources:
            events.append(
                {
                    "kind": "search_results",
                    "id": _text(payload.get("id")),
                    "results": sources,
                }
            )
        return events

    return []


def _citation_event(payload: Any) -> Optional[Dict[str, Any]]:
    data = _as_dict(payload)
    # Chat Completions 的引用是 {"type":"url_citation","url_citation":{...}}
    if isinstance(data.get("url_citation"), dict):
        data = _as_dict(data.get("url_citation"))
    url = _text(data.get("url"))
    if not url:
        return None
    return {
        "kind": "citation",
        "url": url,
        "title": _text(data.get("title")) or None,
        "cited_text": _text(data.get("cited_text")) or None,
    }


def anthropic_block_events(block: Any) -> List[Dict[str, Any]]:
    """Messages 协议 content_block_start 的内容。"""
    data = _as_dict(block)
    block_type = _text(data.get("type"))

    if block_type == "server_tool_use":
        return _server_tool_event(data)

    if block_type == "web_search_tool_result":
        results = [
            public
            for public in (
                _public_search_result(item) for item in (data.get("content") or [])
            )
            if public
        ]
        return [
            {
                "kind": "search_results",
                "id": _text(data.get("tool_use_id")),
                "results": results,
            }
        ]

    if block_type == "web_fetch_tool_result":
        content = _as_dict(data.get("content"))
        if content.get("type") == "web_fetch_tool_result_error":
            return [
                {
                    "kind": "fetch_result",
                    "id": _text(data.get("tool_use_id")),
                    "url": "",
                    "title": None,
                    "ok": False,
                    "error": _text(content.get("error_code") or "unavailable"),
                }
            ]
        if content.get("type") != "web_fetch_result":
            return []
        document = _as_dict(content.get("content"))
        return [
            {
                "kind": "fetch_result",
                "id": _text(data.get("tool_use_id")),
                "url": _text(content.get("url")),
                "title": _text(document.get("title")) or None,
                "published_at": _text(content.get("published_at")) or None,
                "ok": True,
                "error": None,
            }
        ]

    return []


def anthropic_delta_events(delta: Any) -> List[Dict[str, Any]]:
    data = _as_dict(delta)
    if data.get("type") == "citations_delta":
        event = _citation_event(data.get("citation"))
        return [event] if event else []
    return []


def openai_message_events(
    message: Any,
    *,
    include_server_tool_calls: bool = True,
) -> List[Dict[str, Any]]:
    """Chat Completions 的 message / delta 对象。"""
    data = _as_dict(message)
    events: List[Dict[str, Any]] = []

    if include_server_tool_calls:
        for call in _flatten_server_tool_calls(data.get("server_tool_calls")):
            events.extend(_server_tool_event(call))

    for annotation in data.get("annotations") or []:
        event = _citation_event(annotation)
        if event:
            events.append(event)

    refusal = _text(data.get("refusal"))
    if refusal:
        events.append({"kind": "refusal", "message": refusal})
    return events


def openai_server_tool_event(payload: Any) -> List[Dict[str, Any]]:
    """Chat Completions 流式 chunk 上的 choice.server_tool_event。"""
    data = _as_dict(payload)
    call = data.get("call") or data.get("result")
    if isinstance(call, dict):
        return _server_tool_event(call)
    return []


def history_blocks_from_anthropic(blocks: Iterable[Any]) -> List[Dict[str, Any]]:
    """只保留多轮需要回传的阅读链接块（含 signature）。"""
    kept: List[Dict[str, Any]] = []
    kept_ids: set[str] = set()
    for raw in blocks:
        block = _as_dict(raw)
        block_type = _text(block.get("type"))
        if block_type == "web_fetch_tool_result" and block.get("kind") == "read_link":
            if not _text(block.get("signature")):
                continue
            kept.append(block)
            kept_ids.add(_text(block.get("tool_use_id")))
            continue
        if block_type == "server_tool_use" and block.get("kind") == "read_link":
            kept.append(block)
    if not kept:
        return []
    # 结果块在前、调用块在后也能被上游接受；这里仅保留调用 + 带签名的结果。
    return kept


def history_payload_from_openai(
    server_tool_calls: Iterable[Any],
) -> Dict[str, Any]:
    calls = [_as_dict(item) for item in server_tool_calls or [] if _as_dict(item)]
    return {"server_tool_calls": calls} if calls else {}


def responses_item_events(item: Any) -> List[Dict[str, Any]]:
    """Responses API 的 output item / 流式 output_item 事件。"""
    data = _as_dict(item)
    item_type = _text(data.get("type"))
    events: List[Dict[str, Any]] = []

    if item_type in ("web_search_call", "deepseek_web_search", "web_search"):
        action = _text(data.get("action"))
        queries = data.get("queries") or data.get("query")
        url = _text(data.get("url"))
        if url:
            events.append(
                {
                    "kind": "read_url_start",
                    "id": _text(data.get("id")),
                    "url": url,
                    "action": action or "open_page",
                }
            )
        else:
            normalized = (
                [_text(value) for value in queries if _text(value)]
                if isinstance(queries, list)
                else [_text(queries)] if _text(queries) else []
            )
            events.append(
                {
                    "kind": "search_start",
                    "id": _text(data.get("id")),
                    "queries": normalized,
                    "image": False,
                    "deep": action in ("deep_search", "search_while_thinking"),
                }
            )
        return events

    if item_type == "message":
        for content in data.get("content") or []:
            block = _as_dict(content)
            for annotation in block.get("annotations") or []:
                event = _citation_event(annotation)
                if event:
                    events.append(event)
    return events

