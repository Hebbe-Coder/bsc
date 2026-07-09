"""文档切分：按段落/标题结构 + 长度上限切分为 Chunk。"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    content: str
    section: str = "正文"
    meta: dict = field(default_factory=dict)


_HEADING_RE = re.compile(r"^\s*(#{1,6}\s+.+|第[一二三四五六七八九十\d]+[章节部分].*)$")


def _split_sentences(text: str) -> List[str]:
    # 以中文/英文句号、问号、叹号、换行切句，保留标点
    parts = re.split(r"(?<=[。！？!?\n])", text)
    return [p for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int = 500) -> List[Chunk]:
    text = text or ""
    lines = text.split("\n")
    chunks: List[Chunk] = []
    current_section = "正文"
    buf: List[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        para = "".join(buf).strip()
        buf = []
        if not para:
            return
        if len(para) <= max_chars:
            chunks.append(Chunk(content=para, section=current_section,
                                meta={"offset": len(chunks)}))
            return
        # 超长段落：先按句分组，再以 max_chars 硬上限兜底（无标点也必切）
        sents = _split_sentences(para) or [para]
        piece = ""
        base = len(chunks)
        for sent in sents:
            if piece and len(piece) + len(sent) > max_chars:
                chunks.append(Chunk(content=piece, section=current_section,
                                    meta={"offset": base}))
                base += 1
                piece = ""
            piece += sent
            while len(piece) > max_chars:
                chunks.append(Chunk(content=piece[:max_chars], section=current_section,
                                    meta={"offset": base}))
                base += 1
                piece = piece[max_chars:]
        if piece:
            chunks.append(Chunk(content=piece, section=current_section,
                                meta={"offset": base}))

    for line in lines:
        if _HEADING_RE.match(line):
            flush()
            current_section = line.strip().lstrip("#").strip() or "正文"
            continue
        if line.strip() == "":
            flush()
            continue
        buf.append(line + "\n")
    flush()
    return chunks
