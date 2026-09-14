"""M2 向量存储回归测试（Phase 1 任务 3）

覆盖点（implementation-plan §8）：增删 / 余弦搜索排序 / 持久化 round-trip /
纯 Python 兜底，另补：upsert 幂等 / 维度校验 / swap 删除正确性 /
零向量语义 / 双后端结果一致性 / 跨格式加载。

向量用 3 维便于手算余弦：
  a=[1,0,0]  b=[0,1,0]  c=[1,1,0]/√2  d=[-1,0,0]
对查询 [1,0,0] 的余弦期望：a=1.0 > c≈0.7071 > b=0.0 > d=-1.0
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.rag.stores.vector_store import VectorStore

NP_MOD = "backend.modules.rag.stores.vector_store"

A, B, C, D = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.7071067811865476, 0.7071067811865476, 0.0], [-1.0, 0.0, 0.0]


def build_store():
    s = VectorStore()
    s.add("doc#a", A)
    s.add("doc#b", B)
    s.add("doc#c", C)
    s.add("doc#d", D)
    return s


def disable_numpy(monkeypatch):
    monkeypatch.setattr(f"{NP_MOD}._np", None)


class TestAddRemove:
    def test_add_and_len(self):
        s = VectorStore()
        assert len(s) == 0
        s.add("x#1", A)
        s.add("x#2", B)
        assert len(s) == 2
        assert s.has("x#1") and not s.has("x#9")
        assert set(s.ids()) == {"x#1", "x#2"}

    def test_add_is_upsert(self):
        """同 chunk_id 重复 add 覆盖旧值（增量同步幂等的前提）"""
        s = VectorStore()
        s.add("x#1", A)
        s.add("x#1", B)  # 覆盖为正交向量
        assert len(s) == 1
        assert s.search(A, top_k=1) == [("x#1", pytest.approx(0.0, abs=1e-6))]

    def test_add_validates_id_and_vec(self):
        s = VectorStore()
        with pytest.raises(ValueError):
            s.add("", A)
        with pytest.raises(ValueError):
            s.add("x#1", [])

    def test_add_dim_mismatch_raises(self):
        s = VectorStore()
        s.add("x#1", A)
        with pytest.raises(ValueError, match="维度不符"):
            s.add("x#2", [1.0, 0.0])

    def test_remove_returns_and_preserves_rest(self):
        """swap 删除后剩余元素必须全部可查且分数正确"""
        s = build_store()
        assert s.remove("doc#b") is True     # 删中间元素
        assert s.remove("doc#ghost") is False
        assert len(s) == 3
        assert not s.has("doc#b")
        hits = dict(s.search(A, top_k=3))
        assert set(hits) == {"doc#a", "doc#c", "doc#d"}
        assert hits["doc#a"] == pytest.approx(1.0, abs=1e-5)


class TestSearch:
    def test_orders_by_cosine_desc(self):
        s = build_store()
        hits = s.search(A, top_k=4)
        ids = [cid for cid, _ in hits]
        assert ids == ["doc#a", "doc#c", "doc#b", "doc#d"]
        assert hits[0][1] == pytest.approx(1.0, abs=1e-5)
        assert hits[1][1] == pytest.approx(0.70710678, abs=1e-5)
        assert hits[2][1] == pytest.approx(0.0, abs=1e-5)
        assert hits[3][1] == pytest.approx(-1.0, abs=1e-5)

    def test_top_k_limit(self):
        s = build_store()
        assert len(s.search(A, top_k=2)) == 2
        assert s.search(A, top_k=0) == []

    def test_dim_mismatch_raises(self):
        s = build_store()
        with pytest.raises(ValueError, match="查询维度不符"):
            s.search([1.0, 0.0], top_k=1)

    def test_empty_store_returns_empty(self):
        assert VectorStore().search(A, top_k=3) == []

    def test_zero_vector_similarity_is_zero(self):
        """查询零向量 / 库内零向量 → 相似度 0，不抛错（纯代码块真实存在）"""
        s = VectorStore()
        s.add("x#zero", [0.0, 0.0, 0.0])
        s.add("x#a", A)
        hits = dict(s.search([0.0, 0.0, 0.0], top_k=2))
        assert hits["x#zero"] == pytest.approx(0.0, abs=1e-6)
        assert hits["x#a"] == pytest.approx(0.0, abs=1e-6)
        hits2 = dict(s.search(A, top_k=2))
        assert hits2["x#zero"] == pytest.approx(0.0, abs=1e-6)


class TestPersistence:
    def test_npz_roundtrip(self, tmp_path):
        s = build_store()
        path = tmp_path / "vector_index.npz"
        s.save_to_file(str(path))
        assert path.exists()

        s2 = VectorStore()
        assert s2.load_from_file(str(path)) is True
        assert len(s2) == 4
        assert set(s2.ids()) == set(s.ids())
        assert s2.search(A, top_k=4) == [
            (cid, pytest.approx(score, abs=1e-5))
            for cid, score in s.search(A, top_k=4)
        ]

    def test_json_roundtrip_without_numpy(self, tmp_path, monkeypatch):
        disable_numpy(monkeypatch)
        s = build_store()
        path = tmp_path / "vector_index.json"
        s.save_to_file(str(path))

        s2 = VectorStore()
        assert s2.load_from_file(str(path)) is True
        assert len(s2) == 4
        assert s2.dim == 3
        assert [cid for cid, _ in s2.search(A, top_k=4)] == ["doc#a", "doc#c", "doc#b", "doc#d"]

    def test_json_loadable_with_numpy_present(self, tmp_path, monkeypatch):
        """纯 Python 环境存的 json，numpy 环境也能读（内容自探测）"""
        disable_numpy(monkeypatch)
        s = build_store()
        path = tmp_path / "vector_index.json"
        s.save_to_file(str(path))
        monkeypatch.undo()  # 恢复 numpy

        s2 = VectorStore()
        assert s2.load_from_file(str(path)) is True
        assert len(s2) == 4

    def test_load_nonexistent_returns_false(self, tmp_path):
        assert VectorStore().load_from_file(str(tmp_path / "absent.npz")) is False

    def test_load_corrupt_file_returns_false(self, tmp_path):
        bad = tmp_path / "vector_index.npz"
        bad.write_text("this is not a valid index file", encoding="utf-8")
        assert VectorStore().load_from_file(str(bad)) is False


class TestPurePythonFallback:
    def test_backends_agree_on_results(self, monkeypatch):
        """同一份数据，numpy 与纯 Python 的检索结果必须一致"""
        s = build_store()
        numpy_hits = s.search(A, top_k=4)

        disable_numpy(monkeypatch)
        from backend.modules.rag.stores import vector_store as vs_mod
        s_py = vs_mod.VectorStore()
        for cid in s.ids():
            s_py.add(cid, s._vecs[s._pos[cid]])
        python_hits = s_py.search(A, top_k=4)

        assert [c for c, _ in numpy_hits] == [c for c, _ in python_hits]
        for (_, n), (_, p) in zip(numpy_hits, python_hits):
            assert n == pytest.approx(p, abs=1e-5)
