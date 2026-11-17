#!/usr/bin/env python3
"""把旧版记忆迁移到断言式存储。

老版本的记忆是 ``MEMORY.md`` 里一行行散文（``日期|来源|内容``），新版本的主存储是
``MEMORY.jsonl``。应用首次读到记忆时会自动迁移当前工作区的那一份，但这条惰性路径
覆盖不到两种情形：

- 旧数据还留在老布局 ``<程序目录>/memory/``，而新版只看工作区目录；
- 需要离线批量处理、先看结果再落盘、或者按「我认领这些旧内容」导入。

用法::

    # 只看会发生什么，不落盘
    python scripts/migrate_memory.py --dry-run

    # 迁移当前工作区
    python scripts/migrate_memory.py

    # 从老布局目录导入，并把这些旧内容当作显式声明（进入可注入层）
    python scripts/migrate_memory.py --from ./memory --promote

    # 已迁移过、想补上后来才发现的遗漏条目
    python scripts/migrate_memory.py --force

迁移后的条目默认落在冷存档（archived）且标记为 inferred：旧内容是模型对历史对话的
复述，未经确认就注入每一轮，会被当成权威背景反复引用。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.memory import (  # noqa: E402
    Confidence,
    MemoryKind,
    MemoryService,
    MemoryStorage,
)


def _resolve_target(explicit: Optional[str]) -> Path:
    """确定目标记忆目录。

    未显式指定时按当前生效的配置取工作区；配置读不到就退回仓库内的默认工作区，
    避免脚本因为「配置不存在」而无法用于排查。
    """
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.name == "memory" else path / "memory"

    try:
        from backend.modules.config.loader import config_loader

        import asyncio

        config = asyncio.run(config_loader.load())
        if config.workspace.path:
            return Path(config.workspace.path).expanduser().resolve() / "memory"
    except Exception:  # 配置缺失或结构变更都不该让迁移脚本失效
        pass

    from backend.utils.paths import WORKSPACE_DIR

    return Path(WORKSPACE_DIR).resolve() / "memory"


def _candidate_sources(target: Path, explicit: List[str]) -> List[Path]:
    """找出可能有旧记忆的目录。

    老版本把记忆放在程序根目录下的 ``memory/``，新版在工作区目录下，两个位置都要看；
    否则从老版本升级上来的用户会以为记忆全丢了。目标目录始终参与：它自己的
    ``MEMORY.md`` 也要就地迁移，即便本次指定了外部来源。
    """
    if explicit:
        paths = [Path(item).expanduser().resolve() for item in explicit] + [target]
    else:
        from backend.utils.paths import get_runtime_root

        paths = [
            get_runtime_root() / "memory",
            target,
        ]

    normalized: List[Path] = []
    for path in paths:
        resolved = path / "memory" if path.name != "memory" else path
        if not resolved.exists():
            continue
        if resolved in normalized:
            continue
        normalized.append(resolved)
    return normalized


class _BackupGate:
    """在第一次真正写盘前才备份现有存储。

    空跑（旧内容已全部在存储中）不该留下备份文件，否则反复执行会堆一目录的 .bak。
    """

    def __init__(self, target: Path, enabled: bool):
        self._target = target
        self._enabled = enabled
        self._done = False
        self.path: Optional[Path] = None

    def ensure(self) -> None:
        if self._done or not self._enabled:
            return
        self._done = True
        self.path = _backup_jsonl(self._target)


def _backup_jsonl(target: Path) -> Optional[Path]:
    """给现有存储留一份副本。"""
    source = target / "MEMORY.jsonl"
    if not source.exists() or source.stat().st_size == 0:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target / f"MEMORY.jsonl.bak.{stamp}"
    shutil.copy2(source, backup)
    return backup


def _import_foreign(
    source: Path,
    target: Path,
    *,
    promote: bool,
    force: bool,
    dry_run: bool,
    gate: "_BackupGate",
) -> Dict[str, Any]:
    """把一个外部目录的旧记忆并入目标存储。

    去重按内容与派生 key：同一条旧内容重复迁移不会变成两条，即便它上次来自另一个目录。
    ``force`` 配合 ``promote`` 时，已存在但仍是推断状态的同内容条目会被升级，与就地
    迁移的语义保持一致。
    """
    storage = MemoryStorage(source)
    markdown = source / "MEMORY.md"
    if not markdown.exists():
        return {"source": str(source), "status": "nothing_to_do", "imported": 0, "note": "没有 MEMORY.md"}

    try:
        entries = storage.parse_legacy_markdown(markdown.read_text(encoding="utf-8"), promote=promote)
    except OSError as exc:
        return {"source": str(source), "status": "failed", "imported": 0, "note": f"读取失败：{exc}"}

    if not entries:
        return {"source": str(source), "status": "nothing_to_do", "imported": 0, "note": "没有可解析的条目"}

    if dry_run:
        return {
            "source": str(source),
            "status": "would_import",
            "imported": len(entries),
            "note": "预演，未落盘",
        }

    service = MemoryService(target)
    existing = {entry.value: entry for entry in service.list_entries(limit=100000)}
    imported = 0
    upgraded = 0
    for entry in entries:
        current = existing.get(entry.value)
        if current is not None:
            if (
                force
                and promote
                and current.kind is not MemoryKind.PINNED
                and (
                    current.kind is not entry.kind
                    or current.confidence is not entry.confidence
                )
            ):
                gate.ensure()
                service.update_layer(
                    current.id,
                    kind=entry.kind,
                    confidence=entry.confidence,
                )
                upgraded += 1
            continue
        gate.ensure()
        service.remember(
            entry.key,
            entry.value,
            kind=entry.kind,
            confidence=entry.confidence,
            source=entry.source or "manual",
        )
        existing[entry.value] = entry
        imported += 1

    if not imported and not upgraded:
        return {
            "source": str(source),
            "status": "up_to_date",
            "imported": 0,
            "note": "旧内容已全部在存储中",
        }
    return {
        "source": str(source),
        "status": "imported",
        "imported": imported,
        "note": f"新增 {imported} 条" + (f"，升级 {upgraded} 条" if upgraded else ""),
    }


def _migrate_in_place(
    target: Path,
    *,
    force: bool,
    promote: bool,
    dry_run: bool,
    gate: "_BackupGate",
) -> Dict[str, Any]:
    storage = MemoryStorage(target)
    if dry_run:
        markdown = target / "MEMORY.md"
        if not markdown.exists():
            return {"source": str(target), "status": "nothing_to_do", "imported": 0, "note": "没有 MEMORY.md"}
        try:
            entries = storage.parse_legacy_markdown(markdown.read_text(encoding="utf-8"), promote=promote)
        except OSError as exc:
            return {"source": str(target), "status": "failed", "imported": 0, "note": f"读取失败：{exc}"}
        has_store = (target / "MEMORY.jsonl").exists() and (target / "MEMORY.jsonl").stat().st_size > 0
        status = "would_skip" if has_store and not force else "would_import"
        return {
            "source": str(target),
            "status": status,
            "imported": 0 if status == "would_skip" else len(entries),
            "note": (
                "已有存储，跳过；加 --force 补齐遗漏条目"
                if status == "would_skip"
                else "预演，未落盘"
            ),
        }

    report = storage.migrate_legacy(force=force, promote=promote, before_write=gate.ensure)
    return {
        "source": str(report.memory_dir),
        "status": report.status,
        "imported": report.imported,
        "note": report.note,
        "backup": str(report.backup) if report.backup else None,
        "total": report.total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把旧版 markdown 记忆迁移到断言式 JSONL 存储",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", help="目标工作区（默认取当前配置的工作区）")
    parser.add_argument(
        "--from",
        dest="sources",
        action="append",
        default=[],
        help="要导入的旧记忆目录，可重复；缺省自动发现程序根目录与目标目录",
    )
    parser.add_argument("--promote", action="store_true", help="把旧内容当作显式声明导入（进入可注入层）")
    parser.add_argument("--force", action="store_true", help="已有存储时仍补齐遗漏条目")
    parser.add_argument("--dry-run", action="store_true", help="只报告将要做什么，不写盘")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    target = _resolve_target(args.target)
    sources = _candidate_sources(target, args.sources)
    if not sources:
        print(f"没有找到任何含 MEMORY.md 的记忆目录（目标：{target}）", file=sys.stderr)
        return 1

    # 目标目录先处理：任何一次写入都会创建 MEMORY.jsonl，之后再跑就地迁移就只会
    # 报「已存在存储」，结果是「迁了但报告说没迁」
    sources.sort(key=lambda item: (item != target, str(item)))

    gate = _BackupGate(target, enabled=not args.dry_run)

    results: List[Dict[str, Any]] = []
    for source in sources:
        if source == target:
            results.append(
                _migrate_in_place(
                    target,
                    force=args.force,
                    promote=args.promote,
                    dry_run=args.dry_run,
                    gate=gate,
                )
            )
        else:
            results.append(
                _import_foreign(
                    source,
                    target,
                    promote=args.promote,
                    force=args.force,
                    dry_run=args.dry_run,
                    gate=gate,
                )
            )

    payload = {
        "target": str(target),
        "promote": args.promote,
        "dry_run": args.dry_run,
        "backup": str(gate.path) if gate.path else None,
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"目标：{target}")
        if gate.path:
            print(f"写盘前已备份现有存储：{gate.path}")
        for item in results:
            line = f"  {item['status']:<14} {item['imported']:>4} 条  {item['source']}"
            if item.get("note"):
                line += f"  ({item['note']})"
            print(line)
        if args.dry_run:
            print("预演结束，未写入任何文件。去掉 --dry-run 生效。")

    failed = any(item["status"] == "failed" for item in results)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
