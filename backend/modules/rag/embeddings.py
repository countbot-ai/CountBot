"""Embedding 客户端：调用 OpenAI 兼容 /v1/embeddings 端点做向量化（implementation-plan §5 Phase 1 任务 2）。"""

import os
from typing import List, Optional

import httpx
from loguru import logger

# 环境变量定义见 implementation-plan §7
BASE_URL_ENV = "COUNTBOT_RAG_EMBEDDING_BASE_URL"
API_KEY_ENV = "COUNTBOT_RAG_EMBEDDING_API_KEY"
MODEL_ENV = "COUNTBOT_RAG_EMBEDDING_MODEL"
DIM_ENV = "COUNTBOT_RAG_EMBEDDING_DIM"

DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_DIM = 1024
BATCH_SIZE = 16  # 单次请求 input 上限（OpenAI 兼容端点惯例）
_TIMEOUT = 60.0


class EmbeddingClient:
    """OpenAI 兼容嵌入客户端，异步无状态，可安全复用。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = DEFAULT_MODEL,
        dim: int = DEFAULT_DIM,
        timeout: float = _TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.timeout = timeout
        # transport 仅测试注入用（httpx.MockTransport），生产恒为 None
        self._transport = transport

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入：按 ≤BATCH_SIZE 切批，返回与输入同序的向量列表"""
        if not texts:
            return []
        vectors: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start:start + BATCH_SIZE]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def embed_query(self, text: str) -> List[float]:
        """单条查询嵌入 = embed_texts([text])[0]"""
        return (await self.embed_texts([text]))[0]

    async def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": batch}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        client_kwargs: dict = {"timeout": self.timeout}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(f"{self.base_url}/embeddings",
                                     json=payload, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(
                f"embedding API HTTP {resp.status_code}: {resp.text[:200]}")
        data = (resp.json() or {}).get("data")
        if not data or len(data) != len(batch):
            got = len(data) if data else 0
            raise RuntimeError(f"embedding 响应条数不符：期望 {len(batch)}，实际 {got}")

        # OpenAI 兼容格式每条带 index，按 index 归位防乱序
        ordered: List[Optional[List[float]]] = [None] * len(batch)
        for item in data:
            vec = item.get("embedding")
            if not vec or len(vec) != self.dim:
                got = len(vec) if vec else 0
                raise ValueError(
                    f"嵌入维度不符：期望 {self.dim}，实际 {got}"
                    f"（model={self.model}，检查 {DIM_ENV} 配置）")
            idx = item.get("index")
            if not isinstance(idx, int) or not 0 <= idx < len(batch) or ordered[idx] is not None:
                raise RuntimeError(f"embedding 响应 index 缺失/越界/重复：{idx!r}")
            ordered[idx] = vec
        if any(v is None for v in ordered):
            raise RuntimeError("embedding 响应 index 缺失或不连续")
        return ordered


def build_embedding_client() -> Optional[EmbeddingClient]:
    """从环境变量构造客户端；BASE_URL / API_KEY 任一缺失返回 None（上层回落 BM25）"""
    base_url = os.environ.get(BASE_URL_ENV, "").strip()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not base_url or not api_key:
        return None

    model = os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL
    raw_dim = os.environ.get(DIM_ENV, "").strip()
    try:
        dim = int(raw_dim) if raw_dim else DEFAULT_DIM
    except ValueError:
        logger.warning(f"{DIM_ENV}={raw_dim} 非法，回落默认 {DEFAULT_DIM}")
        dim = DEFAULT_DIM

    return EmbeddingClient(base_url, api_key, model=model, dim=dim)
