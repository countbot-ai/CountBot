#!/usr/bin/env python3
"""改动前备份文件并记录校验和与 git 版本，便于回滚对比。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = ROOT / ".backup-split"
MANIFEST = BACKUP_ROOT / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _git_revision() -> str:
    """记录当前的 git 提交，便于知道备份对应哪个版本。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"created_at": datetime.now().isoformat(timespec="seconds"), "entries": {}}


def _save_manifest(data: dict) -> None:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_backup(args: argparse.Namespace) -> int:
    src = Path(args.path)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        print(f"错误: 文件不存在: {src}", file=sys.stderr)
        return 1

    digest = _sha256(src)
    rel = _rel(src)
    # 备份文件名带哈希前缀，内容不同则不会互相覆盖
    target = BACKUP_ROOT / "files" / f"{rel.replace('/', '__')}.{digest[:8]}.orig"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)

    manifest = _load_manifest()
    manifest["entries"].setdefault(rel, []).append(
        {
            "backup": _rel(target),
            "sha256": digest,
            "size": src.stat().st_size,
            "git_revision": _git_revision(),
            "backed_up_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    _save_manifest(manifest)

    print(f"已备份: {rel}")
    print(f"  原始 SHA256: {digest}")
    print(f"  备份位置:    {_rel(target)}")
    print(f"  git 版本:    {_git_revision()}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    manifest = _load_manifest()
    entries = manifest.get("entries", {})
    if not entries:
        print("尚无备份")
        return 0

    print(f"备份清单（创建于 {manifest.get('created_at')}）")
    for rel, records in sorted(entries.items()):
        current = ROOT / rel
        status = "文件已不存在"
        if current.exists():
            status = "未改动" if _sha256(current) == records[-1]["sha256"] else "已改动"
        print(f"\n  {rel}  [{status}]")
        for rec in records:
            print(f"    {rec['backed_up_at']}  {rec['sha256'][:12]}  {rec['backup']}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    src = Path(args.path)
    if not src.is_absolute():
        src = ROOT / src
    rel = _rel(src)
    records = _load_manifest().get("entries", {}).get(rel)
    if not records:
        print(f"错误: {rel} 没有备份记录", file=sys.stderr)
        return 1

    original = ROOT / records[-1]["backup"]
    if not src.exists():
        print(f"{rel}: 当前文件不存在（备份中的版本为 {records[-1]['sha256'][:12]}）")
        return 0

    current_digest = _sha256(src)
    if current_digest == records[-1]["sha256"]:
        print(f"{rel}: 与备份完全一致（未改动）")
        return 0

    print(f"{rel}: 已改动")
    print(f"  备份 {records[-1]['sha256'][:12]}  ({original.stat().st_size} 字节)")
    print(f"  当前 {current_digest[:12]}  ({src.stat().st_size} 字节)")
    print("\n  如需逐行对比，可运行：")
    print(f"    diff -u {_rel(original)} {rel}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    src = Path(args.path)
    if not src.is_absolute():
        src = ROOT / src
    rel = _rel(src)
    records = _load_manifest().get("entries", {}).get(rel)
    if not records:
        print(f"错误: {rel} 没有备份记录", file=sys.stderr)
        return 1

    latest = records[-1]
    original = ROOT / latest["backup"]
    if not original.exists():
        print(f"错误: 备份文件缺失: {original}", file=sys.stderr)
        return 1

    # 回滚前把当前状态也留一份，避免「回滚后又想回去」时无路可走
    if src.exists():
        safety = BACKUP_ROOT / "pre-restore" / f"{rel.replace('/', '__')}.{_sha256(src)[:8]}.py"
        safety.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, safety)
        print(f"回滚前快照: {_rel(safety)}")

    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, src)

    restored = _sha256(src)
    ok = restored == latest["sha256"]
    print(f"已回滚: {rel}")
    print(f"  期望 SHA256: {latest['sha256']}")
    print(f"  实际 SHA256: {restored}")
    print(f"  结果: {'一致 ✓' if ok else '不一致 ✗'}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="拆分前备份与回滚")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backup", help="备份文件")
    b.add_argument("path")
    b.set_defaults(func=cmd_backup)

    l = sub.add_parser("list", help="列出备份")
    l.set_defaults(func=cmd_list)

    d = sub.add_parser("diff", help="对比当前文件与备份")
    d.add_argument("path")
    d.set_defaults(func=cmd_diff)

    r = sub.add_parser("restore", help="回滚到备份")
    r.add_argument("path")
    r.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"执行出错: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
