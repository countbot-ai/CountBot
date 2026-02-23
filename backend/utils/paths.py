"""统一路径管理 - 跨平台兼容"""

import sys
from pathlib import Path


def get_application_root() -> Path:
    """获取应用程序根目录
    
    编译版: 使用可执行文件所在目录
    开发版: 使用项目根目录
    """
    if getattr(sys, "frozen", False):
        # 编译版: _internal 目录包含所有资源
        if sys.platform == "darwin":
            # macOS onedir: CountBot.app/Contents/MacOS/CountBot -> 使用 _internal
            exe_dir = Path(sys.executable).parent
            if (exe_dir / "_internal").exists():
                root = exe_dir / "_internal"
            else:
                # BUNDLE 模式: Contents/MacOS/CountBot -> Contents/Resources/
                root = exe_dir.parent / "Resources"
        else:
            # Windows/Linux onedir: CountBot.exe 旁边的 _internal
            exe_dir = Path(sys.executable).parent
            root = exe_dir / "_internal" if (exe_dir / "_internal").exists() else exe_dir
    else:
        # 开发版: 项目根目录
        root = Path(__file__).parent.parent.parent
    
    return root.resolve()


def get_data_dir() -> Path:
    """获取数据目录（数据库、日志）"""
    data_dir = get_application_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_workspace_dir() -> Path:
    """获取工作区目录
    
    注意: 为兼容现有 skills 目录，默认返回应用根目录
    """
    return get_application_root()


def get_config_dir() -> Path:
    """获取配置目录"""
    config_dir = get_application_root() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


# 导出路径常量
APPLICATION_ROOT = get_application_root()
DATA_DIR = get_data_dir()
WORKSPACE_DIR = get_workspace_dir()
CONFIG_DIR = get_config_dir()


if __name__ == "__main__":
    print("=" * 70)
    print("CountBot 路径配置")
    print("=" * 70)
    print(f"运行模式: {'编译版' if getattr(sys, 'frozen', False) else '开发版'}")
    print(f"平台: {sys.platform}")
    print(f"\n应用程序根目录: {APPLICATION_ROOT}")
    print(f"数据目录: {DATA_DIR}")
    print(f"工作区目录: {WORKSPACE_DIR}")
    print(f"配置目录: {CONFIG_DIR}")
    print("=" * 70)
