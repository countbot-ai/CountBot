"""Reranker 客户端：调用 OpenAI 兼容 /rerank 端点做精排（roadmap §3.4 / implementation-plan §5 Phase 2）。"""

import os
from typing import List, Optional

import httpx
from loguru import logger

ENABLED_ENV = "COUNTBOT_RAG_RERANK"
BASE_URL_ENV = "COUNTBOT_RAG_RERANK_BASE_URL"
API_KEY_ENV = "COUNTBOT_RAG_RERANK_API_KEY"
MODEL_ENV = "COUNTBOT_RAG_RERANK_MODEL"

DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"

# rerank top-1 分数 ≥ 该阈值时，调用方可跳过 LLM grader（置信门控）。
# 2026-09-06 冒烟校准后默认禁用（1.01 = 永不触发）：cross-encoder 度量主题匹配而非
# 可回答性，实测无法用分数分离正负样本（与 roadmap §3.7/D2 结论一致）；机制保留，
# 待有判别力的信号出现后再启用。"单题 LLM 调用 ≤1.5"门禁因此暂不达成（实测约 2.0/题），
# 见 work-log。
RERANK_CONFIDENT_SCORE = 1.01

_TIMEOUT = 30.0
_MAX_DOC_CHARS = 2000  # 单块送入 rerank 的文本上限（防御性截断）


class RerankerClient:
    """OpenAI 兼容的 /rerank 客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = DEFAULT_MODEL,
        top_n: int = 6,
        timeout: float = _TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.top_n = top_n
        self.timeout = timeout
        # transport 仅测试注入用（httpx.MockTransport），生产恒为 None
        self._transport = transport

    async def rerank(self, query: str, chunks: List[dict]) -> List[dict]:
        """按与 query 的相关性重排 chunks，返回前 top_n 个（降序）。

        返回的块 dict 追加 "rerank_score" 字段；原 "score"（检索层排序分）
        保留不动——两者量纲不同，混用会污染下游展示与归因。
        空 chunks → 空列表；HTTP/结构异常抛 RuntimeError（调用方降级）。
        """
        if not chunks:
            return []

        documents = [
            f"{c.get('doc_title', '')} › {c.get('section', '')}\n{c.get('content', '')}"[:_MAX_DOC_CHARS]
            for c in chunks
        ]
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": min(self.top_n, len(documents)),
            "return_documents": False,
        }
        client_kwargs: dict = {"timeout": self.timeout}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(
                f"{self.base_url}/rerank",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"rerank API HTTP {resp.status_code}: {resp.text[:200]}")
        results = (resp.json() or {}).get("results")
        if not results or not isinstance(results, list):
            raise RuntimeError("rerank 响应缺少 results 字段")

        ranked: List[dict] = []
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score")
            if (not isinstance(idx, int) or not 0 <= idx < len(chunks)
                    or not isinstance(score, (int, float))):
                raise RuntimeError(f"rerank 响应条目非法：{item!r}")
            chunk = dict(chunks[idx])
            chunk["rerank_score"] = float(score)
            ranked.append(chunk)
        # 协议按相关性降序返回；再排一次 + 截断 top_n，防御实现不守约
        ranked.sort(key=lambda c: c["rerank_score"], reverse=True)
        return ranked[:self.top_n]


def build_reranker() -> Optional[RerankerClient]:
    """从环境变量构造；开关未开或 BASE_URL/API_KEY 缺失返回 None（上层回落）"""
    if os.environ.get(ENABLED_ENV, "").lower() not in ("1", "true", "yes", "on"):
        return None
    base_url = os.environ.get(BASE_URL_ENV, "").strip()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not base_url or not api_key:
        logger.warning(
            f"{ENABLED_ENV}=1 但 {BASE_URL_ENV}/{API_KEY_ENV} 未配置，rerank 不生效")
        return None
    model = os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL
    return RerankerClient(base_url, api_key, model=model)
