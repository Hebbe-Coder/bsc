"""RRF（Reciprocal Rank Fusion）融合多路排名，对分数尺度不敏感。"""
from __future__ import annotations
from typing import List, Tuple


def rrf_fuse(ranklists: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
    scores: dict = {}
    for rl in ranklists:
        for rank, cid in enumerate(rl):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])
