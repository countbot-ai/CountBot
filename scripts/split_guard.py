#!/usr/bin/env python3
"""拆分大模块前后对比 AST、导入面与路由表，判定拆分是否等价。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ensure_project_root_on_path() -> None:
    """把项目根目录加入 sys.path，使 backend.* 可被导入。"""
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _module_name_from_path(path: str) -> str:
    """把文件路径转成可导入的模块名。"""
    p = Path(path).with_suffix("")
    parts = list(p.parts)
    if parts and parts[0] == "backend":
        return ".".join(parts)
    # 相对路径按点号拼接
    return ".".join(parts)


def _fingerprints(source: str) -> Dict[str, str]:
    """计算每个函数、类与模块级赋值的 AST 指纹。"""
    tree = ast.parse(source)
    result: Dict[str, str] = {}

    def _record(key: str, node: ast.AST) -> None:
        digest = hashlib.sha256(ast.dump(node).encode()).hexdigest()[:16]
        if key in result and result[key] != digest:
            key = f"{key}@{getattr(node, 'lineno', 0)}"
        result[key] = digest

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _record(node.name, node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _record(f"global:{target.id}", node)

    # 嵌套的类方法也要覆盖到
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _record(node.name, node)

    return result


def _collect_source(path: str) -> str:
    """读取模块源码；若传入的是包目录，则拼接包内所有 .py。"""
    p = Path(path)
    if p.is_dir():
        return "\n\n".join(
            f.read_text(encoding="utf-8")
            for f in sorted(p.rglob("*.py"))
            if "__pycache__" not in str(f)
        )
    return p.read_text(encoding="utf-8")


def _public_names(module_name: str) -> Optional[List[str]]:
    """导入模块，取其对外可用的符号名。导入失败返回 None。"""
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - 需要把失败原因呈现给使用者
        print(f"  [warn] 无法导入 {module_name}: {exc}", file=sys.stderr)
        return None
    return sorted(n for n in dir(mod) if not n.startswith("__"))


def _route_signature(module_name: str) -> Optional[List[List[Any]]]:
    """取 FastAPI router 的路由集合。无 router 时返回 None。"""
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        return None
    router = getattr(mod, "router", None)
    if router is None or not hasattr(router, "routes"):
        return None
    sig = []
    for route in router.routes:
        methods = getattr(route, "methods", None)
        sig.append([
            getattr(route, "path", ""),
            sorted(methods) if methods else [],
        ])
    return sorted(sig, key=lambda x: (x[0], x[1]))


def _route_key(route: List[Any]) -> tuple:
    """把 [path, [methods]] 结构转成可哈希的键。"""
    path, methods = route[0], route[1]
    return (path, tuple(methods))


def _symbol_locations(root: Path, names: List[str]) -> Dict[str, List[str]]:
    """在项目内搜索每个符号的定义位置，用于人工确认移动去向。"""
    locations: Dict[str, List[str]] = {name: [] for name in names}
    for f in root.rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in locations:
                    locations[node.name].append(f"{f}:{node.lineno}")
    return locations


def cmd_snapshot(args: argparse.Namespace) -> int:
    path = args.path
    module_name = args.module or _module_name_from_path(path)
    source = _collect_source(path)

    data = {
        "path": path,
        "module": module_name,
        "fingerprints": _fingerprints(source),
        "public_names": _public_names(module_name),
        "routes": _route_signature(module_name),
    }

    # 导入失败会让闸门 2/3 失效，必须让使用者知道，而不是记一个空列表当基线
    if data["public_names"] is None:
        print(
            f"\n错误: 模块 {module_name} 无法导入，基线不完整。\n"
            "请先修正导入错误（或确认 PYTHONPATH），否则导入面与路由闸门将失效。",
            file=sys.stderr,
        )
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"已记录基线: {out}")
    print(f"  函数/类: {len(data['fingerprints'])} 个")
    print(f"  对外符号: {len(data['public_names'] or [])} 个")
    print(f"  路由: {len(data['routes'] or [])} 条")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    path = args.path
    module_name = args.module or baseline.get("module") or _module_name_from_path(path)
    source = _collect_source(path)

    failures: List[str] = []

    # --- 闸门 1：AST 结构等价 ---
    print("[1/4] AST 结构等价检查")
    current = _fingerprints(source)
    before = baseline["fingerprints"]
    missing = [k for k in before if k not in current]
    changed = [k for k in before if k in current and current[k] != before[k]]
    if missing:
        failures.append(f"符号丢失: {missing}")
        print(f"  ✗ 丢失 {len(missing)} 个: {missing[:8]}")
    if changed:
        failures.append(f"结构被改: {changed}")
        print(f"  ✗ 有 {len(changed)} 个函数/类结构变了: {changed[:8]}")
    if not missing and not changed:
        print(f"  ✓ {len(before)} 个函数/类结构完全一致")

    # --- 闸门 2：导入面不变 ---
    print("[2/4] 导入面检查")
    before_pub = baseline.get("public_names")
    if before_pub is None:
        print("  - 基线未记录（原模块当时无法导入），跳过")
    else:
        after_pub = _public_names(module_name)
        if after_pub is None:
            failures.append("模块已无法导入")
            print("  ✗ 模块无法导入")
        else:
            lost = sorted(set(before_pub) - set(after_pub))
            if lost:
                failures.append(f"对外符号丢失: {lost}")
                print(f"  ✗ 丢失 {len(lost)} 个对外符号: {lost}")
            else:
                print(f"  ✓ {len(before_pub)} 个对外符号全部保留")

    # --- 闸门 3：路由表不变 ---
    print("[3/4] 路由表检查")
    before_routes = baseline.get("routes")
    if before_routes is None:
        print("  - 该模块无 router，跳过")
    else:
        after_routes = _route_signature(module_name)
        if after_routes is None:
            failures.append("router 丢失或无法读取")
            print("  ✗ router 不存在或无法导入该模块")
        elif after_routes != before_routes:
            before_set = {_route_key(r) for r in before_routes}
            after_set = {_route_key(r) for r in after_routes}
            lost_routes = before_set - after_set
            new_routes = after_set - before_set
            if lost_routes:
                failures.append(f"路由丢失: {len(lost_routes)} 条")
                print(f"  ✗ 丢失 {len(lost_routes)} 条路由")
                for r in list(lost_routes)[:5]:
                    print(f"      {r}")
            if new_routes:
                print(f"  ! 新增 {len(new_routes)} 条路由（确认是否有意）")
        else:
            print(f"  ✓ {len(before_routes)} 条路由完全一致")

    # --- 闸门 4：符号去向 ---
    print("[4/4] 符号去向")
    root = Path(args.root)
    locations = _symbol_locations(root, list(before.keys()))
    scattered = {
        name: locs for name, locs in locations.items() if len(locs) > 1
    }
    if scattered:
        print(f"  ! 有 {len(scattered)} 个符号在多个位置定义（可能是重复定义）")
        for name, locs in list(scattered.items())[:5]:
            print(f"      {name}: {locs}")
    else:
        print("  ✓ 未发现重复定义")

    print()
    if failures:
        print(f"结果: 失败（{len(failures)} 项）")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("结果: 全部通过")
    return 0


def main() -> int:
    _ensure_project_root_on_path()
    parser = argparse.ArgumentParser(description="大文件拆分安全闸门")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="记录拆分前基线")
    snap.add_argument("path", help="文件路径或包目录")
    snap.add_argument("--module", help="模块名（默认由路径推断）")
    snap.add_argument("--out", required=True, help="基线输出路径")
    snap.set_defaults(func=cmd_snapshot)

    ver = sub.add_parser("verify", help="拆分后对比基线")
    ver.add_argument("path", help="文件路径或包目录")
    ver.add_argument("--module", help="模块名（默认取基线记录值）")
    ver.add_argument("--baseline", required=True, help="基线文件路径")
    ver.add_argument("--root", default=".", help="项目根目录，用于符号定位")
    ver.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        # 闸门自身出错必须显式失败：静默返回 0 会让「没检查」被误当成「检查通过」。
        print(f"\n闸门执行出错: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
