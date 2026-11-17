"""用户工作区隔离：独立根目录、旧目录迁移、删除归档与越界拒绝。"""

from pathlib import Path

import pytest

from backend.modules.workspace import (
    archive_user_workspace,
    ensure_user_workspace,
    get_effective_user_root,
    get_users_root,
    is_path_within_user_workspace,
)
from backend.modules.workspace import manager as workspace_manager_module


@pytest.fixture
def global_workspace(tmp_path, monkeypatch):
    """把全局工作区重定向到临时目录，并清空 users_root 配置。"""
    global_root = tmp_path / "workspace"
    global_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        workspace_manager_module,
        "get_global_workspace_path",
        lambda: global_root,
        raising=False,
    )

    import backend.modules.config.loader as loader_module

    monkeypatch.setattr(
        loader_module.config_loader.config.workspace,
        "users_root",
        "",
        raising=False,
    )
    return global_root


def test_users_root_is_sibling_of_global_workspace(global_workspace: Path):
    """默认用户数据根在全局工作区的**父目录**下，不嵌进管理员工作区内部。"""
    root = get_users_root()

    assert root == (global_workspace.parent / "users").resolve()
    # 关键：不在全局工作区里面，管理员浏览文件时看不到用户数据
    assert global_workspace.resolve() not in root.parents


def test_users_root_honours_config_override(global_workspace: Path, tmp_path, monkeypatch):
    """配置了 users_root 时以配置为准，可指向其他磁盘/挂载点。"""
    custom = tmp_path / "elsewhere" / "userdata"
    import backend.modules.config.loader as loader_module

    monkeypatch.setattr(
        loader_module.config_loader.config.workspace,
        "users_root",
        str(custom),
        raising=False,
    )

    assert get_users_root() == custom.resolve()


def test_ensure_user_workspace_builds_isolated_tree(global_workspace: Path):
    user_id = "user-a"
    workspace = ensure_user_workspace(user_id)

    assert workspace == (get_users_root() / user_id / "workspace").resolve()
    for sub in ("memory", "uploads", "temp", "skills", "wiki"):
        assert (workspace / sub).is_dir()


def test_legacy_nested_user_dir_is_migrated(global_workspace: Path):
    """旧版 <全局工作区>/.users/<uid> 会在首次访问时迁移到新位置。"""
    user_id = "legacy-user"
    legacy = global_workspace / ".users" / user_id
    (legacy / "workspace").mkdir(parents=True)
    (legacy / "workspace" / "marker.txt").write_text("keep", encoding="utf-8")

    root = get_effective_user_root(user_id)

    assert root == (get_users_root() / user_id).resolve()
    assert (root / "workspace" / "marker.txt").read_text(encoding="utf-8") == "keep"
    assert not legacy.exists()


def test_effective_root_prefers_new_location(global_workspace: Path):
    user_id = "both-places"
    new_root = get_users_root() / user_id
    new_root.mkdir(parents=True)
    legacy = global_workspace / ".users" / user_id
    legacy.mkdir(parents=True)

    assert get_effective_user_root(user_id) == new_root.resolve()
    # 已存在新位置时不动旧目录
    assert legacy.exists()


def test_archive_moves_workspace_into_trash(global_workspace: Path):
    user_id = "to-delete"
    ensure_user_workspace(user_id)
    (get_users_root() / user_id / "workspace" / "data.txt").write_text("x", encoding="utf-8")

    archived = archive_user_workspace(user_id)

    assert archived is not None
    assert archived.parent.name == ".trash"
    assert archived.name.startswith(user_id)
    assert (archived / "workspace" / "data.txt").is_file()
    assert not (get_users_root() / user_id).exists()


def test_archive_returns_none_without_workspace(global_workspace: Path):
    assert archive_user_workspace("never-existed") is None


def test_archive_is_idempotent_for_already_archived(global_workspace: Path):
    user_id = "double-archive"
    ensure_user_workspace(user_id)
    first = archive_user_workspace(user_id)
    assert first is not None

    # 第二次调用：原位置已不存在，返回 None 而不是再次归档
    assert archive_user_workspace(user_id) is None


def test_sanitize_rejects_path_traversal(global_workspace: Path):
    """用户 ID 只允许安全字符，纯符号 ID 直接拒绝。"""
    with pytest.raises(ValueError):
        ensure_user_workspace("../..")

    with pytest.raises(ValueError):
        ensure_user_workspace("..")


def test_is_path_within_user_workspace(global_workspace: Path):
    user_id = "scope-user"
    workspace = ensure_user_workspace(user_id)

    assert is_path_within_user_workspace(workspace / "a" / "b.txt", user_id) is True
    assert is_path_within_user_workspace(global_workspace / "admin-file.txt", user_id) is False
