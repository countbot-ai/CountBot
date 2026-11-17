"""混合检索：BM25 与 Dense 双通道经 RRF 融合（implementation-plan §5 Phase 1 任务 4）。"""

from typing import Dict, List

from loguru import logger

RRF_K = 60  # RRF 惯例常数（原论文默认），k 越大名次差异越平缓


def rrf_scores(ranked_lists: List[List[str]], k: int = RRF_K) -> Dict[str, float]:
    """各通道排名列表 → RRF 融合分 dict：score(d) = Σ 1/(k + rank_i(d))

    rank 从 1 起；同一通道内重复出现的 id 只计首次（防御脏数据）。
    纯函数、零副作用。
    """
    scores: Dict[str, float] = {}
    for ranked in ranked_lists:
        seen = set()
        for rank, doc_id in enumerate(ranked, 1):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def rrf_fusion(ranked_lists: List[List[str]], k: int = RRF_K) -> List[str]:
    """RRF 融合排序：返回按融合分降序的 id 列表（同分按首次出现顺序）"""
    scores = rrf_scores(ranked_lists, k=k)
    return sorted(scores, key=lambda d: -scores[d])


class HybridRetriever:
    """BM25 top-K + Dense top-K → RRF → top-k"""

    def __init__(self, store, vector_store, embedding_client, candidate_k: int = 50):
        """store: ChunkedBM25Index；vector_store: VectorStore；
        embedding_client: EmbeddingClient（调用方保证已配置）"""
        self._store = store
        self._vectors = vector_store
        self._embedder = embedding_client
        self.candidate_k = candidate_k  # 每通道候选池深度（对齐 §4 数据流 top-50）

    async def search(self, query: str, top_k: int = 6) -> List[dict]:
        """混合检索：返回结构与 search_chunks 一致的块列表（§6.1）。

        Dense 通道任一异常都只降级不中断（回落 BM25 排序）。
        """
        # 通道①：BM25（弱词法匹配不进候选池，语义召回由 Dense 补位）。
        # max_per_doc=0：候选池不截断单文档块数，多样性由 RRF + 精排决定
        bm25_ids = [cid for cid, _ in self._store.search(
            query, top_k=self.candidate_k, max_per_doc=0)]

        # 通道②：Dense（失败 → 空，RRF 退化为单通道；
        # 零/负相似度 = 语义无关，不进候选池——Dense 通道的噪声门）
        dense_ids: List[str] = []
        try:
            qvec = await self._embedder.embed_query(query)
            dense_hits = self._vectors.search(qvec, top_k=self.candidate_k)
            dense_ids = [cid for cid, s in dense_hits if s > 0.0]
        except Exception as e:
            logger.warning(f"Dense channel failed, degrading to BM25-only: {e}")

        if not bm25_ids and not dense_ids:
            return []

        scores = rrf_scores([bm25_ids, dense_ids])
        ranked = sorted(scores, key=lambda d: -scores[d])

        out: List[dict] = []
        for chunk_id in ranked[:top_k]:
            chunk = self._store.get_chunk(chunk_id)
            if chunk is None:
                # 向量索引与 BM25 索引漂移（同 sync 事务双写可杜绝，此处兜底）
                logger.warning(f"Hybrid hit a chunk without BM25 metadata, skipped: {chunk_id}")
                continue
            out.append({
                "chunk_id": chunk_id,
                "slug": chunk["slug"],
                "doc_title": chunk["doc_title"],
                "section": chunk["section"],
                "score": round(scores[chunk_id], 6),  # RRF 融合分
                "content": chunk["content"],
            })
        return out
