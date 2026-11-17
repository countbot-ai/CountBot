"""统一路径管理。"""

import sys
from pathlib import Path


def get_runtime_root() -> Path:
    """返回当前程序的运行目录。

    编译版:
    - Windows/Linux: 可执行文件所在目录
    - macOS: .app 容器目录

    开发版:
    - 项目根目录
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            root = Path(sys.executable).parent.parent.parent
        else:
            root = Path(sys.executable).parent
    else:
        root = Path(__file__).resolve().parent.parent.parent

    return root.resolve()


def get_application_root() -> Path:
    """返回应用资源根目录。

    这个目录用于查找打包资源，如 frontend/dist、resources、内置 skills。
    """
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            root = Path(sys._MEIPASS)
        else:
            exe_dir = Path(sys.executable).parent
            if sys.platform == "darwin":
                if (exe_dir / "_internal").exists():
                    root = exe_dir / "_internal"
                else:
                    root = exe_dir.parent / "Resources"
            else:
                root = (
                    exe_dir / "_internal" if (exe_dir / "_internal").exists() else exe_dir
                )
    else:
        root = get_runtime_root()

    return root.resolve()


def get_data_dir() -> Path:
    """获取数据目录（数据库、日志等）。"""
    data_dir = get_runtime_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_workspace_dir() -> Path:
    """获取工作空间目录。"""
    workspace_dir = get_runtime_root() / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def get_config_dir() -> Path:
    """获取配置目录。"""
    config_dir = get_runtime_root() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


APPLICATION_ROOT = get_application_root()
RUNTIME_ROOT = get_runtime_root()
DATA_DIR = get_data_dir()
WORKSPACE_DIR = get_workspace_dir()
CONFIG_DIR = get_config_dir()


if __name__ == "__main__":
    print("=" * 70)
    print("CountBot 路径配置")
    print("=" * 70)
    print(f"运行模式: {'编译版' if getattr(sys, 'frozen', False) else '开发版'}")
    print(f"平台: {sys.platform}")
    print(f"\n资源根目录: {APPLICATION_ROOT}")
    print(f"运行根目录: {RUNTIME_ROOT}")
    print(f"数据目录: {DATA_DIR}")
    print(f"工作区目录: {WORKSPACE_DIR}")
    print(f"配置目录: {CONFIG_DIR}")
    print("=" * 70)
