"""工具调用指纹与重复调用拦截文案。"""

import json
import re
from typing import Any, Optional


def normalize_exec_command(command: str) -> str:
    """归一化命令指纹，只剥离不改变语义的包装。"""
    text = command or ""
    # 前导 cd <dir> &&
    text = re.sub(r"^\s*(?:cd\s+\S+\s*&&\s*)+", "", text)
    # 前导 timeout N
    text = re.sub(r"^\s*timeout\s+\d+\s+", "", text)
    # 输出切片管道 | head/tail/wc
    text = re.sub(r"\|\s*(?:head|tail|wc)(?:\s+[^|]*)?", "", text)
    # 静默重定向 2>/dev/null、2>&1
    text = re.sub(r"\d*>+\s*/dev/null", "", text)
    text = re.sub(r"\d*>&\d+", "", text)
    return " ".join(text.split())


def tool_signature(tool_name: str, tool_args: Any) -> str:
    """生成「同名 + 归一化参数」的调用指纹，用于识别重复调用。"""
    if tool_name == "exec" and isinstance(tool_args, dict):
        normalized_args = dict(tool_args)
        command = normalized_args.get("command")
        if isinstance(command, str):
            normalized_args["command"] = normalize_exec_command(command)
        tool_args = normalized_args
    try:
        normalized = json.dumps(
            tool_args, sort_keys=True, ensure_ascii=False, default=str
        )
    except Exception:
        normalized = str(tool_args)
    return f"{tool_name}:{normalized}"


def build_repeat_notice(tool_name: str, attempt: int, cached: Optional[str]) -> str:
    """重复调用被熔断时返回给模型的说明（含上次结果摘要）。"""
    lines = [
        f"[重复调用拦截] 这是本次请求里第 {attempt} 次完全相同的 `{tool_name}` 调用，"
        "已跳过执行——同样的输入不会得到不同的输出。",
        "请换参数、换工具，或直接基于下面的上次结果继续，不要再重复这条调用。",
    ]
    if cached:
        lines.append("上次结果（已截断）：\n" + cached)
    else:
        lines.append("上次调用没有留下可用结果，请换一种方式重试。")
    return "\n".join(lines)
