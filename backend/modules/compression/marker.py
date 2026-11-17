"""模型可见的截断标记：带逐实例计数，使复制可被识别。"""

from __future__ import annotations

import re

# 该文本会进入模型自己的工具调用参数，措辞必须不像模型会写出的内容：
# 非散文分隔符 + 明确的「非原文」声明 + 逐实例计数
_MARKER_PREFIX = "⟪COUNTBOT-CONTEXT-COMPRESSION:"
_MARKER_TEMPLATE = (
    _MARKER_PREFIX
    + " {omitted:,} of {total:,} chars omitted here by CountBot's context compressor. "
    "This is NOT part of the original tool call and must never be reproduced in new "
    "output — always write full, untruncated content.⟫"
)

# 标记内渲染出的省略/总数计数
_MARKER_COUNT_RE = r"\d[\d,]*"

# 完整首句形态，供渲染器与匹配测试使用
_MARKER_RE = re.compile(
    re.escape(_MARKER_TEMPLATE.split(". ", 1)[0] + ".")
    .replace(re.escape("{omitted:,}"), _MARKER_COUNT_RE)
    .replace(re.escape("{total:,}"), _MARKER_COUNT_RE)
)

# 被后续边界切断的标记可能不含固定首句，因此以「前缀 + 首个计数」即认定：
# 这样源码与文档中的裸前缀/模板仍可自由编辑
_MARKER_ARTIFACT_RE = re.compile(
    re.escape(_MARKER_PREFIX) + r"\s+" + _MARKER_COUNT_RE
)

# 其余模型可见的省略（轮次文本、摘要、技能正文、诊断）只铸造首句，
# 使同一匹配器可捕获来自任意渲染器的复制
_ELISION_MARKER_TEMPLATE = _MARKER_TEMPLATE.split(". ", 1)[0] + ".⟫"


def render_marker(omitted: int, total: int) -> str:
    """渲染不可模仿的省略标记，带逐实例字符计数。"""
    return _ELISION_MARKER_TEMPLATE.format(omitted=omitted, total=total)


def marker_max_length() -> int:
    """约 1 TB 以内任意文本对应的最宽标记长度。

    预算不足以同时容纳标记与正文的调用方应跳过该条目，而不是只输出一行标记。
    """
    return len(render_marker(omitted=10**12 - 1, total=10**12 - 1))


ELISION_MARKER_MAX_LEN = marker_max_length()


def elide(text: str, limit: int) -> str:
    """把 ``text`` 截到 ``limit`` 字符，用标记注明省略。

    ``text`` 已在限内时原样返回。否则结果为 ``头部 + 标记``，省略与总数计数准确，
    且不超过 ``limit``（按计数可取的最宽渲染预留）；``limit`` 连标记都容纳不下时
    只返回标记。
    """
    if len(text) <= limit:
        return text
    total = len(text)
    head_len = limit - len(render_marker(omitted=total, total=total))
    if head_len <= 0:
        return render_marker(omitted=total, total=total)
    kept = text[:head_len].rstrip()
    return kept + render_marker(omitted=total - len(kept), total=total)


def elide_middle(text: str, head: int, tail: int) -> str:
    """保留首 ``head`` 字符与末 ``tail`` 字符，省略中段。"""
    if len(text) <= head + tail:
        return text
    marker = render_marker(omitted=len(text) - head - tail, total=len(text))
    return text[:head] + marker + text[len(text) - tail:]


def strip_persistence_markers(messages) -> None:
    """就地移除消息上的持久化标记，保证压缩产物不带库内标记外流。"""
    if not isinstance(messages, list):
        return
    for message in messages:
        if isinstance(message, dict):
            message.pop("_db_persisted", None)
