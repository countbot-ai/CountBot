"""记忆模块的公开入口。"""

from backend.modules.memory.models import Confidence, MemoryEntry, MemoryKind
from backend.modules.memory.policy import INJECT_TOKEN_BUDGET
from backend.modules.memory.service import MemoryDenied, MemoryService, RememberResult
from backend.modules.memory.source import UNKNOWN_SOURCE, resolve_source
from backend.modules.memory.storage import MemoryStorage, MigrationReport

# 兼容旧引用名：MemoryStore 即 MemoryService，保留以改动历史调用方与装配点
MemoryStore = MemoryService

__all__ = [
    "Confidence",
    "INJECT_TOKEN_BUDGET",
    "MemoryDenied",
    "MemoryEntry",
    "MemoryKind",
    "MemoryService",
    "MemoryStorage",
    "MemoryStore",
    "MigrationReport",
    "RememberResult",
    "UNKNOWN_SOURCE",
    "resolve_source",
]
