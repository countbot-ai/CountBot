"""记忆的持久化层：``MEMORY.jsonl`` 为主存储，``MEMORY.md`` 为可读视图。"""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from loguru import logger

from backend.modules.memory.models import (
    Confidence,
    MemoryEntry,
    MemoryKind,
    utc_now,
)

try:  # 文件锁只在类 Unix 平台提供；缺失时退化为无锁，单进程部署仍可用
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None


# 视图行：- [key] value | YYYY-MM-DD | source
_VIEW_LINE_RE = re.compile(
    r"^-\s*\[(?P<key>[^\]]+)\]\s*(?P<value>.*?)\s*\|\s*(?P<date>\S+)\s*\|\s*(?P<source>.+?)\s*$"
)
# 旧行式格式：YYYY-MM-DD|source|content
_LEGACY_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*(?P<source>[^|]+?)\s*\|\s*(?P<value>.+)$"
)
_SECTION_RE = re.compile(r"^##\s+(?P<name>pinned|recent|archived)\s*$", re.IGNORECASE)
_SECTION_KINDS = {
    "pinned": MemoryKind.PINNED,
    "recent": MemoryKind.RECENT,
    "archived": MemoryKind.ARCHIVED,
}
_VIEW_HEADER = "# Memory\n"
_SECTION_ORDER = (
    (MemoryKind.PINNED, "pinned"),
    (MemoryKind.RECENT, "recent"),
    (MemoryKind.ARCHIVED, "archived"),
)
# 冷存档在视图中只展示最近一批：随使用时长增长，全量渲染会使文件失去可读性，且人工
# 编辑的对象是断言层。
_ARCHIVE_VIEW_LIMIT = 20


@dataclass
class MigrationReport:
    """一次旧格式迁移的结果。

    ``status`` 取值：``migrated``（写入了一批条目）、``up_to_date``（旧内容已在存储中）、
    ``nothing_to_do``（没有旧文件或无可解析条目）、``failed``（读写失败）。
    不合并成布尔值，是因为「本来就没事」和「迁移失败」需要不同的处置。
    """

    memory_dir: Path
    status: str
    imported: int
    total: int
    backup: Optional[Path] = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status != "failed"


class MemoryStorage:
    """记忆文件的读写与格式迁移。"""

    def __init__(self, memory_dir: Path):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.memory_dir / "MEMORY.jsonl"
        self.markdown_path = self.memory_dir / "MEMORY.md"
        self.lock_path = self.memory_dir / ".memory.lock"

    # ------------------------------------------------------------------ 锁

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """对独立的锁文件加排他锁。

        锁与数据文件分离，数据文件才能用临时文件 + rename 原子替换。
        """
        if fcntl is None:
            yield
            return
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        raw_fd = os.open(self.lock_path, flags, 0o600)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(raw_fd, 0o600)
            handle = os.fdopen(raw_fd, "r+")
        except Exception:
            os.close(raw_fd)
            raise
        with handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def transaction(self) -> Iterator[List[MemoryEntry]]:
        """在锁内读入全部条目，退出时整体落盘。

        调用方获得可直接修改的列表；正常退出即持久化，异常退出则放弃本次改动，不留下
        半写状态。
        """
        with self._file_lock():
            entries = self._load_unlocked()
            yield entries
            self._save_unlocked(entries)

    # ------------------------------------------------------------------ 读

    def load(self) -> List[MemoryEntry]:
        if fcntl is None:
            return self._load_unlocked()
        with self._file_lock():
            return self._load_unlocked()

    def read_markdown(self) -> str:
        """返回由当前数据渲染的视图。

        视图是派生数据：直接读文件会读到上次落盘时的版本，与之后新增或降级的条目
        不一致。因此每次按数据重算，并在文件内容不同步时顺手校正文件。
        """
        rendered = self._render_markdown(self.load())
        try:
            current: Optional[str] = self.markdown_path.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current != rendered:
            self._atomic_write(self.markdown_path, rendered)
        return rendered

    def _load_unlocked(self) -> List[MemoryEntry]:
        # 空文件不算「可用的新存储」：零字节的 MEMORY.jsonl 一旦存在就永久挡住旧格式
        # 迁移，旧记忆会静默消失
        if self.jsonl_path.exists() and self.jsonl_path.stat().st_size > 0:
            entries = self._read_jsonl()
            if entries is not None:
                return entries
            logger.warning(f"记忆文件不可解析，转用 markdown 迁移：{self.jsonl_path}")
        return self._migrate_from_markdown()

    def _read_jsonl(self) -> Optional[List[MemoryEntry]]:
        """读取 JSONL；存在但整行不可解析时返回 None，交由迁移逻辑处理。

        单行损坏只跳过该行，不使整份记忆失效。
        """
        entries: List[MemoryEntry] = []
        broken = 0
        try:
            content = self.jsonl_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"读取记忆文件失败：{exc}")
            return None
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(MemoryEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                broken += 1
        if broken:
            logger.warning(f"跳过 {broken} 行不可解析的记忆数据：{self.jsonl_path}")
        return entries if entries or not broken else None

    def _migrate_from_markdown(self) -> List[MemoryEntry]:
        """把旧版行式 MEMORY.md 迁移为条目。

        旧格式无 key，也无法区分可信度，且多由上下文摘要自动写入，故统一按
        ``inferred`` 处理并落冷存档，避免未经声明的历史内容进入断言层影响注入。
        """
        if not self.markdown_path.exists():
            return []
        try:
            raw = self.markdown_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"读取旧记忆文件失败：{exc}")
            return []
        entries = self.parse_legacy_markdown(raw)
        if entries:
            self._backup_legacy_markdown()
            self._save_unlocked(entries)
            logger.info(f"已迁移 {len(entries)} 条旧记忆到断言式存储")
        return entries

    def parse_legacy_markdown(
        self,
        text: str,
        *,
        promote: bool = False,
    ) -> List[MemoryEntry]:
        """按旧格式解析视图文本，缺省统一落冷存档并标记为推断。

        与 :meth:`parse_markdown` 的区别在默认层与可信度：那个面向人工整体编辑，视为
        用户本人声明；这个面向历史迁移，历史内容未经确认，不能直接进断言层。
        ``promote`` 给一次性迁移用：用户明确认领旧内容时按显式声明处理，仅影响本次
        解析结果，不改变以后的自动摘要。
        """
        return self._parse_markdown(
            text,
            base_kind=MemoryKind.RECENT if promote else MemoryKind.ARCHIVED,
            base_confidence=Confidence.STATED if promote else Confidence.INFERRED,
            promote=promote,
        )

    def migrate_legacy(
        self,
        *,
        force: bool = False,
        promote: bool = False,
        before_write: Optional[Callable[[], None]] = None,
    ) -> "MigrationReport":
        """显式执行一次旧格式迁移，并给出可用于回报的结果。

        与惰性迁移的区别：能在已有新存储的情况下补齐遗漏条目、按需升级已迁移条目，
        且不静默吞掉「为什么没迁」——脚本与部署流程需要能一眼看出结论。

        ``before_write`` 在确认要落盘之后、写之前调用一次，供调用方做备份：无事可做的
        空跑不该留下备份文件。
        """
        if not self.markdown_path.exists():
            return MigrationReport(self.memory_dir, "nothing_to_do", 0, self._count_jsonl(), None, "没有 MEMORY.md")

        try:
            raw = self.markdown_path.read_text(encoding="utf-8")
        except OSError as exc:
            return MigrationReport(self.memory_dir, "failed", 0, 0, None, f"读取旧记忆失败：{exc}")

        expected = self.parse_legacy_markdown(raw, promote=promote)
        if not expected:
            return MigrationReport(self.memory_dir, "nothing_to_do", 0, self._count_jsonl(), None, "旧记忆里没有可解析的条目")

        existing = self._read_jsonl() if self.jsonl_path.exists() else []
        existing = existing or []
        if existing and not force:
            return MigrationReport(
                self.memory_dir,
                "up_to_date",
                0,
                len(existing),
                None,
                "已存在 MEMORY.jsonl，跳过；需要补齐遗漏条目时用 --force",
            )

        by_key = {entry.key: entry for entry in existing}
        known_values = {entry.value for entry in existing}
        added: List[MemoryEntry] = []
        upgraded = 0
        for entry in expected:
            current = by_key.get(entry.key)
            if current is not None and current.value == entry.value:
                # 只升级、不降级：已按声明处理过的条目不因再跑一次迁移退回冷存档；
                # pinned 由人工维护，迁移不碰
                if (
                    force
                    and promote
                    and current.kind is not MemoryKind.PINNED
                    and (
                        current.kind is not entry.kind
                        or current.confidence is not entry.confidence
                    )
                ):
                    current.kind = entry.kind
                    current.confidence = entry.confidence
                    current.archived_at = None
                    current.updated_at = utc_now()
                    upgraded += 1
                continue
            if entry.value in known_values:
                continue
            added.append(entry)

        if not added and not upgraded:
            return MigrationReport(self.memory_dir, "up_to_date", 0, len(existing), None, "旧内容已全部在存储中")

        backup = self._backup_legacy_markdown()
        if before_write is not None:
            before_write()
        self.save(existing + added)
        logger.info(
            f"已迁移 {len(added)} 条旧记忆到断言式存储"
            f"（新增 {len(added)}，升级 {upgraded}，共 {len(existing) + len(added)} 条）"
        )
        note = f"新增 {len(added)} 条"
        if upgraded:
            note += f"，升级 {upgraded} 条"
        return MigrationReport(
            self.memory_dir,
            "migrated",
            len(added),
            len(existing) + len(added),
            backup,
            note,
        )

    def _count_jsonl(self) -> int:
        if not self.jsonl_path.exists():
            return 0
        return len(self._read_jsonl() or [])

    def _backup_legacy_markdown(self) -> Optional[Path]:
        """迁移前保留原文副本。

        迁移会重写 MEMORY.md，原文一旦被覆盖便无法核对，故首次迁移保留 .legacy 备份。
        """
        target = self.markdown_path.with_suffix(".md.legacy")
        if target.exists():
            return target
        try:
            shutil.copy2(self.markdown_path, target)
        except OSError as exc:
            logger.warning(f"备份旧记忆文件失败：{exc}")
            return None
        return target

    # ------------------------------------------------------------------ 写

    def save(self, entries: List[MemoryEntry]) -> None:
        if fcntl is None:
            self._save_unlocked(entries)
            return
        with self._file_lock():
            self._save_unlocked(entries)

    def _save_unlocked(self, entries: List[MemoryEntry]) -> None:
        payload = "\n".join(entry.to_json() for entry in entries)
        if payload:
            payload += "\n"
        self._atomic_write(self.jsonl_path, payload)
        self._atomic_write(self.markdown_path, self._render_markdown(entries))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """先写临时文件再 rename。

        直接覆盖写入中途失败会留下截断的记忆文件（不可恢复）；rename 在同一文件系统内
        是原子的。
        """
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)

    # ------------------------------------------------------------- markdown

    def _render_markdown(self, entries: List[MemoryEntry]) -> str:
        blocks: List[str] = [_VIEW_HEADER]
        for kind, title in _SECTION_ORDER:
            # 冷存档本身即推断内容的归属层，故只对断言层施加可信度过滤
            visible = [
                entry
                for entry in entries
                if entry.kind is kind
                and entry.is_active
                and (kind is MemoryKind.ARCHIVED or entry.confidence is Confidence.STATED)
            ]
            if not visible:
                continue
            visible.sort(key=lambda item: item.updated_at, reverse=True)
            note = ""
            if kind is MemoryKind.ARCHIVED and len(visible) > _ARCHIVE_VIEW_LIMIT:
                note = (
                    f"\n> 仅展示最近 {_ARCHIVE_VIEW_LIMIT} 条，"
                    f"其余 {len(visible) - _ARCHIVE_VIEW_LIMIT} 条通过 /api/memory/entries 查看。"
                )
                visible = visible[:_ARCHIVE_VIEW_LIMIT]
            blocks.append(
                f"\n## {title}\n{note}\n" + "\n".join(item.render_line() for item in visible) + "\n"
            )
        return "".join(blocks)

    def parse_markdown(self, text: str) -> List[MemoryEntry]:
        """把视图文本解析回条目，供人工整体编辑。

        未出现章节标题时按 recent 处理，兼容直接粘贴纯条目列表。
        """
        return self._parse_markdown(text, base_kind=MemoryKind.RECENT, base_confidence=Confidence.STATED)

    def _parse_markdown(
        self,
        text: str,
        *,
        base_kind: MemoryKind,
        base_confidence: Confidence,
        promote: bool = False,
    ) -> List[MemoryEntry]:
        entries: List[MemoryEntry] = []
        current_kind = base_kind
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            section = _SECTION_RE.match(line)
            if section:
                current_kind = _SECTION_KINDS[section.group("name").lower()]
                # 认领旧内容时，视图里的 archived 章节不代表用户仍要把它留在冷存档
                if promote and current_kind is MemoryKind.ARCHIVED:
                    current_kind = MemoryKind.RECENT
                continue
            # 以 # 开头的标题与以 > 开头的说明行不属于条目
            if line.startswith(("#", ">")):
                continue
            matched = _VIEW_LINE_RE.match(line)
            if matched:
                entries.append(
                    self._entry_from_parts(
                        key=matched.group("key").strip(),
                        value=matched.group("value"),
                        date=matched.group("date"),
                        source=matched.group("source"),
                        kind=current_kind,
                        confidence=base_confidence,
                    )
                )
                continue
            legacy = _LEGACY_LINE_RE.match(line)
            if legacy:
                entries.append(
                    self._entry_from_parts(
                        key="",
                        value=legacy.group("value"),
                        date=legacy.group("date"),
                        source=legacy.group("source").strip(),
                        kind=current_kind,
                        confidence=base_confidence,
                    )
                )
                continue
            # 无格式的裸行按正文处理：用户可以只写一句结论而不关心格式
            bare = line[2:].strip() if line.startswith(("- ", "* ")) else line
            if bare:
                entries.append(
                    self._entry_from_parts(
                        key="",
                        value=bare,
                        date=utc_now()[:10],
                        source="manual",
                        kind=current_kind,
                        confidence=base_confidence,
                    )
                )
        return entries

    @staticmethod
    def _entry_from_parts(
        *,
        key: str,
        value: str,
        date: str,
        source: str,
        kind: MemoryKind,
        confidence: Confidence,
    ) -> MemoryEntry:
        normalized_key = key.strip() or _key_from_value(value)
        timestamp = _normalize_date(date)
        return MemoryEntry(
            key=normalized_key,
            value=value.strip(),
            kind=kind,
            confidence=confidence,
            source=source.strip() or "manual",
            created_at=timestamp,
            updated_at=timestamp,
        )


def _key_from_value(value: str) -> str:
    """旧条目无显式 key，用内容摘要派生。

    同一段旧内容重复出现会归并到同一条，优于给每行随机分配 key。
    """
    from backend.modules.memory.models import generate_key

    return generate_key(value.strip(), "legacy")


def _normalize_date(raw: str) -> str:
    value = (raw or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        suffix = value[10:] or "T00:00:00+00:00"
        if suffix.startswith("T"):
            return f"{value[:10]}{suffix}"
        return f"{value[:10]}T00:00:00+00:00"
    return utc_now()


def entry_payload(entry: MemoryEntry) -> Dict[str, Any]:
    """工具与接口层统一使用的条目摘要，避免把内部字段直接暴露出去。"""
    return {
        "id": entry.id,
        "key": entry.key,
        "value": entry.value,
        "kind": entry.kind.value,
        "source": entry.source,
        "updated_at": entry.updated_at,
        "hits": entry.hits,
        "superseded_by": entry.superseded_by,
    }
