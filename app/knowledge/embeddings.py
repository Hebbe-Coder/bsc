"""Embedding 抽象：将文本批量转为稠密向量。

默认 MockEmbeddingProvider（离线确定性，非真语义，仅供测试与零配置运行）；
RemoteEmbeddingProvider 走远程 OpenAI 兼容 /v1/embeddings（OpenAI / vLLM / 任意兼容服务）。
"""
from __future__ import annotations
import hashlib
import logging
from typing import List, Optional

import httpx
import numpy as np

from app.core.config import settings
from app.knowledge.tokenize import tokenize

logger = logging.getLogger(__name__)

MOCK_DIM = 256


class EmbeddingProvider:
    """抽象基类：embed(texts) -> List[List[float]]。"""

    name: str = "base"
    dim: int = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def batch_embed(self, texts: List[str]) -> List[List[float]]:
        return self.embed(texts)


class MockEmbeddingProvider(EmbeddingProvider):
    """确定性哈希向量：离线、无依赖、测试用。非真语义。"""

    name = "mock"
    dim = MOCK_DIM

    def embed(self, texts: List[str]) -> List[List[float]]:
        out = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float64)
            for tok in tokenize(text or ""):
                # 使用非加盐的稳定哈希,保证跨进程/重启后仍确定(区别于内置 hash())
                vec[int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % self.dim] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            out.append(vec.tolist())
        return out


class RemoteEmbeddingProvider(EmbeddingProvider):
    """远程 OpenAI 兼容 /v1/embeddings（真语义）。失败即抛，由 VectorBackend 捕获降级。"""

    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str,
                 timeout: float = 30.0, http_client: Optional[httpx.Client] = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._http = http_client
        self.dim = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        body = {"model": self.model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            client = self._http or httpx.Client(timeout=self.timeout)
            try:
                resp = client.post(f"{self.base_url}/embeddings", headers=headers, json=body)
                resp.raise_for_status()
            finally:
                if self._http is None:
                    client.close()
        except httpx.HTTPError as e:
            logger.warning("embedding 请求失败: %s", e)
            raise
        try:
            data = resp.json()
        except ValueError as e:
            logger.warning("embedding 响应不是合法 JSON: %s", e)
            raise
        try:
            items = sorted(data["data"], key=lambda d: d["index"])
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("embedding 响应解析失败: %s", e)
            raise
        if vectors and self.dim == 0:
            self.dim = len(vectors[0])
        return vectors


def get_embedding_provider(provider: Optional[str] = None, **kwargs) -> EmbeddingProvider:
    name = (provider or settings.EMBEDDING_PROVIDER or "mock").lower()
    if name == "mock":
        return MockEmbeddingProvider()
    if name == "openai":
        return RemoteEmbeddingProvider(
            api_key=kwargs.get("api_key", settings.EMBEDDING_API_KEY),
            base_url=kwargs.get("base_url", settings.EMBEDDING_BASE_URL),
            model=kwargs.get("model", settings.EMBEDDING_MODEL),
            timeout=kwargs.get("timeout", 30.0),
            http_client=kwargs.get("http_client"),
        )
    raise ValueError(f"未知 EMBEDDING provider: {name}")
