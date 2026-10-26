"""切点安全性与边界对齐：避免拆散工具调用及其结果。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

# 角色交替判定时需要跳过的角色：部分严格模板不计入可见序列
_TEMPLATE_EXEMPT_ROLES = frozenset({"system", "tool"})


def role_of(message: Any) -> str:
    """消息角色，非字典返回空串。"""
    if not isinstance(message, dict):
        return ""
    return str(message.get("role") or "")


def is_tool_result(message: Any) -> bool:
    return role_of(message) == "tool"


def has_tool_calls(message: Any) -> bool:
    return isinstance(message, dict) and bool(message.get("tool_calls"))


def template_visible_role(message: Any) -> Optional[str]:
    """模板可见角色；豁免角色返回 None，表示不参与交替计算。"""
    role = role_of(message)
    if not role or role in _TEMPLATE_EXEMPT_ROLES:
        return None
    return role


def last_template_visible_role(messages: Sequence[Any]) -> Optional[str]:
    """序列中最后一个模板可见角色。"""
    for message in reversed(messages):
        role = template_visible_role(message)
        if role is not None:
            return role
    return None


def is_safe_cut_point(messages: Sequence[Dict[str, Any]], index: int) -> bool:
    """判断在 ``index`` 处切分是否安全。

    安全意味着保留段 ``messages[index:]`` 不以工具结果开头，且不与前一条消息的
    ``tool_calls`` 拆散。
    """
    if index <= 0 or index >= len(messages):
        return True
    head = messages[index]
    if is_tool_result(head):
        return False
    previous = messages[index - 1]
    if has_tool_calls(previous) and is_tool_result(head):
        return False
    return True


def align_forward(messages: Sequence[Dict[str, Any]], index: int) -> int:
    """把切点向后推到最近的安全位置：跳过开头的孤儿工具结果。"""
    total = len(messages)
    cursor = max(0, index)
    while cursor < total and is_tool_result(messages[cursor]):
        cursor += 1
    return cursor


def align_backward(messages: Sequence[Dict[str, Any]], index: int) -> int:
    """把切点向前拉，避免把工具组切开（尾部孤儿结果会被丢弃）。"""
    if index <= 0 or index >= len(messages):
        return index
    check = index - 1
    while check >= 0 and is_tool_result(messages[check]):
        check -= 1
    # 落在发起调用的 assistant 上：切到它之前，使整组一起被摘要
    if check >= 0 and role_of(messages[check]) == "assistant" and has_tool_calls(messages[check]):
        return check
    return index


def turn_pair_end(messages: Sequence[Dict[str, Any]], user_index: int) -> int:
    """用户轮次的结束位置：其后的工具组与助手回复一并算作同一轮。"""
    total = len(messages)
    cursor = user_index + 1
    while cursor < total:
        role = role_of(messages[cursor])
        if role == "user":
            break
        cursor += 1
    return cursor


def call_id_variants(tool_call: Any) -> Set[str]:
    """工具调用可能被结果引用的全部 id 写法。

    不同上游分别使用 ``id`` 与 ``call_id``，部分网关还会加前缀，因此匹配时
    需要同时接受多种拼写，否则会把正常的调用对误判为孤儿。
    """
    if not isinstance(tool_call, dict):
        return set()
    variants: Set[str] = set()
    for key in ("id", "call_id", "tool_call_id"):
        value = tool_call.get(key)
        if isinstance(value, str) and value.strip():
            variants.add(value.strip())
    # 复合写法 ``call|item``：部分响应式上游把两个 id 拼在一起
    for value in list(variants):
        if "|" in value:
            variants.update(part.strip() for part in value.split("|") if part.strip())
    return variants


def classify_tool_pairs(
    messages: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """分类工具调用与结果的配对情况，供压缩后清理使用。

    Returns:
        ``result_call_ids`` 有对应 assistant 调用的结果 id 集合；
        ``orphaned_results`` 找不到调用的结果消息；
        ``missing_calls`` 找不到结果的工具调用。
    """
    declared: Set[str] = set()
    for message in messages:
        if role_of(message) != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            declared.update(call_id_variants(tool_call))

    answered: Set[str] = set()
    orphaned_results: List[Dict[str, Any]] = []
    for message in messages:
        if is_tool_result(message):
            identifiers = set()
            for key in ("tool_call_id", "call_id", "id"):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    identifiers.add(value.strip())
            if identifiers & declared:
                answered.update(identifiers)
            else:
                orphaned_results.append(message)

    missing_calls: List[tuple] = []
    for message in messages:
        if role_of(message) != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not (call_id_variants(tool_call) & answered):
                missing_calls.append((message, tool_call))

    return {
        "declared_ids": declared,
        "result_call_ids": answered,
        "orphaned_results": orphaned_results,
        "missing_calls": missing_calls,
    }


def sanitize_tool_pairs(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """清理压缩产生的孤儿工具调用与结果。

    孤儿结果直接删除；孤儿调用从 assistant 上剥离（不补桩，补桩在后续序列修复
    中会因 id 不一致被丢弃）。仍在执行中的最新一轮调用保留原样：压缩可能发生在
    执行器尚未追加结果之前。
    """
    report = classify_tool_pairs(messages)
    orphaned = report["orphaned_results"]
    if orphaned:
        orphaned_ids = {id(message) for message in orphaned}
        messages = [m for m in messages if id(m) not in orphaned_ids]

    if not report["missing_calls"]:
        return messages

    # 在途保护：最后一个非 tool 消息若是带调用的 assistant，其调用视为尚未返回
    in_flight_index = next(
        (i for i in range(len(messages) - 1, -1, -1) if role_of(messages[i]) != "tool"),
        -1,
    )
    in_flight = (
        messages[in_flight_index]
        if in_flight_index >= 0 and role_of(messages[in_flight_index]) == "assistant"
        else None
    )

    for message in messages:
        calls = message.get("tool_calls")
        if role_of(message) != "assistant" or message is in_flight or not calls:
            continue
        kept = [tc for tc in calls if call_id_variants(tc) & report["result_call_ids"]]
        if len(kept) == len(calls):
            continue
        if kept:
            message["tool_calls"] = kept
            continue
        message.pop("tool_calls", None)
        # 保留可见内容，避免出现空轮次被上游拒绝
        content = message.get("content")
        if not content or (isinstance(content, str) and not content.strip()):
            message["content"] = "(tool call removed)"
    return messages
