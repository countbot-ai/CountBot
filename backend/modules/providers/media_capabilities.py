"""模型图片输入能力解析。

配置优先级最高；未显式配置时按模型名做保守判断。未知模型默认不发送图片，
继续沿用「工作区路径 + 图片技能」的旧链路，避免向纯文本模型发出必然失败的请求。
"""

from __future__ import annotations

import re
from typing import Optional

# 主流多模态模型命名。匹配范围故意放宽，显式配置仍然可以覆盖误判。
_VISION_MODEL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"gpt-4o",
        r"gpt-4\.1",
        r"gpt-4-turbo",
        r"gpt-5",
        r"(^|[-_/])o[134]($|[-_/])",
        r"claude-(3|4)",
        r"claude-(sonnet|opus|haiku)",
        r"gemini",
        r"glm-4(?:\.\d)?v",
        r"glm-4v",
        r"qwen[^/]*vl",
        r"qwen[^/]*omni",
        r"doubao[^/]*vision",
        r"doubao[^/]*-v",
        r"internvl",
        r"llava",
        r"pixtral",
        r"mistral-small-3",
        r"grok[^/]*vision",
        r"grok-4",
        r"step-1v",
        r"yi-vision",
        r"deepseek[^/]*vl",
        r"deepseek[^/]*v4",
        r"kimi[^/]*vl",
        r"minimax[^/]*vl",
        r"hunyuan[^/]*vision",
        r"ernie[^/]*vl",
        r"vision",
        r"multimodal",
        r"omni",
    )
)

# 明确只有文本输入的常见模型，避免 “vision” 一类宽泛规则误判。
_TEXT_ONLY_MODEL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"deepseek-(chat|reasoner|coder)",
        r"kimi-k2",
        r"llama-3",
        r"mixtral",
        r"command-r",
        r"hunyuan-lite",
        r"ernie-4\.0",
        r"baichuan",
        r"yi-large",
        r"glm-4\.7-flash",
        r"glm-5",
        r"qwen-(max|plus|turbo)",
    )
)


def resolve_supports_image(
    *,
    provider_id: Optional[str] = None,
    model: Optional[str] = None,
    override: Optional[bool] = None,
) -> bool:
    """解析当前执行模型是否支持图片输入。

    Args:
        provider_id: Provider ID，用于日志与后续扩展。
        model: 实际执行模型名。
        override: 配置中的显式开关；True/False 优先于自动判断。
    """
    if isinstance(override, bool):
        return override

    model_name = str(model or "").strip().lower()
    if not model_name:
        return False

    if any(pattern.search(model_name) for pattern in _TEXT_ONLY_MODEL_PATTERNS):
        return False
    if any(pattern.search(model_name) for pattern in _VISION_MODEL_PATTERNS):
        return True

    # 未知模型保持旧行为：路径 + 图片技能。用户可在模型配置里显式打开。
    return False
