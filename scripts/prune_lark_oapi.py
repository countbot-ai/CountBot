#!/usr/bin/env python3
"""打包前裁剪 lark_oapi，去除 CountBot 用不到的飞书 OpenAPI 客户端代码。

背景：lark_oapi/api/__init__.py 会 eager import 全部约 59 个产品模块，
lark_oapi/event/dispatcher_handler.py 也会 wildcard import 全部产品的
processor。CountBot 只使用 im / cardkit / contact 三个产品（见
backend/modules/channels/feishu.py 的显式导入），未用模块约占 SDK 体积
的 90%，会全部进入 PyInstaller 产物。

做法：
1. 删除 lark_oapi/api/ 下保留清单之外的子包；
2. 重写 lark_oapi/api/__init__.py，只 import 保留清单；
3. 重写 lark_oapi/event/dispatcher_handler.py，只保留保留产品的
   processor wildcard import（EventDispatcherHandler 类体只依赖 core 的
   通用类型，产品类只经 wildcard 引入，删除不影响保留产品的分发）；
4. 清理残留 __pycache__。

事件分发的取舍：被裁剪产品的事件不再有注册入口；CountBot 的飞书渠道
只注册 im 事件（feishu_websocket_worker.py，其他注册名均 getattr 探测，
缺失时跳过），行为不变。

用法：在装有 lark-oapi 的打包环境里执行 ``python scripts/prune_lark_oapi.py``，
支持 --dry-run 预览。幂等，可重复执行。
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import sys
from pathlib import Path

# CountBot 飞书渠道实际使用的 api 产品模块（feishu.py 显式导入）。
KEEP_API_DIRS = ("cardkit", "contact", "im")

# dispatcher_handler.py 里 wildcard import 的行格式。
_DISPATCHER_IMPORT_RE = re.compile(r"^from (lark_oapi\.api\.[a-z_0-9]+)\.[\w.]+ import \*\s*$")

# client.py 三组按产品生成的行：service import、__init__ 声明、build() 装配。
_CLIENT_IMPORT_RE = re.compile(r"^from \.api\.([a-z_0-9]+)\.service import \w+Service\s*$")
_CLIENT_DECL_RE = re.compile(r"^        self\.([a-z][a-z_0-9]*): Optional\[\w+Service\] = None\s*$")
_CLIENT_BUILD_RE = re.compile(r"^        client\.([a-z][a-z_0-9]*) = \w+Service\(self\._config\)\s*$")


def locate_lark_package() -> Path:
    spec = importlib.util.find_spec("lark_oapi")
    if not spec or not spec.origin:
        raise SystemExit("lark_oapi 未安装到当前 Python 环境")
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
    """裁剪 dispatcher_handler.py，返回处理的 wildcard import 行数。

    generated 文件的 ``register_p2_*`` 方法把事件模型类用在方法注解里，
    类创建时会求值，因此除按保留清单过滤 wildcard import 外，还需在文件
    顶部注入 ``from __future__ import annotations``：注解延迟为字符串，
    被裁剪产品的 register 方法变成「仅调用时才报 NameError」的死方法，
    而方法体本就只在显式注册时才执行。CountBot 只注册 im 事件（含
    getattr 探测的可选注册名），行为不变。
    """
    target = event_dir / "dispatcher_handler.py"
    if not target.exists():
        return 0
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)

    if any("__future__ import annotations" in line for line in lines[:5]):
        pass
    else:
        # future import 必须位于文件第一条语句之前；generated 文件以注释开头。
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
    """按保留清单过滤 client.py 的产品 Service 行，返回删除条数。

    Client 的三个 Service 赋值位置（import / __init__ 声明 / build() 装配）
    都是每产品一行的规则生成代码，按行过滤即可；CountBot 通过
    ``client.im / client.contact / client.cardkit`` 属性调用 SDK，
    保留清单内的属性在裁剪后行为不变。
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只报告，不实际删除")
    args = parser.parse_args()

    package_dir = locate_lark_package()
    api_dir = package_dir / "api"
    event_dir = package_dir / "event"
    if not api_dir.is_dir():
        raise SystemExit(f"异常的 lark_oapi 包结构: {package_dir}")

    size_before = dir_size(package_dir)
    removed_dirs = prune_api_dir(api_dir, args.dry_run)
    rewrite_api_init(api_dir, args.dry_run)
    dropped_imports = rewrite_dispatcher(event_dir, args.dry_run)
    dropped_client_lines = rewrite_client(package_dir, args.dry_run)
    pycache_count = clean_pycache(package_dir, args.dry_run)
    size_after = size_before if args.dry_run else dir_size(package_dir)

    print(f"lark_oapi 包: {package_dir}")
    print(f"裁剪 api 子包: {[p.name for p in removed_dirs] or '(无，可能已裁剪)'}")
    print(f"dispatcher_handler 移除 wildcard import: {dropped_imports} 行")
    print(f"client.py 移除产品 Service 行: {dropped_client_lines} 行")
    print(f"清理 __pycache__: {pycache_count} 个")
    print(f"体积: {size_before / 1024 / 1024:.1f}MB -> {size_after / 1024 / 1024:.1f}MB")

    # 收尾自检：import 失败说明裁剪破坏了保留链路，打包前直接失败。
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
                "裁剪后 lark_oapi 导入失败，请勿打包：\n" + (check.stderr or "")
            )
        print("自检通过: import lark_oapi / lark_oapi.ws 正常")


if __name__ == "__main__":
    main()
