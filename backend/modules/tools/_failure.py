"""失败隔离协议模块（Failure Isolation Protocol）

核心原则（源自 Armin Ronacher《Agent Design Is Still Hard》）：
- 失败完整细节给人看（logger / 审计落盘）。
- 失败一句话给模型看：``Error: <事实>. <原因>. Next: <下一步建议>.``

本模块对外暴露三个符号：
- ``format_failure``：把错误格式化为模型可见的一句话模板；
- ``RetryableToolError``：可重试错误（网络/超时/5xx 类），由上层（主循环）捕获后重试；
- ``is_retryable``：判断一个异常是否属于可重试类别。

仅依赖标准库，避免引入循环依赖。
"""

from typing import Tuple

_SENTENCE_ENDINGS: Tuple[str, ...] = (".", "!", "?", "。", "！", "？")


def single_line(text: str, max_len: int = 300) -> str:
    """把文本压成单行并截断，避免换行/超长破坏模型可见的一句话模板。"""
    line = " ".join(str(text).split())
    if len(line) > max_len:
        line = line[:max_len] + "..."
    return line


def _ensure_sentence_ending(text: str) -> str:
    """确保文本以句末标点结尾（避免拼接出 ``..``）。"""
    text = text.rstrip()
    if text and not text.endswith(_SENTENCE_ENDINGS):
        return text + "."
    return text


def format_failure(
    *,
    kind: str,
    summary: str,
    next: str,
    detail: str = "",
) -> str:
    """把错误格式化为模型可见的一句话模板。

    模板：``Error: <一句话事实>. <原因>. Next: <下一步建议>.``

    Args:
        kind: 错误类别（execution_error / validation_error / permission_error ...），
            仅供日志分类，不进入模型可见文案。
        summary: 一句话事实（可含原因，例如 ``File not found: foo.py``，
            若结尾已有句号则原样保留）。
        next: 给模型的下一步建议；为空字符串时省略 ``Next:`` 段。
        detail: 完整细节，仅供 logger / 审计使用，**不**进入返回值。

    Returns:
        str: 以 ``Error: `` 开头、可含 ``Next: `` 的模型可见文案。
    """
    parts = ["Error:", _ensure_sentence_ending(summary)]
    if next:
        parts.append("Next: " + _ensure_sentence_ending(str(next)))
    return " ".join(parts)


class RetryableToolError(Exception):
    """可重试工具错误。

    由 ``registry.execute`` 在 ``raise_on_retryable=True`` 时对网络/超时/5xx
    类异常重新抛出，供主循环的 ``for attempt in range(max_retries)`` 捕获后重试。

    ``__str__`` 返回**不含** ``Error:`` 前缀的模型可见单句（summary + Next），
    避免主循环重试耗尽后的最终文案出现 ``Error: Error: ...`` 前缀重复。
    """

    def __init__(
        self,
        *,
        tool_name: str,
        summary: str,
        next: str = "retry the operation",
        detail: str = "",
    ) -> None:
        super().__init__(tool_name, summary)
        self.tool_name = tool_name
        self.summary = summary
        self.next = next
        self.detail = detail

    def __str__(self) -> str:
        parts = [_ensure_sentence_ending(self.summary)]
        if self.next:
            parts.append("Next: " + _ensure_sentence_ending(str(self.next)))
        return " ".join(parts)

    def to_model_message(self) -> str:
        """返回模型可见完整文案（带 ``Error:`` 前缀）。"""
        return format_failure(
            kind="execution_error",
            summary=self.summary,
            next=self.next,
            detail=self.detail,
        )


def _is_httpx_request_error(exc: BaseException) -> bool:
    """判断是否为 httpx 网络请求异常（惰性 import，避免模块级硬依赖）。"""
    try:
        import httpx
    except Exception:
        return False
    return isinstance(exc, httpx.RequestError)


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否属于可重试类别（网络 / 超时 / 连接类）。

    不可重试的典型错误：参数错误、权限错误、文件不存在等业务类失败——
    重试不会改变结果，应直接以失败文案返回给模型。
    """
    if isinstance(exc, RetryableToolError):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if _is_httpx_request_error(exc):
        return True
    return False
