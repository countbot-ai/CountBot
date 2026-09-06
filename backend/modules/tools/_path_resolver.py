"""工具路径统一解析（内部模块，带下划线前缀表示不对外导出）。

背景（共享层与死胡同）：
- 运行期工作空间会随配置热切换（api/settings.py -> config_loader.save_config
  -> WorkspaceManager.activate_workspace_path）。
- 工具若在构造时冻结 workspace 快照（如旧 shell.py / screenshot.py），热切换后
  仍指向旧目录，导致「截图产出 -> send_media 消费」这类跨工具链路按 CWD 或旧基准
  解析，路径基准断裂成为任务死胡同。

本模块提供唯一权威的解析入口：绝对路径原样返回，相对路径按当前工作空间解析。
"""

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
