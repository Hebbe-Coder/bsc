"""通用工具函数

提供统一的工具函数，消除代码重复：
- UUID生成
- JSON序列化/反序列化
- 时间格式化
- 哈希计算
- 字符串处理
"""
import uuid
import json
import time
import hashlib
from typing import Any, Dict, Optional, List, Union


def generate_id() -> str:
    """生成标准UUID"""
    return str(uuid.uuid4())


def generate_short_id(length: int = 12) -> str:
    """生成短UUID

    Args:
        length: 短ID长度，默认12位

    Returns:
        短UUID字符串
    """
    return str(uuid.uuid4())[:length]


def json_dumps(data: Any, **kwargs) -> str:
    """安全的JSON序列化

    Args:
        data: 要序列化的数据
        **kwargs: 额外参数

    Returns:
        JSON字符串
    """
    default_kwargs = {"ensure_ascii": False, "indent": None}
    default_kwargs.update(kwargs)
    try:
        return json.dumps(data, **default_kwargs)
    except (TypeError, ValueError):
        return json.dumps(str(data), **default_kwargs)


def json_loads(data: str, default: Any = None) -> Any:
    """安全的JSON反序列化

    Args:
        data: JSON字符串
        default: 解析失败时的默认值

    Returns:
        解析后的数据
    """
    if not data:
        return default

    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default


def format_datetime(dt: Optional[Any] = None, fmt: str = "%Y-%m-%dT%H:%M:%S") -> str:
    """格式化日期时间

    Args:
        dt: 日期时间对象，如果为None则使用当前时间
        fmt: 格式化字符串

    Returns:
        格式化后的时间字符串
    """
    if dt is None:
        dt = time.localtime()
    elif isinstance(dt, (int, float)):
        dt = time.localtime(dt)
    return time.strftime(fmt, dt)


def get_now() -> str:
    """获取当前时间字符串

    Returns:
        当前时间字符串，格式：YYYY-MM-DDTHH:MM:SS
    """
    return format_datetime()


def get_now_timestamp() -> float:
    """获取当前时间戳

    Returns:
        当前时间戳（秒）
    """
    return time.time()


def hash_content(content: str, algorithm: str = "md5", length: int = 16) -> str:
    """计算内容哈希

    Args:
        content: 要哈希的内容
        algorithm: 哈希算法（md5, sha256）
        length: 返回的哈希长度

    Returns:
        哈希字符串
    """
    if algorithm == "sha256":
        hash_obj = hashlib.sha256(content.encode("utf-8"))
    else:
        hash_obj = hashlib.md5(content.encode("utf-8"))
    return hash_obj.hexdigest()[:length]


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """截断字符串

    Args:
        s: 原始字符串
        max_length: 最大长度
        suffix: 后缀（默认"..."）

    Returns:
        截断后的字符串
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def safe_get(d: Dict, path: str, default: Any = None) -> Any:
    """安全获取嵌套字典的值

    Args:
        d: 字典
        path: 路径，用"."分隔（如"a.b.c"）
        default: 默认值

    Returns:
        对应的值或默认值
    """
    keys = path.split(".")
    result = d
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    return result


def deep_merge(dest: Dict, src: Dict) -> Dict:
    """深度合并字典

    Args:
        dest: 目标字典
        src: 源字典

    Returns:
        合并后的字典
    """
    result = dest.copy()
    for key, value in src.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(d: Dict, parent_key: str = "", sep: str = ".") -> Dict:
    """扁平化嵌套字典

    Args:
        d: 嵌套字典
        parent_key: 父键
        sep: 分隔符

    Returns:
        扁平化后的字典
    """
    items = []
    for key, value in d.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        else:
            items.append((new_key, value))
    return dict(items)


RISK_TYPES = ["process_risks", "organization_risks", "system_risks", "compliance_risks"]


def flatten_risks(risk_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将嵌套的风险数据扁平化为列表

    Args:
        risk_data: 风险数据字典

    Returns:
        扁平化的风险列表
    """
    all_risks = []
    for risk_type in RISK_TYPES:
        all_risks.extend(risk_data.get(risk_type, []))
    return all_risks


def build_cache_key(prefix: str, content: str, suffix: str = "", namespace: str = "bsc", provider: str = "", template_id: str = "") -> str:
    """构建缓存键

    Args:
        prefix: 缓存前缀
        content: 内容（用于生成哈希）
        suffix: 后缀
        namespace: 命名空间
        provider: LLM提供商（用于区分不同模型输出）
        template_id: 模板ID（用于区分不同行业模板）

    Returns:
        缓存键字符串
    """
    content_hash = hash_content(content, algorithm="md5", length=16)
    provider_suffix = f":{provider}" if provider else ""
    template_suffix = f":{template_id}" if template_id else ""
    return f"{namespace}:{prefix}:{suffix}{provider_suffix}{template_suffix}:{content_hash}"