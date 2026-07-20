"""文档切分：语义分块 + Parent-Child Chunk 结构。

生产级 RAG 的核心：
- 语义分块：按文档结构切分（需求背景/业务流程/异常流程/验收标准等）
- Parent-Child Chunk：父节点保存模块上下文，子节点用于精准检索
- 回答时携带父节点上下文，避免上下文丢失
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

SECTION_PATTERNS = [
    ("需求背景", r"需求背景|背景介绍|业务背景|项目背景"),
    ("用户故事", r"用户故事|User Story|用户场景"),
    ("业务流程", r"业务流程|流程说明|操作流程|处理流程"),
    ("异常流程", r"异常流程|错误处理|异常处理|容错机制"),
    ("接口定义", r"接口定义|API|接口说明|API文档"),
    ("验收标准", r"验收标准|验收条件|测试用例|验证标准"),
    ("违规定义", r"违规定义|违规情形|违规类型"),
    ("审核流程", r"审核流程|审核机制|审核步骤"),
    ("处罚机制", r"处罚机制|处罚等级|处罚措施"),
    ("招聘标准", r"招聘标准|录用条件|任职要求"),
    ("培训体系", r"培训体系|培训流程|岗前培训"),
    ("绩效评估", r"绩效评估|考核标准|评估维度"),
    ("流失预警", r"流失预警|离职预警|人才保留"),
    ("烘焙阶段", r"烘焙阶段|烘焙工艺|烘焙流程"),
    ("温度控制", r"温度控制|温度参数|烘焙温度"),
    ("风味特征", r"风味特征|风味描述|口感特点"),
]


@dataclass
class Chunk:
    content: str
    section: str = "正文"
    chunk_type: str = "child"
    parent_id: Optional[str] = None
    document_type: str = "general"
    meta: dict = field(default_factory=dict)


_HEADING_RE = re.compile(r"^\s*(#{1,6}\s+.+|第[一二三四五六七八九十\d]+[章节部分].*)$")


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？!?\n])", text)
    return [p for p in parts if p.strip()]


def _detect_section(line: str) -> str:
    line_lower = line.lower().strip()
    if "\u9879\u76ee\u80cc\u666f" in line_lower:
        return "\u9879\u76ee\u80cc\u666f"
    for name, pattern in SECTION_PATTERNS:
        if re.search(pattern, line_lower):
            return name
    return ""


def _detect_document_type(text: str) -> str:
    lower_text = text.lower()
    if re.search(r"prd|产品需求|需求文档", lower_text):
        return "prd"
    if re.search(r"sop|标准操作|操作流程", lower_text):
        return "sop"
    if re.search(r"管理规范|管理办法|规章制度", lower_text):
        return "policy"
    if re.search(r"工艺指南|技术手册|操作指南", lower_text):
        return "guide"
    return "general"


def chunk_text(text: str, max_chars: int = 500) -> List[Chunk]:
    text = text or ""
    lines = text.split("\n")
    chunks: List[Chunk] = []
    current_section = "正文"
    current_section_content = []
    document_type = _detect_document_type(text)
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
            chunks.append(Chunk(
                content=para,
                section=current_section,
                chunk_type="child",
                document_type=document_type,
                meta={"offset": len(chunks)}
            ))
            return
        sents = _split_sentences(para) or [para]
        piece = ""
        base = len(chunks)
        for sent in sents:
            if piece and len(piece) + len(sent) > max_chars:
                chunks.append(Chunk(
                    content=piece,
                    section=current_section,
                    chunk_type="child",
                    document_type=document_type,
                    meta={"offset": base}
                ))
                base += 1
                piece = ""
            piece += sent
            while len(piece) > max_chars:
                chunks.append(Chunk(
                    content=piece[:max_chars],
                    section=current_section,
                    chunk_type="child",
                    document_type=document_type,
                    meta={"offset": base}
                ))
                base += 1
                piece = piece[max_chars:]
        if piece:
            chunks.append(Chunk(
                content=piece,
                section=current_section,
                chunk_type="child",
                document_type=document_type,
                meta={"offset": base}
            ))

    for line in lines:
        if _HEADING_RE.match(line):
            flush()
            detected = _detect_section(line)
            if detected:
                current_section = detected
            else:
                current_section = line.strip().lstrip("#").strip() or "正文"
            current_section_content.clear()
            continue
        section_name = _detect_section(line)
        if section_name:
            flush()
            current_section = section_name
            current_section_content.clear()
            continue
        if line.strip() == "":
            flush()
            continue
        buf.append(line + "\n")
        current_section_content.append(line)
    flush()

    return chunks


def build_parent_child_chunks(text: str, max_chars: int = 500) -> List[Chunk]:
    child_chunks = chunk_text(text, max_chars)
    if not child_chunks:
        return []

    parent_chunks = []
    section_map: Dict[str, List[Chunk]] = {}

    for chunk in child_chunks:
        if chunk.section not in section_map:
            section_map[chunk.section] = []
        section_map[chunk.section].append(chunk)

    for section, children in section_map.items():
        parent_content = f"【{section}】\n"
        for child in children[:3]:
            snippet = child.content[:100]
            parent_content += f"- {snippet}...\n"

        parent_chunk = Chunk(
            content=parent_content,
            section=section,
            chunk_type="parent",
            document_type=children[0].document_type,
            meta={"child_count": len(children)}
        )
        parent_chunks.append(parent_chunk)

        for child in children:
            child.parent_id = parent_chunk.meta.get("chunk_id", "")

    result = parent_chunks + child_chunks
    for i, chunk in enumerate(result):
        chunk.meta["chunk_id"] = f"chunk-{i:04d}"

    return result
