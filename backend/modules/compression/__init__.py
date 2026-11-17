"""上下文压缩的公开入口；四阶段流水线见 ``engine``。"""

from backend.modules.compression.engine import (
    COMPRESSION_NOTE,
    CompactionResult,
    CompressionEngine,
    build_engine,
)
from backend.modules.compression.marker import elide, elide_middle
from backend.modules.compression.model_meta import (
    DEFAULT_CONTEXT_LENGTH,
    ContextResolution,
    get_resolver,
)
from backend.modules.compression.settings import CompactionSettings
from backend.modules.compression.summarizer import (
    FailureClass,
    SummaryOutcome,
    Summarizer,
    deterministic_summary,
)
from backend.modules.compression.tokens import (
    estimate_messages_tokens,
    estimate_request_tokens,
    estimate_tokens,
    forget_message_token_cache,
)

__all__ = [
    "COMPRESSION_NOTE",
    "CompactionResult",
    "CompactionSettings",
    "CompressionEngine",
    "ContextResolution",
    "DEFAULT_CONTEXT_LENGTH",
    "FailureClass",
    "Summarizer",
    "SummaryOutcome",
    "build_engine",
    "deterministic_summary",
    "elide",
    "elide_middle",
    "estimate_messages_tokens",
    "estimate_request_tokens",
    "estimate_tokens",
    "forget_message_token_cache",
    "get_resolver",
]
