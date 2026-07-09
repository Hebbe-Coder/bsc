"""导出层边界纯函数库：定界（有界/类型安全/编码干净）+ HTML 转义。
所有函数永不抛异常；不可强制的值产出安全占位。"""
from __future__ import annotations

import html as _html
from typing import Any, List, Tuple

MAX_TEXT_LEN = 2000
MAX_LIST_ITEMS = 200
PLACEHOLDER_NONE = "—"


def _decode_bytes(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("utf-8", "replace")


def coerce_str(v: Any) -> str:
    """任意值安全转 str：None→占位符，bytes→UTF-8 解码，其余 str()。"""
    if v is None:
        return PLACEHOLDER_NONE
    if isinstance(v, bytes):
        return _decode_bytes(v)
    return str(v)


def strip_control(s: Any) -> str:
    """删控制字符（\\x00-\\x1f 除 \\n \\t），去 BOM；非 str 先 coerce。"""
    s = coerce_str(s)
    s = s.replace("\ufeff", "")
    return "".join(
        ch for ch in s
        if not (ord(ch) <= 0x1f and ch not in ("\n", "\t"))
    )


def truncate_text(s: Any, max_len: int = MAX_TEXT_LEN) -> str:
    """定界文本：coerce + 去控制字符，超阈值截断并加标记。"""
    s = strip_control(s)
    n = len(s)
    if n > max_len:
        return s[:max_len] + f"…（已截断，原文 {n} 字）"
    return s


def cap_list(items: List[Any], max_items: int = MAX_LIST_ITEMS) -> Tuple[List[Any], int]:
    """定界列表：超过阈值取前 N 条，返回 (capped, omitted_count)。"""
    if len(items) <= max_items:
        return items, 0
    return list(items[:max_items]), len(items) - max_items


def normalize_text(s: Any) -> str:
    """编码清洗：去 BOM、bytes 安全解码、控制字符剥离（不截断）。"""
    return strip_control(s)


def escape_html(s: Any) -> str:
    """HTML 转义，供 html_exporter 插值使用（quote=True）。"""
    return _html.escape(str(s), quote=True)
