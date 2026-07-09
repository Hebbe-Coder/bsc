"""中英文混合分词（镜像 llm_service._tokenize，独立无重依赖）。"""
from __future__ import annotations
import re
from typing import List


def tokenize(text: str, max_length: int = 2000) -> List[str]:
    text = (text or "")[:max_length]
    tokens: List[str] = []
    for word in re.findall(r"[\u4e00-\u9fff]+", text):
        for i in range(len(word)):
            for j in range(i + 1, min(i + 3, len(word) + 1)):
                tokens.append(word[i:j])
    for word in re.findall(r"[a-zA-Z]+", text.lower()):
        if len(word) >= 2:
            tokens.append(word)
    return tokens
