#!/usr/bin/env python3
"""Prune lark_oapi before packaging, dropping Feishu OpenAPI client code CountBot never uses.

Background: lark_oapi/api/__init__.py eagerly imports all ~59 product modules,
and lark_oapi/event/dispatcher_handler.py wildcard-imports every product's
processor. CountBot only uses the im / cardkit / contact products (see the
explicit imports in backend/modules/channels/feishu.py); the unused modules are
roughly 90% of the SDK size and would all be bundled into the PyInstaller build.

Steps:
1. Delete every subpackage under lark_oapi/api/ that is not in the keep list;
2. Rewrite lark_oapi/api/__init__.py to import only the keep list;
3. Rewrite lark_oapi/event/dispatcher_handler.py so it wildcard-imports only
   the kept products' processors (the EventDispatcherHandler class body only
   depends on generic core types and pulls product classes in through those
   wildcard imports, so dropping the rest does not affect dispatch for the
   kept products);
4. Clean up leftover __pycache__ directories.

Event dispatch trade-off: events of pruned products no longer have a
registration entry point. CountBot's Feishu channel only registers im events
(feishu_websocket_worker.py; any other registration name is probed via getattr
and skipped when missing), so behavior is unchanged.

Usage: run ``python scripts/prune_lark_oapi.py`` in a packaging environment that
has lark-oapi installed; ``--dry-run`` previews without changes. Idempotent and
safe to re-run.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import sys
from pathlib import Path

# API product modules actually used by CountBot's Feishu channel (explicit imports in feishu.py).
KEEP_API_DIRS = ("cardkit", "contact", "im")

# Line format of the wildcard imports in dispatcher_handler.py.
_DISPATCHER_IMPORT_RE = re.compile(r"^from (lark_oapi\.api\.[a-z_0-9]+)\.[\w.]+ import \*\s*$")

# Three per-product line groups in client.py: service import, __init__ declaration, build() wiring.
_CLIENT_IMPORT_RE = re.compile(r"^from \.api\.([a-z_0-9]+)\.service import \w+Service\s*$")
_CLIENT_DECL_RE = re.compile(r"^        self\.([a-z][a-z_0-9]*): Optional\[\w+Service\] = None\s*$")
_CLIENT_BUILD_RE = re.compile(r"^        client\.([a-z][a-z_0-9]*) = \w+Service\(self\._config\)\s*$")


def ensure_utf8_stdio() -> None:
    """Windows consoles/CI default to cp1252; force UTF-8 so logging never breaks."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def locate_lark_package() -> Path:
    spec = importlib.util.find_spec("lark_oapi")
    if not spec or not spec.origin:
        raise SystemExit("lark_oapi is not installed in the current Python environment")
    return Path(spec.origin).parent


def prune_api_dir(api_dir: Path, dry_run: bool) -> list[Path]:
    removed = []
    for child in sorted(api_dir.iterdir()):
        if not child.is_dir() or child.name in KEEP_API_DIRS:
            continue
        removed.append(child)
        if not dry_run:
            shutil.rmtree(child, ignore_errors=True)
    return removed


def rewrite_api_init(api_dir: Path, dry_run: bool) -> None:
    keep_lines = [
        f"from . import {name}\n"
        for name in KEEP_API_DIRS
        if (api_dir / name).is_dir()
    ]
    target = api_dir / "__init__.py"
    if dry_run:
        return
    target.write_text("".join(keep_lines), encoding="utf-8")


def rewrite_dispatcher(event_dir: Path, dry_run: bool) -> int:
    """Prune dispatcher_handler.py and return the number of wildcard imports processed.

    The generated ``register_p2_*`` methods use event model classes in their
    annotations, which are evaluated when the class is created. So besides
    filtering wildcard imports by the keep list, we also inject
    ``from __future__ import annotations`` at the top of the file: annotations
    become strings, and the register methods of pruned products turn into dead
    methods that only raise NameError if ever called — and method bodies only
    run on explicit registration anyway. CountBot registers only im events
    (including the optional getattr-probed names), so behavior is unchanged.
    """
    target = event_dir / "dispatcher_handler.py"
    if not target.exists():
        return 0
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)

    if any("__future__ import annotations" in line for line in lines[:5]):
        pass
    else:
        # The future import must precede the first statement; the generated file starts with comments.
        for idx, line in enumerate(lines):
            if not line.startswith("#"):
                lines.insert(idx, "from __future__ import annotations\n")
                break

    kept: list[str] = []
    dropped = 0
    for line in lines:
        match = _DISPATCHER_IMPORT_RE.match(line)
        if match:
            product = match.group(1).split(".")[-1]
            if product not in KEEP_API_DIRS:
                dropped += 1
                continue
        kept.append(line)
    if not dry_run:
        target.write_text("".join(kept), encoding="utf-8")
    return dropped


def rewrite_client(package_dir: Path, dry_run: bool) -> int:
    """Filter client.py's per-product Service lines by the keep list, returning the count removed.

    All three Service assignment sites (import / __init__ declaration / build()
    wiring) are one line per product and generated by rule, so line filtering is
    enough. CountBot calls the SDK through ``client.im / client.contact /
    client.cardkit``, and attributes in the keep list behave the same after
    pruning.
    """
    target = package_dir / "client.py"
    if not target.exists():
        return 0
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    kept: list[str] = []
    dropped = 0
    for line in lines:
        product = None
        for regex in (_CLIENT_IMPORT_RE, _CLIENT_DECL_RE, _CLIENT_BUILD_RE):
            match = regex.match(line)
            if match:
                product = match.group(1)
                break
        if product is not None and product not in KEEP_API_DIRS:
            dropped += 1
            continue
        kept.append(line)
    if not dry_run:
        target.write_text("".join(kept), encoding="utf-8")
    return dropped


def clean_pycache(package_dir: Path, dry_run: bool) -> int:
    removed = 0
    for cache in package_dir.rglob("__pycache__"):
        removed += 1
        if not dry_run:
            shutil.rmtree(cache, ignore_errors=True)
    return removed


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, delete nothing")
    args = parser.parse_args()

    package_dir = locate_lark_package()
    api_dir = package_dir / "api"
    event_dir = package_dir / "event"
    if not api_dir.is_dir():
        raise SystemExit(f"unexpected lark_oapi package layout: {package_dir}")

    size_before = dir_size(package_dir)
    removed_dirs = prune_api_dir(api_dir, args.dry_run)
    rewrite_api_init(api_dir, args.dry_run)
    dropped_imports = rewrite_dispatcher(event_dir, args.dry_run)
    dropped_client_lines = rewrite_client(package_dir, args.dry_run)
    pycache_count = clean_pycache(package_dir, args.dry_run)
    size_after = size_before if args.dry_run else dir_size(package_dir)

    print(f"lark_oapi package: {package_dir}")
    print(f"pruned api subpackages: {[p.name for p in removed_dirs] or '(none, possibly already pruned)'}")
    print(f"dispatcher_handler wildcard imports removed: {dropped_imports} lines")
    print(f"client.py product Service lines removed: {dropped_client_lines} lines")
    print(f"__pycache__ directories cleaned: {pycache_count}")
    print(f"size: {size_before / 1024 / 1024:.1f}MB -> {size_after / 1024 / 1024:.1f}MB")

    # Final sanity check: import failure means pruning broke a kept path, so fail before packaging.
    if not args.dry_run:
        import subprocess

        check = subprocess.run(
            [
                sys.executable,
                "-c",
                "import lark_oapi\n"
                "import lark_oapi.ws\n"
                "c = lark_oapi.Client.builder().app_id('x').app_secret('y').build()\n"
                "assert c.im and c.contact and c.cardkit, 'service attr missing'\n"
                "b = lark_oapi.EventDispatcherHandler.builder('', '')\n"
                "assert hasattr(b, 'register_p2_im_message_receive_v1')\n",
            ],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            raise SystemExit(
                "lark_oapi import failed after pruning, do not package:\n" + (check.stderr or "")
            )
        print("self-check passed: import lark_oapi / lark_oapi.ws OK")


if __name__ == "__main__":
    main()
