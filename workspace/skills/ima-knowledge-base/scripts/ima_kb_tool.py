#!/usr/bin/env python3
"""Thin wrapper exposing only IMA knowledge-base commands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ALLOWED_COMMANDS = {
    "list-kb",
    "list-addable-kb",
    "list-kb-items",
    "search-kb",
    "show-kb-hit",
    "inspect-kb-hit",
    "upload-file",
    "import-url",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IMA knowledge-base command wrapper")
    parser.add_argument("--config", default="", help="Optional path to config.json")
    parser.add_argument("command", choices=sorted(ALLOWED_COMMANDS), help="Knowledge-base command")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to ima_tool.py")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    local_tool = Path(__file__).resolve().parent / "ima_tool.py"
    command = [sys.executable, str(local_tool)]
    if args.config:
        command.extend(["--config", args.config])
    command.append(args.command)
    command.extend(args.args)
    raise SystemExit(subprocess.run(command).returncode)


if __name__ == "__main__":
    main()
