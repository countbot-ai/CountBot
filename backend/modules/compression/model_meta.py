"""模型上下文窗口解析与目录拉取：按用户配置、缓存、上游、家族表、默认值依次降级。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

# 上游 /models 条目中表示「输入窗口」的字段别名
CONTEXT_LENGTH_KEYS: Tuple[str, ...] = (
    "context_length",
    "context_window",
    "context_size",
    "max_context_length",
    "max_position_embeddings",
    "max_model_len",
    "max_input_tokens",
    "max_sequence_length",
    "max_seq_len",
    "n_ctx_train",
    "n_ctx",
    "ctx_size",
)

# 输出上限字段：不能当窗口用，仅在上面的别名全部缺失时兜底
MAX_OUTPUT_KEYS: Tuple[str, ...] = ("max_completion_tokens", "max_output_tokens", "max_tokens")

# 合理窗口区间：低于下限说明拿到的是输出上限或截断值，高于上限说明字段语义有误
MIN_REASONABLE_CONTEXT = 1_024
MAX_REASONABLE_CONTEXT = 10_000_000

# 检测失败时的兜底窗口。取值偏保守，优先早压缩而非超窗被上游拒绝。
DEFAULT_CONTEXT_LENGTH = 128_000

# 低于该窗口的模型不具备持续会话所需的可用空间，用于配置校验提示
MINIMUM_CONTEXT_LENGTH = 16_000

# 家族兜底表：仅在既无用户配置、又无法从上游获取窗口时使用。
#
# 键按最长优先做子串匹配（具体型号须严格长于同族兜底键）。数值只用于量级判断：
# 取小会偏早压缩（安全），取大会在真实上限处被上游拒绝；无法确定代际时按该家族
# **较早代际**取值。
#
# 新增型号无需改表：代际推断（见 ``infer_context_by_generation``）优先识别型号中的
# 代际标识，未命中才落回家族键。
FAMILY_CONTEXT_LENGTHS: Mapping[str, int] = {
    # 家族默认值，取该家族近几代的保守窗口
    "claude": 200_000,
    "gemini": 1_048_576,
    "gemma": 131_072,
    "deepseek": 128_000,
    "llama": 131_072,
    "qwen": 131_072,
    "glm": 131_072,
    "kimi": 262_144,
    "moonshot": 262_144,
    "grok": 131_072,
    "minimax": 204_800,
    "mistral": 131_072,
    "yi": 32_768,
    "ernie": 128_000,
    "doubao": 128_000,
    "hunyuan": 262_144,
    "spark": 32_768,
    "gpt": 128_000,
    "o1": 200_000,
    "o3": 200_000,
    "o4": 200_000,
    "command": 128_000,
    "jamba": 262_144,
    "phi": 131_072,
    "nemotron": 131_072,
}

# 代际推断规则：(家族匹配, 代际匹配, 窗口)
#
# 代际标识是窗口的主要决定因素（同一家族的新代际窗口通常扩大数倍），
# 因此先按代际判定，再落回家族默认值。键按列表顺序匹配，越靠前优先级越高。
_GENERATION_RULES: List[Tuple[str, str, int]] = [
    # 百万级窗口的代际
    ("claude", r"(?:opus|sonnet|haiku)-[4-9]", 1_000_000),
    ("gemini", r"1\.5", 2_000_000),
    ("gemini", r"[23]\.\d", 1_048_576),
    # 型号内的代际后缀（如 gpt-5.2-terra）：只取到字母后缀，不吞后续连字符
    ("gpt", r"gpt-\d+\.\d+(?:-[a-z]+)?", 1_048_576),
    ("gpt", r"gpt-[5-9](?:\.\d+)?", 400_000),
    ("gpt", r"gpt-4\.1", 1_047_576),
    ("grok", r"grok-[3-9]", 256_000),
    ("deepseek", r"v[3-9]", 128_000),
    ("qwen", r"qwen[23]?\.?\d*-?(?:max|plus)", 131_072),
    ("glm", r"glm-[4-9]", 131_072),
    ("kimi", r"k[2-9]", 262_144),
    ("minimax", r"m[2-9]", 204_800),
]

_GENERATION_COMPILED: List[Tuple[str, "re.Pattern[str]", int]] = [
    (family, re.compile(pattern, re.IGNORECASE), window)
    for family, pattern, window in _GENERATION_RULES
]


def infer_context_by_generation(model: str) -> Optional[Tuple[str, int]]:
    """按型号中的代际标识推断窗口，返回 ``(命中规则, 窗口)``。

    型号命名普遍把代际写在名字里（``claude-sonnet-4``、``gpt-5.2-terra``），
    因此先识别代际再落家族默认值，比纯家族表更贴近实际窗口，且新代际无需改表。
    """
    name = (model or "").strip().lower().rsplit("/", 1)[-1]
    if not name:
        return None
    for family, pattern, window in _GENERATION_COMPILED:
        if family not in name:
            continue
        match = pattern.search(name)
        if match:
            return f"{family}:{match.group(0)}", window
    return None


def longest_family_match(model: str) -> Optional[Tuple[str, int]]:
    """窗口兜底解析：先按代际推断，再按家族表最长优先匹配。

    最长优先保证具体型号（如 ``gpt-4.1-mini``）胜出同族兜底键（``gpt``）；
    比较前对两侧做版本分隔符归一化。
    """
    name = (model or "").strip().lower().rsplit("/", 1)[-1]
    if not name:
        return None

    generation = infer_context_by_generation(name)
    if generation is not None:
        return generation

    normalized_name = _normalize_version_separators(name)
    for key, value in sorted(FAMILY_CONTEXT_LENGTHS.items(), key=lambda item: len(item[0]), reverse=True):
        normalized_key = _normalize_version_separators(key.lower())
        if normalized_key in normalized_name:
            return key, value
    return None


def _coerce_length(value: Any) -> Optional[int]:
    """把上游字段值规整为合理区间内的整数，越界或非数值返回 None。"""
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", "")
        result = int(value)
    except (TypeError, ValueError):
        return None
    if MIN_REASONABLE_CONTEXT <= result <= MAX_REASONABLE_CONTEXT:
        return result
    return None


def extract_context_length(payload: Any) -> Optional[int]:
    """从上游模型条目中提取上下文窗口。

    先按窗口别名在**顶层**查找；全部缺失时才退回 ``max_tokens`` 系列
    （Anthropic 载荷同时带 ``max_input_tokens`` 与 ``max_tokens``，后者是输出上限）。
    """
    if not isinstance(payload, dict):
        return None
    for key in CONTEXT_LENGTH_KEYS:
        if key in payload:
            coerced = _coerce_length(payload.get(key))
            if coerced is not None:
                return coerced
    for key in MAX_OUTPUT_KEYS:
        if key in payload:
            coerced = _coerce_length(payload.get(key))
            if coerced is not None:
                return coerced
    return None


def _normalize_version_separators(text: str) -> str:
    """把版本号写法归一化，使 ``z-ai-glm-5-3`` 能命中 ``glm-5.3`` 这类键。"""
    result = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in "-_" and index + 1 < len(text) and text[index + 1].isdigit():
            # 中间件常用连字符替代点号：把「字母-数字」间的连字符视为版本点号
            if index > 0 and (text[index - 1].isalpha() or text[index - 1].isdigit()):
                result.append(".")
                index += 1
                continue
        result.append(char)
        index += 1
    return "".join(result)


@dataclass
class ContextResolution:
    """一次窗口解析的结果，含来源，便于界面展示与问题定位。"""

    context_length: int
    source: str
    # 是否需要提示用户补充配置（走默认兜底时为 True）
    degraded: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "context_length": self.context_length,
            "source": self.source,
            "degraded": self.degraded,
        }


class ContextWindowResolver:
    """多级窗口解析器。

    解析顺序（前者优先）：
    1. 用户显式配置的窗口
    2. 上游 /models 拉取后写入配置的窗口
    3. 运行时探测缓存（同一进程内，短 TTL，避免重复探测）
    4. 家族表兜底
    5. 默认值（标记 degraded，供上层提示补充配置）
    """

    # 探测缓存 TTL：上游窗口极少变化，缓存一小时即可避免每轮重复解析
    PROBE_TTL_SECONDS = 3_600.0

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, str], Tuple[int, float]] = {}
        self._warned: set = set()
        self._configured: Dict[str, int] = {}

    def register_configured(self, entries: Mapping[str, int]) -> int:
        """登记用户在模型配置中填写的窗口，返回登记数量。

        配置是最高优先级来源：用户在设置页为模型显式填写窗口时，其意图优先于
        任何探测或家族兜底值。键为模型 id，大小写不敏感。
        """
        count = 0
        for key, value in (entries or {}).items():
            if isinstance(value, int) and value >= MIN_REASONABLE_CONTEXT:
                self._configured[str(key).strip().lower()] = value
                count += 1
        return count

    def configured_window(self, model: Optional[str]) -> Optional[int]:
        """取用户为该模型配置的窗口，未配置返回 None。

        先精确匹配，再做最长子串匹配，使带供应商前缀的 id（``openai/gpt-4o``）
        也能命中用户填写的 ``gpt-4o``。
        """
        name = (model or "").strip().lower()
        if not name:
            return None
        exact = self._configured.get(name)
        if exact is not None:
            return exact
        matches = [
            (key, value) for key, value in self._configured.items() if key and key in name
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: len(item[0]), reverse=True)
        return matches[0][1]

    def resolve(
        self,
        model: Optional[str],
        *,
        configured: Optional[int] = None,
        api_base: str = "",
    ) -> ContextResolution:
        """解析模型的上下文窗口。"""
        if isinstance(configured, int) and configured > 0:
            return ContextResolution(configured, "config")

        name = (model or "").strip()
        if not name:
            return ContextResolution(DEFAULT_CONTEXT_LENGTH, "default", degraded=True)

        # 用户在模型配置中填写的窗口优先于探测与家族兜底
        declared = self.configured_window(name)
        if declared is not None:
            return ContextResolution(declared, "model_config")

        cached = self._cache_get(name, api_base)
        if cached is not None:
            return ContextResolution(cached, "cache")

        family = longest_family_match(name)
        if family is not None:
            return ContextResolution(family[1], f"family:{family[0]}")

        return ContextResolution(DEFAULT_CONTEXT_LENGTH, "default", degraded=True)

    def remember(self, model: str, api_base: str, context_length: int) -> None:
        """记入探测缓存（上游目录拉取到窗口后调用）。"""
        if not model or context_length <= 0:
            return
        self._cache[(model.strip().lower(), api_base or "")] = (
            int(context_length),
            time.monotonic(),
        )

    def _cache_get(self, model: str, api_base: str) -> Optional[int]:
        entry = self._cache.get((model.strip().lower(), api_base or ""))
        if entry is None:
            return None
        value, stamped_at = entry
        if (time.monotonic() - stamped_at) >= self.PROBE_TTL_SECONDS:
            self._cache.pop((model.strip().lower(), api_base or ""), None)
            return None
        return value

    def degraded_warning(self, model: str, api_base: str, resolved: ContextResolution) -> Optional[str]:
        """窗口走默认兜底时的去重告警文案，非兜底返回 None。

        窗口过大会在真实上限处被上游拒绝，过小会过早压缩，两种情况都需要显式提示。
        """
        if not resolved.degraded:
            return None
        key = (model, api_base or "")
        if key in self._warned:
            return None
        self._warned.add(key)
        return (
            f"未能确定模型 {model!r} 的上下文窗口，按 {resolved.context_length:,} tokens 处理。"
            "可在供应商的模型条目中填写 context_window 覆盖。"
        )


def load_configured_windows(config: Any) -> Dict[str, int]:
    """从应用配置中收集用户填写的模型窗口。

    模型窗口由用户在设置页为每个模型条目填写（``ModelEntry.context_window``），
    这是比任何探测或家族兜底都可靠的来源，因此优先读取。
    """
    entries: Dict[str, int] = {}
    providers = getattr(config, "providers", None)
    if not isinstance(providers, Mapping):
        return entries
    for provider in providers.values():
        models = getattr(provider, "models", None)
        if not isinstance(models, (list, tuple)):
            continue
        for model in models:
            model_id = getattr(model, "id", None)
            window = getattr(model, "context_window", None)
            if isinstance(window, int) and window >= MIN_REASONABLE_CONTEXT and model_id:
                entries[str(model_id)] = window
    return entries


def sync_configured_windows(config: Any) -> int:
    """把配置中的模型窗口同步到解析器，返回登记数量。"""
    entries = load_configured_windows(config)
    if entries:
        _resolver.register_configured(entries)
    return len(entries)


_resolver = ContextWindowResolver()


def get_resolver() -> ContextWindowResolver:
    """进程级解析器（探测缓存跨会话共享）。"""
    return _resolver


def parse_models_payload(payload: Any) -> List[Dict[str, Any]]:
    """解析上游 /models 响应为统一条目列表。

    兼容 ``{"data": [...]}``、``{"models": [...]}`` 与直接数组三种形态；
    非字符串 id 的条目跳过而不报错。
    """
    raw_items: List[Any] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            raw_items = data
        elif isinstance(payload.get("models"), list):
            raw_items = payload["models"]
    elif isinstance(payload, list):
        raw_items = payload

    seen: set = set()
    result: List[Dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, str):
            model_id = item.strip()
            entry: Dict[str, Any] = {}
        elif isinstance(item, dict):
            model_id = str(
                item.get("id") or item.get("name") or item.get("model") or ""
            ).strip()
            entry = item
        else:
            continue
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        display_name = str(
            entry.get("display_name") or entry.get("displayName") or ""
        ).strip() or None
        result.append(
            {
                "id": model_id,
                "display_name": display_name,
                "context_window": extract_context_length(entry),
            }
        )
    return result
