"""M1 开关回归测试：COUNTBOT_RAG_CHUNKS 未启用时与旧（文档级）行为一致

这是"零行为变化"承诺的证据：
1. 开关 OFF 时不实例化 RagService、不 import rag 模块（投毒验证）；
2. OFF 路径的 search/ask 输出 = 纯文档级 BM25 结果（与直接调 WikiService 一致）；
3. 开关 ON 时确实切换到块级路径（输出格式不同、含 [slug#section] 溯源）；
4. RagService 依赖显式注入（构造签名）、on_document_added 只重建单文档。
"""

import asyncio
import sys
import types
from pathlib import Path

import frontmatter
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.wiki.service import WikiService
from backend.modules.wiki.tool import WikiTool, _rag_chunks_enabled


SAMPLE_DEPLOY = """介绍如何部署 CountBot。

## Docker 部署

使用 docker-compose 一键启动，命令为 docker compose up -d。
"""

SAMPLE_MEMORY = """记忆存储在 memory.md 文件中，按会话隔离。

## 检索

支持按关键词检索历史记忆。
"""


def write_concept(wiki_dir: Path, slug: str, title: str, content: str, tags=None):
    """写入一篇带 frontmatter 的 wiki 文档（与 tool._handle_create 同构）"""
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(content)
    post.metadata["title"] = title
    post.metadata["tags"] = list(tags or [])
    post.metadata["summary"] = content[:200].strip()
    (concepts / f"{slug}.md").write_text(frontmatter.dumps(post), encoding="utf-8")


@pytest.fixture
def wiki_dir(tmp_path):
    d = tmp_path / "wiki"
    write_concept(d, "deploy", "部署指南", SAMPLE_DEPLOY, ["ops"])
    write_concept(d, "memory", "记忆系统", SAMPLE_MEMORY, ["core"])
    return d


@pytest.fixture
def no_rag_env(monkeypatch):
    monkeypatch.delenv("COUNTBOT_RAG_CHUNKS", raising=False)


@pytest.fixture
def rag_env(monkeypatch):
    monkeypatch.setenv("COUNTBOT_RAG_CHUNKS", "1")


class TestFlagParsing:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "On"])
    def test_truthy(self, monkeypatch, value):
        monkeypatch.setenv("COUNTBOT_RAG_CHUNKS", value)
        assert _rag_chunks_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "garbage"])
    def test_falsy(self, monkeypatch, value):
        monkeypatch.setenv("COUNTBOT_RAG_CHUNKS", value)
        assert _rag_chunks_enabled() is False

    def test_unset_means_off(self, no_rag_env):
        assert _rag_chunks_enabled() is False


class TestSwitchOff:
    """开关 OFF = 与旧文档级行为一致"""

    def test_no_rag_instance_when_off(self, wiki_dir, no_rag_env):
        tool = WikiTool(wiki_dir)
        assert tool._rag is None

    def test_off_search_matches_doc_level_service(self, wiki_dir, no_rag_env):
        """OFF 的 search 输出必须是文档级 search_with_metadata 的纯格式化，
        不掺入任何块级逻辑。"""
        tool = WikiTool(wiki_dir)
        # 独立构造一个无 RAG 知识的 WikiService 作参照（同目录、同索引）
        reference = WikiService(wiki_dir)
        expected = reference.search_with_metadata("Docker 部署", top_k=10, min_score_ratio=0.3)

        out = tool._handle_search("Docker 部署", top_k=10)

        assert expected, "参照检索不应为空"
        assert out.startswith(f"Found {len(expected)} wiki entries for 'Docker 部署':")
        for r in expected:
            assert f"**{r['title']}**" in out
            assert r["slug"] in out
        # 块级格式的标志不应出现
        assert "matching sections" not in out
        assert "deploy#" not in out  # chunk_id 溯源标识，若出现说明走了块级

    def test_off_path_survives_broken_rag_import(self, wiki_dir, no_rag_env, monkeypatch):
        """投毒验证：rag 模块彻底损坏也不影响 OFF 路径（import 从未发生）"""
        monkeypatch.setitem(sys.modules, "backend.modules.rag.service", None)
        tool = WikiTool(wiki_dir)
        assert tool._rag is None
        out = tool._handle_search("Docker 部署", top_k=10)
        assert "Docker" in out

    def test_off_ask_falls_back_to_doc_level(self, wiki_dir, no_rag_env, monkeypatch):
        """无 LLM provider 时，ask 走旧的文档级降级路径"""
        fake_app = types.ModuleType("backend.app")
        fake_app.get_shared_provider = lambda: None
        monkeypatch.setitem(sys.modules, "backend.app", fake_app)

        tool = WikiTool(wiki_dir)
        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))
        # 旧降级 = _format_search_results：文档标题 + 正文前 300 字
        assert "部署指南" in out
        assert "matching sections" not in out


class TestSwitchOn:
    """开关 ON = 切换到块级路径"""

    def test_rag_instance_when_on(self, wiki_dir, rag_env):
        tool = WikiTool(wiki_dir)
        assert tool._rag is not None

    def test_on_search_returns_sections(self, wiki_dir, rag_env):
        tool = WikiTool(wiki_dir)
        out = tool._handle_search("Docker 部署", top_k=10)
        assert "matching sections" in out  # 块级格式
        assert "deploy#" in out  # [slug#section] 溯源

    def test_on_off_outputs_differ(self, wiki_dir, monkeypatch):
        """同一个问题，两种开关必须产生不同粒度的输出（证明开关真的生效）"""
        monkeypatch.delenv("COUNTBOT_RAG_CHUNKS", raising=False)
        off_tool = WikiTool(wiki_dir)
        monkeypatch.setenv("COUNTBOT_RAG_CHUNKS", "1")
        on_tool = WikiTool(wiki_dir)

        off_out = off_tool._handle_search("Docker 部署", top_k=10)
        on_out = on_tool._handle_search("Docker 部署", top_k=10)

        assert "wiki entries" in off_out  # 文档级
        assert "matching sections" in on_out  # 块级

    def test_on_ask_falls_back_to_chunk_search(self, wiki_dir, rag_env, monkeypatch):
        fake_app = types.ModuleType("backend.app")
        fake_app.get_shared_provider = lambda: None
        monkeypatch.setitem(sys.modules, "backend.app", fake_app)

        tool = WikiTool(wiki_dir)
        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))
        assert "matching sections" in out


class TestRagServiceInternals:
    """RagService：显式依赖注入 + 单文档重建"""

    def test_explicit_wiki_dir_dependency(self, wiki_dir):
        """构造签名要求显式 wiki_dir（不读 WikiService 私有属性）"""
        from backend.modules.rag.service import RagService

        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir)
        assert rag.stats()["total_docs"] == 2

    def test_on_document_added_rebuilds_single_doc(self, wiki_dir):
        """新增文档只重建该文档的块，不动其他文档的索引"""
        from backend.modules.rag.service import RagService

        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir)
        before = rag.stats()

        # 模拟 tool 的 create 流程：先写文件，再通知 RAG
        write_concept(wiki_dir, "newdoc", "新条目", "# 新\n\n云原生部署新方案。\n", ["new"])
        n = rag.on_document_added("newdoc")

        assert n >= 1
        assert rag._store.has_document("newdoc")
        # 旧文档的块原样保留
        assert rag._store.has_document("deploy")
        assert rag._store.has_document("memory")
        stats = rag.stats()
        assert stats["total_docs"] == before["total_docs"] + 1
        assert stats["total_chunks"] > before["total_chunks"]
        # 新内容可检索
        assert any(r["slug"] == "newdoc" for r in rag.search_chunks("云原生"))

    def test_on_document_added_replaces_old_chunks(self, wiki_dir):
        """更新文档时旧块被替换（不残留旧内容）"""
        from backend.modules.rag.service import RagService

        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir)
        assert any("docker-compose" in r["content"]
                   for r in rag.search_chunks("docker-compose 一键启动"))

        # 模拟 tool 的 update 流程：改文件 → service.add_document（失效缓存）→ 通知 RAG
        write_concept(wiki_dir, "deploy", "部署指南", "部署方式已改为 k8s helm install。\n", ["ops"])
        svc.add_document("deploy", "部署指南", "部署方式已改为 k8s helm install。\n", ["ops"])
        rag.on_document_added("deploy")

        assert all("docker-compose" not in r["content"]
                   for r in rag.search_chunks("docker-compose 一键启动"))
        assert any("helm" in r["content"] for r in rag.search_chunks("k8s helm"))


class ScriptedProvider:
    """按调用顺序返回预设响应的假 LLM provider；Exception 实例则抛出"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def chat_completion(self, prompt, **kwargs):
        self.calls.append(prompt)
        if not self.replies:
            return "DEFAULT"
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _install_provider(monkeypatch, provider):
    fake_app = types.ModuleType("backend.app")
    fake_app.get_shared_provider = lambda: provider
    monkeypatch.setitem(sys.modules, "backend.app", fake_app)


GRADING_MARK = "检索质量评估器"
REWRITE_MARK = "改写成更适合知识库关键词检索"
GEN_MARK = "请根据以下 Wiki 知识库内容回答问题"


class TestRagAskGrading:
    """块级问答的评估-路由（CRAG）行为：三段路由 + 拒答 + 全链路回退"""

    def test_grade_all_generates_directly(self, wiki_dir, rag_env, monkeypatch):
        provider = ScriptedProvider([
            '{"grade": "all", "relevant": [1, 2]}',
            "ANSWER_OK",
        ])
        _install_provider(monkeypatch, provider)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))

        assert out == "ANSWER_OK"
        assert len(provider.calls) == 2  # 评估 1 次 + 生成 1 次，无改写
        assert GRADING_MARK in provider.calls[0]
        assert GEN_MARK in provider.calls[1]
        assert "docker-compose" in provider.calls[1]  # 生成上下文含检索块

    def test_grade_partial_filters_unrelated_chunks(self, wiki_dir, rag_env, monkeypatch):
        provider = ScriptedProvider([
            '{"grade": "partial", "relevant": [1]}',
            "ANSWER_OK",
        ])
        _install_provider(monkeypatch, provider)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))

        assert out == "ANSWER_OK"
        gen_prompt = provider.calls[1]
        # 只注入编号 1 的块：无关文档（memory）不得进入生成上下文
        assert "memory.md" not in gen_prompt
        assert "检索" not in gen_prompt.split("问题")[0] or "Docker" in gen_prompt

    def test_grade_none_refuses_after_one_rewrite(self, wiki_dir, rag_env, monkeypatch):
        provider = ScriptedProvider([
            '{"grade": "none", "relevant": []}',   # 首次评估：全不相关
            "Docker 部署方法",                       # 改写
            '{"grade": "none", "relevant": []}',   # 重试评估：仍不相关
        ])
        _install_provider(monkeypatch, provider)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))

        assert "没有找到" in out
        # 评估 2 次 + 改写 1 次，绝不发起生成
        assert len(provider.calls) == 3
        assert not any(GEN_MARK in c for c in provider.calls)

    def test_grade_none_retry_then_succeeds(self, wiki_dir, rag_env, monkeypatch):
        provider = ScriptedProvider([
            '{"grade": "none", "relevant": []}',   # 首次评估：不相关
            "docker compose 部署",                   # 改写
            '{"grade": "all", "relevant": [1]}',   # 重试评估：相关
            "ANSWER_AFTER_RETRY",
        ])
        _install_provider(monkeypatch, provider)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))

        assert out == "ANSWER_AFTER_RETRY"
        assert len(provider.calls) == 4

    def test_grading_failure_falls_back_to_generation(self, wiki_dir, rag_env, monkeypatch):
        provider = ScriptedProvider([
            RuntimeError("grading exploded"),  # 评估失败 → 回退旧行为：直接生成
            "ANSWER_FALLBACK",
        ])
        _install_provider(monkeypatch, provider)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))

        assert out == "ANSWER_FALLBACK"
        assert len(provider.calls) == 2

    def test_unparseable_grade_falls_back(self, wiki_dir, rag_env, monkeypatch):
        provider = ScriptedProvider([
            "我觉得这些结果看起来都挺好的！",  # 非 JSON → 评估不可用
            "ANSWER_UNPARSED",
        ])
        _install_provider(monkeypatch, provider)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))
        assert out == "ANSWER_UNPARSED"
        assert len(provider.calls) == 2

    def test_no_provider_keeps_legacy_fallback(self, wiki_dir, rag_env, monkeypatch):
        """无 provider：评估/改写/生成全部跳过，回退块级搜索（与旧行为一致）"""
        provider = ScriptedProvider([])
        _install_provider(monkeypatch, None)
        tool = WikiTool(wiki_dir)

        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))
        assert "matching sections" in out
        assert len(provider.calls) == 0


class TestParseGrade:
    """_parse_grade：LLM 输出 → (grade, relevant_ids) 的解析契约"""

    @pytest.mark.parametrize("text,grade,rel", [
        ('{"grade": "all", "relevant": [1, 2]}', "all", [1, 2]),
        ('好的，这是我的判断：\n{"grade": "partial", "relevant": [2]}', "partial", [2]),
        ('{"grade": "NONE", "relevant": []}', "none", []),
        ('{"grade": "none"}', "none", []),
    ])
    def test_valid(self, text, grade, rel):
        assert WikiTool._parse_grade(text, 6) == (grade, rel)

    @pytest.mark.parametrize("text", [
        "",
        "完全没有 JSON",
        '{"grade": "maybe"}',
        '{"grade": "partial", "relevant": "not-a-list"}',  # relevant 非列表 → 空编号
    ])
    def test_invalid_returns_none(self, text):
        if "not-a-list" in text:
            grade, rel = WikiTool._parse_grade(text, 6)
            assert grade == "partial" and rel == []
        else:
            assert WikiTool._parse_grade(text, 6) == (None, None)

    def test_out_of_range_ids_dropped(self):
        grade, rel = WikiTool._parse_grade('{"grade": "partial", "relevant": [0, 1, 9, "2"]}', 6)
        assert grade == "partial"
        assert rel == [1, 2]
