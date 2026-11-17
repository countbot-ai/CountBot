#!/usr/bin/env python3
"""检测模块中使用了但未定义的名字，用于拆分后查漏。"""

from __future__ import annotations

import argparse
import ast
import builtins
import sys
from pathlib import Path
from typing import Dict, List, Set

_BUILTINS = set(dir(builtins))


def _collect_defined(tree: ast.AST) -> Set[str]:
    """收集模块内所有被定义的名字（导入、赋值、函数、类、参数、推导变量）。"""
    defined: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                defined.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    defined.add(alias.asname or alias.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.comprehension):
            for target in ast.walk(node.target):
                if isinstance(target, ast.Name):
                    defined.add(target.id)
        elif isinstance(node, ast.Global):
            defined.update(node.names)
    return defined


def _collect_used(tree: ast.AST) -> Set[str]:
    """收集所有被读取的名字。"""
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def check_file(path: Path) -> List[str]:
    """返回该文件缺失的名字列表。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError as exc:
        return [f"<语法错误: {exc}>"]

    defined = _collect_defined(tree)
    used = _collect_used(tree)

    # 只把注解中的字符串当作名字，普通字符串常量不算标识符
    for node in ast.walk(tree):
        annotation = None
        if isinstance(node, ast.arg):
            annotation = node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotation = node.returns
        elif isinstance(node, ast.AnnAssign):
            annotation = node.annotation
        if annotation is None:
            continue
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                for token in sub.value.replace("[", " ").replace("]", " ").replace(",", " ").split():
                    used.add(token)

    return sorted(used - defined - _BUILTINS)


def iter_targets(path: Path):
    if path.is_dir():
        for f in sorted(path.rglob("*.py")):
            if "__pycache__" not in str(f):
                yield f
    else:
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="检测未定义名字")
    parser.add_argument("path", help="文件或目录")
    parser.add_argument(
        "--quiet", action="store_true", help="只输出有问题的文件"
    )
    args = parser.parse_args()

    results: Dict[str, List[str]] = {}
    for target in iter_targets(Path(args.path)):
        missing = check_file(target)
        if missing:
            results[str(target)] = missing

    if not results:
        if not args.quiet:
            print("未发现缺失的名字")
        return 0

    for name, missing in results.items():
        print(f"{name}:")
        print(f"  缺失 {missing}")
    print(f"\n共 {len(results)} 个文件有问题")
    return 1


if __name__ == "__main__":
    sys.exit(main())
