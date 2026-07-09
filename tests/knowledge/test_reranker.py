import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.reranker import rrf_fuse

def test_reranker_rrf_agreement():
    fused = rrf_fuse([["a", "b", "c"], ["a", "b", "c"]])
    assert fused[0] == "a" and fused[1] == "b"

def test_reranker_rrf_scale_invariant():
    # 只吃排名不吃分数；a 在两榜都靠前 → 总体靠前
    fused = rrf_fuse([["a", "b"], ["c", "a"]])
    assert fused[0] == "a"
    # 缺失后端（空榜）仍鲁棒
    fused2 = rrf_fuse([["a", "b"], []])
    assert fused2[0] == "a"
