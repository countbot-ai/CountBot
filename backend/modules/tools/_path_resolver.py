"""工具路径统一解析：绝对路径原样返回，相对路径按当前工作空间解析。"""

from pathlib import Path


def resolve_path(input_path: str | Path) -> Path:
    """统一路径解析：绝对路径直接返回，相对路径按当前工作空间解析。

    权威基准为 `backend.modules.workspace.WorkspaceManager` 单例
    （与 config_loader 保存配置时同步热切换），与 filesystem 工具
    WorkspaceValidator 动态读 config 的行为一致。

    Args:
        input_path: 输入路径（相对路径按当前工作空间解析）。

    Returns:
        解析后的绝对路径。
    """
    path = Path(input_path)
    if path.is_absolute():
        return path.resolve()

    try:
        from backend.modules.workspace import workspace_manager

        workspace = workspace_manager.workspace_path
    except Exception:
        workspace = Path.cwd()

    return (workspace / path).resolve()
