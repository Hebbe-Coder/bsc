"""工具函数模块

提供统一的工具函数：
- UUID生成
- JSON序列化/反序列化
- 时间格式化
- 哈希计算
- 字符串处理
"""
from .common import (
    generate_id,
    generate_short_id,
    json_dumps,
    json_loads,
    format_datetime,
    get_now,
    get_now_timestamp,
    hash_content,
    truncate_string,
    safe_get,
    deep_merge,
    flatten_dict,
)