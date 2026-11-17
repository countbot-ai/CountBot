"""检测拆分或重构后漏导入、只在运行到才暴露的 NameError。"""
import ast
import builtins
import dis
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"

# 导入系统自动注入的模块级名字，不算未解析
MODULE_DUNDERS = {
    "__file__",
    "__name__",
    "__doc__",
    "__package__",
    "__spec__",
    "__loader__",
    "__builtins__",
    "__annotations__",
    "__debug__",
}

# 这些模块允许出现未解析全局名；值为 None 表示运行时动态注入
RUNTIME_INJECTED_MODULES = {
    "backend/modules/channels/feishu.py": (
        "飞书 SDK 延迟加载：_ensure_feishu_sdk() 用 globals().update() 在运行时注入 "
        "CreateMessageRequest / Emoji / lark 等 SDK 类，目的是 provider-only / HTTP / "
        "卡片渲染这三条路径不得触发 lark_oapi 导入。"
    ),
}

# 纯静态白名单，一般无需使用
ALLOWED_UNRESOLVED = {}


def _module_level_names(tree: ast.Module) -> set:
    """收集模块顶层绑定的名字（含 if/try/with/for 内，但不进函数和类）。"""
    names = set(MODULE_DUNDERS)

    def bind_target(target):
        for sub in ast.walk(target):
            if isinstance(sub, ast.Name):
                names.add(sub.id)

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(child.name)
                continue                              # 不进函数/类体
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    if alias.name == "*":
                        continue
                    names.add(alias.asname or alias.name.split(".")[0])
                continue
            if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    bind_target(target)
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.comprehension)):
                bind_target(child.target)
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if item.optional_vars is not None:
                        bind_target(item.optional_vars)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                names.add(child.name)
            elif isinstance(child, ast.NamedExpr):
                bind_target(child.target)
            if isinstance(child, (ast.Global, ast.Nonlocal)):
                names.update(child.names)
            visit(child)

    visit(tree)
    # 函数体里写了 global X 的，也算模块级绑定
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            names.update(node.names)
    return names


def _iter_code_objects(code: types.CodeType):
    """递归取出所有嵌套 code object（函数、方法、lambda、推导式）。"""
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield const
            yield from _iter_code_objects(const)


def _runtime_injected_names(path: Path) -> set:
    """读出 globals().update({...}) 注入的名字。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    injected = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"):
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Call)
                and isinstance(owner.func, ast.Name)
                and owner.func.id == "globals"):
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Dict):
                continue
            for key in arg.keys:
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if key.value[:1].isupper() or key.value == "lark":
                    injected.add(key.value)
    return injected


def _unresolved_globals(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = path.relative_to(BACKEND.parent).as_posix()
    allowed = set(ALLOWED_UNRESOLVED.get(rel, set()))
    if rel in RUNTIME_INJECTED_MODULES:
        allowed |= _runtime_injected_names(path)
        allowed |= {"lark_oapi"}
    known = _module_level_names(tree)
    module_code = compile(source, str(path), "exec")

    missing = []
    for code in _iter_code_objects(module_code):
        seen = set()
        for ins in dis.get_instructions(code):
            if ins.opname != "LOAD_GLOBAL":
                continue
            # 3.11+ 的 LOAD_GLOBAL 直接给 argval，不能用 lstrip 按字符集裁剪
            name = ins.argval
            if not isinstance(name, str) or name in seen:
                continue
            seen.add(name)
            if name in known or hasattr(builtins, name) or name in allowed:
                continue
            missing.append(f"{path.relative_to(BACKEND.parent)}:{code.co_firstlineno} "
                           f"{code.co_name}() -> {name}")
    return missing


@pytest.mark.parametrize(
    "path",
    sorted(p for p in BACKEND.rglob("*.py") if "__pycache__" not in p.parts),
    ids=lambda p: p.relative_to(BACKEND).as_posix(),
)
def test_no_unresolved_global_names(path):
    """每个模块的每个函数体里，引用的全局名都必须能解析。"""
    missing = _unresolved_globals(path)
    assert not missing, "发现未解析的全局名（运行到该分支会 NameError）:\n" + "\n".join(missing)


# ----------------------------------------------------------------------
# Mixin 拆分专用：组合类必须能解析内部所有 self.xxx 引用
# ----------------------------------------------------------------------

CHANNEL_DIR = BACKEND / "modules" / "channels"
MIXIN_MODULES = [
    "commands.py",
    "sessions.py",
    "persistence.py",
    "turn.py",
    "direct_route.py",
    "handler.py",
]


def _collect_classes():
    classes, by_name = {}, {}
    for name in MIXIN_MODULES:
        path = CHANNEL_DIR / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            members, reads = set(), []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    members.add(item.target.id)
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Attribute)
                        and isinstance(sub.value, ast.Name)
                        and sub.value.id == "self"):
                    if isinstance(sub.ctx, ast.Store):
                        members.add(sub.attr)
                    else:
                        reads.append((sub.attr, sub.lineno))
            by_name.setdefault(node.name, set()).update(members)
            classes[(name, node.name)] = {
                "members": members,
                "reads": reads,
                "bases": [b.id for b in node.bases if isinstance(b, ast.Name)],
            }
    return classes, by_name


def test_mixin_composition_resolves_every_self_member():
    """组合类的每个 self.xxx 都必须由某个 Mixin 提供。"""
    classes, by_name = _collect_classes()
    handler = classes[("handler.py", "ChannelMessageHandler")]

    pool, frontier, seen = set(handler["members"]), list(handler["bases"]), set()
    while frontier:
        base = frontier.pop()
        if base in seen:
            continue
        seen.add(base)
        pool |= by_name.get(base, set())
        for (_, cls_name), rec in classes.items():
            if cls_name == base:
                frontier.extend(rec["bases"])

    missing = [f"handler.py:{line} self.{attr}" for attr, line in handler["reads"]
               if attr not in pool]
    assert not missing, "组合类缺少成员（调用会 AttributeError）:\n" + "\n".join(sorted(missing))
