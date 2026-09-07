"""向量存储 - 余弦相似度检索（M2 混合检索的向量索引）

设计目标（Phase 1 任务 3，implementation-plan §5）：
- numpy 优先、纯 Python 兜底：`try: import numpy` 失败时用 math 手写
  点积，保证 rag 模块「零第三方依赖」哲学不被破坏（与 jieba 同款
  可选依赖模式：不安装只是慢，不是坏）；
- 数据量级 = 全量块池（当前 1,423 块 × 1024 维 ≈ 5.8MB float32），
  暴力余弦扫描即可（单次查询 ~1.5M 次乘加，纯 Python 也在毫秒级），
  不引入 ANN 索引（规模不匹配，§1 范围纪律）；
- 持久化双格式：numpy 可用时存 .npz（chunk_ids + vectors float32[N,dim]，
  见 implementation-plan §6.2），否则 .json；load 按内容自探测格式，
  两种环境互不破坏。

与 ChunkedBM25Index 的分工：BM25 管 chunk_id → 词法倒排，
VectorStore 管 chunk_id → 向量；两者以 chunk_id 对齐，
由 service 层（任务 4）在同一 sync 事务内双写。
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as _np
except ImportError:  # 纯 Python 兜底：不安装 numpy 只是慢，不是坏
    _np = None

from loguru import logger


def default_index_filename() -> str:
    """向量索引默认文件名：numpy 可用 → .npz，否则 .json（service 层持久化用）"""
    return "vector_index.npz" if _np is not None else "vector_index.json"


class VectorStore:
    """以 chunk_id 为键的稠密向量池（余弦相似度 top-k 检索）"""

    def __init__(self, dim: Optional[int] = None):
        self.dim = dim  # 首次 add 时锁定；None 表示尚未确定
        self._ids: List[str] = []
        self._vecs: List[List[float]] = []
        self._pos: Dict[str, int] = {}  # chunk_id -> 下标（add/remove O(1) 定位）
        # 调用方元数据（如 slug→mtime 过期追踪），随索引一并持久化。
        # chunk_id 在内容变更时可能复用（同 slug#section），仅凭 id 存在
        # 判断"向量未过期"不可靠，过期判定由调用方经 meta 完成。
        self.meta: Dict[str, object] = {}

    def __len__(self) -> int:
        return len(self._ids)

    # ---------- 写入 ----------

    def add(self, chunk_id: str, vec: List[float]) -> None:
        """添加/替换向量（upsert：同 chunk_id 重复 add 覆盖旧值，幂等）"""
        if not chunk_id:
            raise ValueError("chunk_id 不能为空")
        if not vec:
            raise ValueError(f"向量不能为空：{chunk_id}")
        if self.dim is None:
            self.dim = len(vec)
        elif len(vec) != self.dim:
            raise ValueError(
                f"向量维度不符：期望 {self.dim}，实际 {len(vec)}（{chunk_id}）")

        if chunk_id in self._pos:  # upsert：原位覆盖
            self._vecs[self._pos[chunk_id]] = [float(x) for x in vec]
        else:
            self._pos[chunk_id] = len(self._ids)
            self._ids.append(chunk_id)
            self._vecs.append([float(x) for x in vec])

    def remove(self, chunk_id: str) -> bool:
        """删除向量；不存在返回 False（删除已过期 chunk 是 sync 常态，不算错误）"""
        pos = self._pos.pop(chunk_id, None)
        if pos is None:
            return False
        # 尾部元素补位，保持 O(1) 删除（顺序无关：检索按相似度排序）
        last = len(self._ids) - 1
        if pos != last:
            self._ids[pos] = self._ids[last]
            self._vecs[pos] = self._vecs[last]
            self._pos[self._ids[pos]] = pos
        self._ids.pop()
        self._vecs.pop()
        return True

    # ---------- 查询 ----------

    def search(self, query_vec: List[float], top_k: int = 6) -> List[Tuple[str, float]]:
        """余弦相似度 top-k，返回 [(chunk_id, score)] 按分数降序

        零向量（查询或库内任一方）相似度定义为 0，不抛错——
        空内容块在语料里真实存在（如纯代码围栏块）。
        """
        if self.dim is not None and len(query_vec) != self.dim:
            raise ValueError(f"查询维度不符：期望 {self.dim}，实际 {len(query_vec)}")
        if not self._ids or top_k <= 0:
            return []

        if _np is not None:
            sims = self._cosine_numpy(query_vec)
        else:
            sims = self._cosine_python(query_vec)

        # 降序取 top_k；稳定排序保证同分按入库顺序
        order = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
        return [(self._ids[i], float(sims[i])) for i in order[:top_k]]

    def _cosine_numpy(self, query_vec) -> List[float]:
        mat = _np.asarray(self._vecs, dtype=_np.float32)
        q = _np.asarray(query_vec, dtype=_np.float32)
        norms = _np.linalg.norm(mat, axis=1) * _np.linalg.norm(q)
        # 任一方为零向量 → dot 必为 0，除以 1 兜底得相似度 0
        return ((mat @ q) / _np.where(norms == 0.0, 1.0, norms)).tolist()

    def _cosine_python(self, query_vec) -> List[float]:
        q = [float(x) for x in query_vec]
        q_norm = math.sqrt(sum(x * x for x in q))
        sims = []
        for v in self._vecs:
            v_norm = math.sqrt(sum(x * x for x in v))
            if q_norm == 0.0 or v_norm == 0.0:
                sims.append(0.0)
                continue
            dot = sum(a * b for a, b in zip(v, q))
            sims.append(dot / (v_norm * q_norm))
        return sims

    # ---------- 元信息（供 service 增量同步做差集） ----------

    def has(self, chunk_id: str) -> bool:
        return chunk_id in self._pos

    def ids(self) -> List[str]:
        return list(self._ids)

    # ---------- 持久化 ----------

    def save_to_file(self, path: str) -> None:
        """numpy 可用 → .npz（§6.2：chunk_ids + vectors float32[N,dim]）；否则 .json"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if _np is not None:
            _np.savez(
                p,
                chunk_ids=_np.array(self._ids),
                vectors=_np.asarray(self._vecs, dtype=_np.float32),
                meta=_np.array([json.dumps(self.meta, ensure_ascii=False)]),
            )
        else:
            data = {"dim": self.dim, "chunk_ids": self._ids,
                    "vectors": self._vecs, "meta": self.meta}
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def load_from_file(self, path: str) -> bool:
        """加载索引；文件不存在/格式不符返回 False（上层据此重建，不算错误）

        格式按内容自探测：先试 npz（需 numpy），失败再试 json，
        保证 numpy 环境存的 .npz 在纯 Python 环境至少能明确报缺
        （返回 False 触发重建），反之 json 到处可读。
        """
        p = Path(path)
        if not p.exists():
            return False
        try:
            if _np is not None:
                try:
                    with _np.load(p, allow_pickle=False) as z:
                        ids = z["chunk_ids"].tolist()
                        vecs = z["vectors"].tolist()
                        meta = (json.loads(z["meta"].tolist()[0])
                                if "meta" in z.files else {})
                    self._reset(ids, vecs, meta)
                    return True
                except Exception:
                    pass  # 不是 npz，落到 json
            data = json.loads(p.read_text(encoding="utf-8"))
            self._reset(data["chunk_ids"], data["vectors"], data.get("meta", {}))
            return True
        except Exception as e:
            logger.warning(f"向量索引加载失败，将重建：{p}（{e}）")
            return False

    def _reset(self, ids: List[str], vecs: List[List[float]],
               meta: Optional[Dict[str, object]] = None) -> None:
        if len(ids) != len(vecs):
            raise ValueError(f"索引数据不一致：{len(ids)} ids vs {len(vecs)} vectors")
        self._ids = list(ids)
        self._vecs = [[float(x) for x in v] for v in vecs]
        self._pos = {cid: i for i, cid in enumerate(self._ids)}
        self.dim = len(self._vecs[0]) if self._vecs else None
        self.meta = dict(meta or {})
