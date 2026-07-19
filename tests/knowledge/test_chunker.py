import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.chunker import chunk_text

def test_chunker_basic():
    text = "# 项目背景\n这是关于内容安全平台的业务系统。内容安全平台用于过滤违规信息。\n\n# 核心目标\n提升审核效率，降低人工成本。"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].section == "项目背景"
    assert "内容安全平台" in chunks[0].content
    assert chunks[1].section == "核心目标"
    assert "审核效率" in chunks[1].content

def test_chunker_long_paragraph():
    text = "内容" * 600  # 1200 字，超 500 上限
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.section == "正文"
        assert "offset" in c.meta
    # offset 连续
    offsets = [c.meta["offset"] for c in chunks]
    assert offsets == sorted(offsets)
