"""共享模式 Wiki 合并逻辑测试。"""

from pathlib import Path

import pytest

from backend.modules.wiki.layered import LayeredWikiService
from backend.modules.wiki.service import WikiService


def _make_service(root: Path) -> WikiService:
    wiki_dir = root / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    return WikiService(wiki_dir)


def _write(service: WikiService, slug: str, title: str, content: str, tags=None) -> None:
    concepts = service._concepts_dir  # noqa: SLF001 - 测试直接落文件
    concepts.mkdir(parents=True, exist_ok=True)
    (concepts / f"{slug}.md").write_text(
        f"---\ntitle: {title}\ntags: {tags or []}\nsummary: {content[:20]}\n---\n{content}\n",
        encoding="utf-8",
    )
    service.force_sync()


@pytest.fixture()
def layered(tmp_path):
    admin = _make_service(tmp_path / "admin")
    user = _make_service(tmp_path / "user")
    _write(admin, "shared-doc", "共享文档", "管理员提供的知识", ["shared"])
    _write(user, "private-doc", "我的文档", "用户自己的知识", ["private"])
    return LayeredWikiService(user, admin), admin, user


def test_safe_md_path_rejects_traversal(tmp_path):
    from fastapi import HTTPException

    from backend.api.wiki import _safe_md_path

    concepts = tmp_path / "concepts"
    concepts.mkdir()
    assert _safe_md_path(concepts, "ok-doc").name == "ok-doc.md"

    for slug in ("../evil", "/etc/passwd", "a/b", "a\\b", "..", "."):
        with pytest.raises(HTTPException):
            _safe_md_path(concepts, slug)


def test_list_merges_admin_and_user(layered):
    service, _admin, _user = layered
    slugs = {item["slug"] for item in service.list_documents()}
    assert slugs == {"shared-doc", "private-doc"}


def test_get_document_reads_both_layers(layered):
    service, _admin, _user = layered
    assert service.get_document("shared-doc")["title"] == "共享文档"
    assert service.get_document("private-doc")["title"] == "我的文档"
    assert service.get_document("missing-doc") is None


def test_user_entry_wins_on_same_slug(tmp_path):
    admin = _make_service(tmp_path / "admin")
    user = _make_service(tmp_path / "user")
    _write(admin, "dup", "管理员版本", "admin content")
    _write(user, "dup", "用户版本", "user content")
    service = LayeredWikiService(user, admin)

    assert service.get_document("dup")["title"] == "用户版本"
    # 用户已有同名条目时不再视为只读，避免历史数据被永久锁死
    assert service.is_readonly_slug("dup") is False


def test_readonly_detection(layered):
    service, _admin, _user = layered
    assert service.is_readonly_slug("shared-doc") is True
    assert service.is_readonly_slug("private-doc") is False
    assert service.is_readonly_slug("missing-doc") is False


def test_readonly_slugs_excludes_user_overrides(layered):
    service, _admin, _user = layered
    assert service.readonly_slugs() == {"shared-doc"}


def test_search_merges_and_dedupes(layered, monkeypatch):
    """合并逻辑与底层 BM25 排序无关，这里把两层检索结果固定住。"""
    service, admin, user = layered

    monkeypatch.setattr(
        admin,
        "search_with_snippets",
        lambda query, top_k=10: [
            {"slug": "shared-doc", "title": "共享文档", "score": 1.0, "snippet": "", "tags": []},
            {"slug": "same-doc", "title": "管理员同名", "score": 0.8, "snippet": "", "tags": []},
        ],
    )
    monkeypatch.setattr(
        user,
        "search_with_snippets",
        lambda query, top_k=10: [
            {"slug": "private-doc", "title": "我的文档", "score": 1.2, "snippet": "", "tags": []},
            {"slug": "same-doc", "title": "用户同名", "score": 0.9, "snippet": "", "tags": []},
        ],
    )

    results = service.search_with_snippets("anything", top_k=10)
    slugs = [item["slug"] for item in results]

    # 合并 + 去重 + 按分数倒序
    assert set(slugs) == {"shared-doc", "private-doc", "same-doc"}
    assert slugs[0] == "private-doc"
    # 同名条目以用户层为准
    assert next(item for item in results if item["slug"] == "same-doc")["title"] == "用户同名"


def test_stats_counts_union(layered):
    service, _admin, _user = layered
    stats = service.get_stats()
    assert stats["article_count"] == 2


def test_writes_go_to_user_layer_only(layered):
    service, admin, user = layered

    # 写文件必须落在用户层目录
    assert service.concepts_dir == user._concepts_dir  # noqa: SLF001
    assert service.concepts_dir != admin._concepts_dir  # noqa: SLF001

    # 索引写入也只影响用户层
    service.add_document("new-doc", "新文档", "内容", [])
    assert "new-doc" in user._bm25.documents  # noqa: SLF001
    assert "new-doc" not in admin._bm25.documents  # noqa: SLF001

    service.remove_document("new-doc")
    assert "new-doc" not in user._bm25.documents  # noqa: SLF001


def test_force_sync_only_touches_user_layer(layered):
    service, _admin, user = layered
    stats = service.force_sync()
    assert set(stats.keys()) == {"added", "updated", "deleted"}
    # 用户层索引仍然可读
    assert user.get_document("private-doc") is not None


def test_isolated_mode_has_no_admin_layer(tmp_path):
    """隔离模式：单层服务不应看到管理员条目。"""
    user = _make_service(tmp_path / "user")
    _write(user, "private-doc", "我的文档", "内容")
    # 隔离模式不会构造 LayeredWikiService，这里直接用单层验证语义
    assert user.get_document("private-doc") is not None
    assert not hasattr(user, "readonly")


def test_api_guards_reject_readonly_slugs(layered):
    """API 层写保护：管理员条目 403，创建同名 409。"""
    from fastapi import HTTPException

    from backend.api import wiki as wiki_api

    service, _admin, _user = layered

    with pytest.raises(HTTPException) as forbidden:
        wiki_api._ensure_own_entry(service, "shared-doc")
    assert forbidden.value.status_code == 403

    # 自己的条目不受影响
    wiki_api._ensure_own_entry(service, "private-doc")

    with pytest.raises(HTTPException) as conflict:
        wiki_api._ensure_slug_not_shared(service, "shared-doc")
    assert conflict.value.status_code == 409
