"""共享技能分层测试：发布校验、审核分发、加载与 API 作用域。"""

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.utils.paths import APPLICATION_ROOT
from backend.modules.agent.skills import SkillsLoader
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.shared_skills import (
    SYSTEM_OWNER_ID,
    SharedSkillError,
    disabled_shared_names,
    ensure_name_available,
    is_visible_to,
    publish_skill,
    resolve_storage_path,
    review_skill,
    revoke_skill,
    set_state,
    validate_publishable,
    visible_shared_dirs,
)


def _write_skill(root: Path, name: str, body: str = "正文", extra: str = "") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: 测试技能\n{extra}---\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """把全局工作区与用户工作区都重定向到临时目录，避免污染仓库。"""
    import backend.modules.workspace as workspace_module

    global_root = tmp_path / "global"
    global_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        workspace_module, "get_global_workspace_path", lambda: global_root, raising=False
    )
    (global_root / "skills").mkdir(parents=True, exist_ok=True)
    return global_root


# ---------------------------------------------------------------------------
# 发布前校验
# ---------------------------------------------------------------------------


def test_accept_script_files(tmp_path):
    """共享快照按目录整体复制：脚本随技能一起分发，不做后缀过滤。"""
    skill_dir = _write_skill(tmp_path, "with-script")
    (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

    validate_publishable(skill_dir, "with-script")


def test_accept_binary_assets(tmp_path):
    skill_dir = _write_skill(tmp_path, "with-bin")
    (skill_dir / "tool.exe").write_bytes(b"MZ\x00\x00")

    validate_publishable(skill_dir, "with-bin")


def test_reject_always_true(tmp_path):
    skill_dir = _write_skill(tmp_path, "always-on", extra="always: true\n")

    with pytest.raises(SharedSkillError) as exc:
        validate_publishable(skill_dir, "always-on")
    assert "always" in str(exc.value)


def test_accept_name_mismatch_with_directory(tmp_path):
    """加载按目录名寻址，frontmatter 的 name 只用于展示，不阻断共享。"""
    skill_dir = _write_skill(tmp_path, "dir-name", extra="")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: other-name\ndescription: x\n---\nbody\n", encoding="utf-8"
    )

    data = validate_publishable(skill_dir, "dir-name")
    assert data["name"] == "other-name"


def test_reject_symlink(tmp_path):
    """符号链接可能指向工作区外，必须拒绝（否则会把外部文件分发出去）。"""
    outside = tmp_path / "outside-secret.md"
    outside.write_text("机密内容", encoding="utf-8")

    skill_dir = _write_skill(tmp_path, "with-link")
    (skill_dir / "leak.md").symlink_to(outside)

    with pytest.raises(SharedSkillError) as exc:
        validate_publishable(skill_dir, "with-link")
    assert "符号链接" in str(exc.value)


def test_accept_clean_markdown_skill(tmp_path):
    skill_dir = _write_skill(tmp_path, "clean-skill")
    (skill_dir / "notes.md").write_text("补充说明", encoding="utf-8")
    (skill_dir / "data.json").write_text('{"a": 1}', encoding="utf-8")

    data = validate_publishable(skill_dir, "clean-skill")
    assert data["name"] == "clean-skill"


# ---------------------------------------------------------------------------
# 发布 / 审核 / 撤回
# ---------------------------------------------------------------------------


async def _make_user(session, username: str) -> AuthUser:
    from backend.models.user import User

    user_id = str(uuid.uuid4())
    session.add(
        User(
            id=user_id,
            username=username,
            password_hash="x",
            role="user",
            status="active",
        )
    )
    await session.commit()
    return AuthUser(id=user_id, username=username, role="user", status="active")


@pytest_asyncio.fixture
async def db():
    """真实库会话；用后清掉本次测试写入的技能登记与用户，避免污染开发库。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.skill import SkillRegistry, UserSkillState
    from backend.models.user import User

    await init_db()
    async with AsyncSessionLocal() as session:
        yield session

    async with AsyncSessionLocal() as session:
        for row in (await session.execute(select(SkillRegistry))).scalars().all():
            await session.delete(row)
        for row in (await session.execute(select(UserSkillState))).scalars().all():
            await session.delete(row)
        for row in (await session.execute(select(User))).scalars().all():
            if row.username.startswith(("author_", "viewer_", "allowed_", "other_", "user_")):
                await session.delete(row)
        await session.commit()
        # 清理会话缓存，避免残留 token
        from backend.modules.auth.utils import revoke_all_sessions

        for name in ("author", "viewer", "allowed", "other"):
            revoke_all_sessions(name)


@pytest.mark.asyncio
async def test_publish_review_and_distribute(workspace, db, monkeypatch):
    """发布 -> 审核通过 -> 快照落地 -> 对其他用户可见。"""
    import backend.modules.workspace as workspace_module

    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    viewer = await _make_user(db, f"viewer_{uuid.uuid4().hex[:6]}")

    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module,
        "resolve_user_workspace",
        lambda user: author_ws if user.id == author.id else workspace / ".users" / "x",
        raising=False,
    )
    _write_skill(author_ws / "skills", "shared-clean")

    row = await publish_skill(db, author, "shared-clean")
    assert row.status == "pending"
    assert row.version == 1
    snapshot = resolve_storage_path(row.storage_path)
    assert snapshot is not None and (snapshot / "shared-clean" / "SKILL.md").is_file()
    assert str(row.storage_path).startswith(".shared-skills/")

    # 快照根目录必须能被 SkillsLoader 按工作区同样的规则扫到
    loader = SkillsLoader(
        workspace / ".users" / "empty" / "workspace" / "skills",
        external_skills_dirs=[],
        shared_skills_dirs=[snapshot],
        include_builtin=False,
    )
    shared = loader.get_skill("shared-clean")
    assert shared is not None and shared.source == "shared"

    # 未审核通过前不可见
    assert await visible_shared_dirs(db, viewer) == []

    await review_skill(db, AuthUser(id="admin", username="admin", role="admin"), row.id, approved=True)
    dirs = await visible_shared_dirs(db, viewer)
    assert len(dirs) == 1 and dirs[0] == snapshot


@pytest.mark.asyncio
async def test_reject_then_revoked_is_not_distributed(workspace, db, monkeypatch):
    import backend.modules.workspace as workspace_module

    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    viewer = await _make_user(db, f"viewer_{uuid.uuid4().hex[:6]}")
    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module, "resolve_user_workspace", lambda user: author_ws, raising=False
    )
    _write_skill(author_ws / "skills", "rejected-skill")

    row = await publish_skill(db, author, "rejected-skill")
    admin = AuthUser(id="admin", username="admin", role="admin")

    await review_skill(db, admin, row.id, approved=False, reason="含不当内容")
    refreshed = await db.get(type(row), row.id)
    assert refreshed.status == "rejected"
    assert "不当内容" in (refreshed.reject_reason or "")
    assert await visible_shared_dirs(db, viewer) == []

    # 重新提交 -> 版本递增
    row2 = await publish_skill(db, author, "rejected-skill")
    assert row2.id == row.id and row2.version == 2
    await review_skill(db, admin, row.id, approved=True)
    assert len(await visible_shared_dirs(db, viewer)) == 1

    # 撤回后不再分发
    await revoke_skill(db, admin, row.id, "发现风险")
    refreshed = await db.get(type(row), row.id)
    assert refreshed.status == "revoked"
    assert await visible_shared_dirs(db, viewer) == []
    # 快照保留，便于审计
    assert resolve_storage_path(refreshed.storage_path) is not None


@pytest.mark.asyncio
async def test_audience_limits_visibility(workspace, db, monkeypatch):
    import backend.modules.workspace as workspace_module

    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    allowed = await _make_user(db, f"allowed_{uuid.uuid4().hex[:6]}")
    other = await _make_user(db, f"other_{uuid.uuid4().hex[:6]}")
    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module, "resolve_user_workspace", lambda user: author_ws, raising=False
    )
    _write_skill(author_ws / "skills", "scoped-skill")

    row = await publish_skill(db, author, "scoped-skill", audience_ids=[allowed.id])
    await review_skill(db, AuthUser(id="admin", username="admin", role="admin"), row.id, approved=True)

    refreshed = await db.get(type(row), row.id)
    assert is_visible_to(refreshed, allowed) is True
    assert is_visible_to(refreshed, other) is False
    assert len(await visible_shared_dirs(db, allowed)) == 1
    assert await visible_shared_dirs(db, other) == []


@pytest.mark.asyncio
async def test_user_disable_filters_shared_skill(workspace, db, monkeypatch):
    import backend.modules.workspace as workspace_module

    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    viewer = await _make_user(db, f"viewer_{uuid.uuid4().hex[:6]}")
    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module, "resolve_user_workspace", lambda user: author_ws, raising=False
    )
    _write_skill(author_ws / "skills", "toggle-skill")

    row = await publish_skill(db, author, "toggle-skill")
    await review_skill(db, AuthUser(id="admin", username="admin", role="admin"), row.id, approved=True)

    assert await disabled_shared_names(db, viewer) == set()
    await set_state(db, viewer, row.id, False)
    assert await disabled_shared_names(db, viewer) == {"toggle-skill"}


@pytest.mark.asyncio
async def test_name_conflict_with_system_skill(workspace, db):
    """系统技能已占用的名字不允许再创建/发布。"""
    _write_skill(workspace / "skills", "system-taken")

    user = await _make_user(db, f"user_{uuid.uuid4().hex[:6]}")
    with pytest.raises(SharedSkillError) as exc:
        await ensure_name_available(db, "system-taken", user)
    assert "系统技能" in str(exc.value)

    # 不冲突的名字放行
    await ensure_name_available(db, "free-name", user)


@pytest.mark.asyncio
async def test_empty_audience_means_nobody_not_everyone(workspace, db, monkeypatch):
    """显式传空数组应表示「谁都不发」，不能与「不传 = 全站」混为一谈。"""
    import backend.modules.workspace as workspace_module

    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    other = await _make_user(db, f"other_{uuid.uuid4().hex[:6]}")
    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module, "resolve_user_workspace", lambda user: author_ws, raising=False
    )
    _write_skill(author_ws / "skills", "nobody-skill")

    row = await publish_skill(db, author, "nobody-skill", audience_ids=[])
    await review_skill(db, AuthUser(id="admin", username="admin", role="admin"), row.id, approved=True)

    refreshed = await db.get(type(row), row.id)
    assert refreshed.audience_json == "[]"
    assert is_visible_to(refreshed, other) is False
    assert await visible_shared_dirs(db, other) == []
    # 作者本人始终可见
    assert is_visible_to(refreshed, author) is True


@pytest.mark.asyncio
async def test_publish_rejects_name_taken_by_approved_skill(workspace, db, monkeypatch):
    """同名技能已被批准后，第二个用户不能再发布同名技能。"""
    import backend.modules.workspace as workspace_module

    admin = AuthUser(id="admin", username="admin", role="admin")
    author_a = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    author_b = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")

    ws_a = workspace / ".users" / "a" / "workspace"
    ws_b = workspace / ".users" / "b" / "workspace"
    monkeypatch.setattr(
        workspace_module,
        "resolve_user_workspace",
        lambda user: ws_a if user.id == author_a.id else ws_b,
        raising=False,
    )
    _write_skill(ws_a / "skills", "dup-name")
    _write_skill(ws_b / "skills", "dup-name")

    first = await publish_skill(db, author_a, "dup-name")
    await review_skill(db, admin, first.id, approved=True)

    with pytest.raises(SharedSkillError) as exc:
        await publish_skill(db, author_b, "dup-name")
    assert "已被共享技能占用" in str(exc.value)


@pytest.mark.asyncio
async def test_review_rejects_duplicate_approved_name(workspace, db, monkeypatch):
    """审核是分发前最后一道闸门：并发绕过了发布检查时也要拦住同名。"""
    from backend.models.skill import SkillRegistry

    import backend.modules.workspace as workspace_module

    admin = AuthUser(id="admin", username="admin", role="admin")
    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module, "resolve_user_workspace", lambda user: author_ws, raising=False
    )
    _write_skill(author_ws / "skills", "raced-name")

    # 直接造出「同名已批准」+「同名待审核」两条记录，模拟发布检查被绕过
    approved = SkillRegistry(
        id=str(uuid.uuid4()),
        owner_id="someone-else",
        name="raced-name",
        scope="user",
        visibility="shared",
        status="approved",
        storage_path=".shared-skills/x/1",
    )
    pending = SkillRegistry(
        id=str(uuid.uuid4()),
        owner_id=author.id,
        name="raced-name",
        scope="user",
        visibility="shared",
        status="pending",
        storage_path=".shared-skills/y/1",
    )
    db.add(approved)
    db.add(pending)
    await db.commit()

    with pytest.raises(SharedSkillError) as exc:
        await review_skill(db, admin, pending.id, approved=True)
    assert "已批准" in str(exc.value)


@pytest.mark.asyncio
async def test_set_state_rejects_invisible_skill(workspace, db, monkeypatch):
    """不能给未分发给自己、也不属于自己的技能写启用状态。"""
    import backend.modules.workspace as workspace_module

    author = await _make_user(db, f"author_{uuid.uuid4().hex[:6]}")
    outsider = await _make_user(db, f"other_{uuid.uuid4().hex[:6]}")
    author_ws = workspace / ".users" / author.id / "workspace"
    monkeypatch.setattr(
        workspace_module, "resolve_user_workspace", lambda user: author_ws, raising=False
    )
    _write_skill(author_ws / "skills", "private-pending")

    # 仍是 pending，未分发
    row = await publish_skill(db, author, "private-pending")
    with pytest.raises(SharedSkillError):
        await set_state(db, outsider, row.id, False)


# ---------------------------------------------------------------------------
# 加载器
# ---------------------------------------------------------------------------


def test_loader_mounts_shared_snapshot_readonly(tmp_path):
    ws = tmp_path / "workspace"
    _write_skill(ws / "skills", "mine")
    shared_root = tmp_path / "snap"
    _write_skill(shared_root, "team-skill")

    loader = SkillsLoader(
        ws / "skills",
        external_skills_dirs=[],
        shared_skills_dirs=[shared_root],
        # 必须显式关闭内置目录，否则会回落到仓库默认目录
        include_builtin=False,
    )

    assert loader.get_skill("mine").source == "workspace"
    shared = loader.get_skill("team-skill")
    assert shared is not None and shared.source == "shared"
    assert shared.enabled is True


def test_loader_extra_disabled_skills(tmp_path):
    ws = tmp_path / "workspace"
    shared_root = tmp_path / "snap"
    _write_skill(shared_root, "team-skill")

    loader = SkillsLoader(
        ws / "skills",
        external_skills_dirs=[],
        shared_skills_dirs=[shared_root],
        extra_disabled_skills={"team-skill"},
        include_builtin=False,
    )

    assert loader.get_skill("team-skill").enabled is False


def test_loader_skips_builtin_when_not_shared(tmp_path):
    """隔离模式：include_builtin=False 时完全不加载内置技能目录。"""
    ws = tmp_path / "workspace"
    loader = SkillsLoader(
        ws / "skills",
        external_skills_dirs=[],
        shared_skills_dirs=[],
        include_builtin=False,
    )
    # 只应看到工作区里的技能（此处为空），不得回落默认内置目录
    assert loader.list_skills() == []
    assert loader.builtin_skills is None


# ---------------------------------------------------------------------------
# API 作用域回归
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_api_scoped_to_user_workspace(workspace):
    """回归：普通用户调 /api/skills 不应看到管理员工作区的技能。"""
    import backend.modules.workspace as workspace_module
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import (
        create_session,
        hash_password,
        revoke_all_sessions,
        revoke_sessions_for_user_id,
    )
    from backend.modules.multiuser.settings import invalidate_cache, load_settings, save_settings

    # 管理员工作区里有一个"机密"技能
    _write_skill(workspace / "skills", "admin-only-skill")

    original_settings = await load_settings(use_cache=False)
    await save_settings(mode="isolated", enabled=True)
    invalidate_cache()

    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__shared_skill_admin__", hash_password("test-placeholder"))

    user_id = str(uuid.uuid4())
    username = f"__skill_scope_{user_id[:8]}"
    user_ws = workspace / ".users" / user_id / "workspace"
    monkeypatch_ws = workspace_module.resolve_user_workspace
    workspace_module.resolve_user_workspace = lambda user: (
        user_ws if getattr(user, "id", None) == user_id else monkeypatch_ws(user)
    )

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    username=username,
                    password_hash=hash_password("test-placeholder"),
                    role="user",
                    status="active",
                )
            )
            await session.commit()

        _write_skill(user_ws / "skills", "my-own-skill")

        token = create_session(username, user_id=user_id)
        client = TestClient(app)
        response = client.get(
            "/api/skills", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        names = {item["name"] for item in response.json()["skills"]}
        assert "my-own-skill" in names
        assert "admin-only-skill" not in names
    finally:
        workspace_module.resolve_user_workspace = monkeypatch_ws
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)
                await session.commit()
        revoke_sessions_for_user_id(user_id)
        revoke_all_sessions(username)
        if not original_hash:
            await save_credentials(original_username, original_hash)
        await save_settings(mode=original_settings.mode, enabled=original_settings.enabled)
        invalidate_cache()


@pytest.mark.asyncio
async def test_admin_publish_is_immediately_shared(workspace, db, monkeypatch):
    """管理员发布即分发：管理员自己就是审核方，不应卡在待审状态。"""
    import backend.modules.workspace as workspace_module

    admin = AuthUser(id="admin", username="admin", role="admin")
    viewer = await _make_user(db, f"viewer_{uuid.uuid4().hex[:6]}")

    admin_ws = workspace / "admin_ws"
    monkeypatch.setattr(
        workspace_module,
        "resolve_user_workspace",
        lambda user: admin_ws,
        raising=False,
    )
    _write_skill(admin_ws / "skills", "admin-shared")

    row = await publish_skill(db, admin, "admin-shared")
    assert row.status == "approved"
    assert row.owner_id == SYSTEM_OWNER_ID
    assert row.visibility == "shared"

    # 其他用户可见，无需再走审核
    dirs = await visible_shared_dirs(db, viewer)
    assert len(dirs) == 1


def test_bundled_skill_names_detects_shipped_skills():
    """内置技能名来自随应用分发的目录，用于区分「用户自建」与「初始化播种」。"""
    from backend.api.skills import _bundled_skill_names

    names = _bundled_skill_names()
    assert isinstance(names, set)
    # 分发目录存在时必然非空；不存在时退化为空集，不应抛错
    if (APPLICATION_ROOT / "workspace" / "skills").is_dir():
        assert names
