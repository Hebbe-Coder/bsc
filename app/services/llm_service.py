"""
Model Provider Layer - 大模型调用层

支持Provider（按优先级）：
    1. DeepSeek（分析类Agent，结构化输出）
    2. 豆包（Doubao / Volcengine，生成类Agent，创意写作）
    3. 元宝（Yuanbao / Tencent）
    4. Mock（不调API，用于开发/测试）

配置方式（通过config.py或.env文件）：
    LLM_PROVIDER=deepseek
    ANALYSIS_PROVIDER=deepseek    # SOP/Risk/Strategy/Optimization使用
    GENERATION_PROVIDER=doubao    # Business Understanding/Report使用

    DEEPSEEK_API_KEY=sk-xxx
    DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
    DEEPSEEK_MODEL=deepseek-chat

    DOUBAO_API_KEY=xxx
    DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
    DOUBAO_MODEL=doubao-pro-32k

    YUANBAO_API_KEY=xxx
    YUANBAO_BASE_URL=https://api.hunyuan.cloud.tencent.com/v1
    YUANBAO_MODEL=hunyuan-pro

    LLM_TIMEOUT=60
    LLM_TEMPERATURE=0.7
    LLM_MAX_TOKENS=8000

    LLM_PROVIDER=mock（默认，不调API）
"""
from __future__ import annotations
import json, os, time, logging, re, threading, traceback
from enum import Enum
from typing import Dict, Optional, Any, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Provider类型枚举"""
    DEEPSEEK = "deepseek"
    DOUBAO = "doubao"
    YUANBAO = "yuanbao"
    QWEN = "qwen"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LOCALAI = "localai"
    MOCK = "mock"


class AgentType(str, Enum):
    """Agent类型枚举"""
    ANALYSIS = "analysis"
    GENERATION = "generation"


class LLMService:
    """
    Model Provider Layer
    
    所有Agent通过此类调用大模型。
    统一接口：chat(system_prompt, user_prompt) -> dict

    支持多模型路由：
    - Analysis Agents (SOP/Risk/Strategy/Optimization) → DeepSeek
    - Generation Agents (Business Understanding/Report) → Doubao

    线程安全：
    - 使用线程本地存储，每个线程有独立实例
    - 无共享状态，避免并发问题
    """

    DOMAIN_KEYWORDS: Dict[str, List[str]] = {
        "finance": ["金融", "银行", "支付", "保险", "理财", "证券", "基金", "贷款",
                    "投资", "股票", "债券", "信托", "租赁", "征信", "结算", "交易",
                    "bank", "payment", "insurance", "finance", "investment", "stock",
                    "securities", "fund", "loan", "credit", "trade"],
        "healthcare": ["医疗", "健康", "医院", "医生", "病人", "药品", "诊断",
                       "挂号", "诊疗", "病历", "医保", "体检", "康复", "疫苗", "药房",
                       "问诊", "门诊", "住院", "手术", "护理", "影像", "检验",
                       "healthcare", "hospital", "doctor", "patient", "medicine", "diagnosis",
                       "treatment", "medical", "pharmacy", "health", "consultation", "clinic"],
        "retail": ["零售", "电商", "购物", "商品", "订单", "库存",
                   "购物车", "优惠券", "促销", "会员", "店铺", "商品管理",
                   "retail", "e-commerce", "shopping", "product", "order", "inventory",
                   "cart", "coupon", "promotion"],
        "manufacturing": ["制造", "生产", "工厂", "质检", "仓库",
                          "工艺", "设备", "产能", "工单", "装配", "零部件", "质量控制",
                          "manufacturing", "production", "factory", "quality",
                          "assembly", "equipment", "workshop"],
        "education": ["教育", "培训", "学校", "课程", "学生", "老师",
                      "学习", "考试", "作业", "在线教育", "MOOC", "题库", "培训课程",
                      "education", "training", "school", "course", "student", "teacher",
                      "learning", "exam", "online", "elearning", "tutorial"],
        "content": ["内容", "审核", "视频", "图片", "文本",
                    "媒体", "直播", "短视频", "社区", "论坛", "UGC", "PGC",
                    "content", "moderation", "video", "image", "text",
                    "media", "live", "streaming", "community", "forum"],
        "logistics": ["物流", "快递", "配送", "运输", "仓储",
                      "货运", "报关", "分拣", "冷链", "干线", "末端", "物流中心",
                      "logistics", "delivery", "shipping", "transport", "warehouse",
                      "freight", "courier"],
        "human_resource": ["人力", "招聘", "员工", "绩效", "薪酬", "考勤",
                           "HR", "入职", "离职", "福利", "社保", "人才",
                           "human resource", "HR", "recruitment", "employee", "performance",
                           "salary", "attendance", "talent"],
        "enterprise": ["企业", "公司", "组织", "管理", "办公", "OA", "ERP",
                       "CRM", "SaaS", "业务系统", "数字化", "信息化", "协作",
                       "enterprise", "company", "organization", "management", "ERP",
                       "CRM", "SaaS", "digital", "collaboration"],
        "marketing": ["营销", "广告", "推广", "品牌", "渠道", "获客",
                      "投放", "转化", "KOL", "裂变", "私域", "增长黑客",
                      "marketing", "advertising", "promotion", "brand", "channel",
                      "conversion", "campaign", "growth"],
        "energy": ["能源", "电力", "光伏", "风电", "储能", "电网",
                   "新能源", "充电桩", "碳中和", "环保", "节能减排",
                   "energy", "power", "solar", "wind", "storage", "grid",
                   "renewable", "charging", "carbon", "green"],
        "real_estate": ["房地产", "物业", "楼盘", "销售", "租赁", "中介",
                        "建筑", "装修", "物业管理", "房产交易",
                        "real estate", "property", "housing", "construction",
                        "building", "rental", "broker"],
    }

    DOMAIN_TEMPLATES: Dict[str, Dict[str, str]] = {
        "finance": {"name": "金融服务", "department": "金融部", "role_prefix": "金融", "core_objective": "风险管理与合规"},
        "healthcare": {"name": "医疗健康", "department": "医疗部", "role_prefix": "医疗", "core_objective": "患者安全与疗效"},
        "retail": {"name": "零售电商", "department": "电商部", "role_prefix": "电商", "core_objective": "用户体验与转化"},
        "manufacturing": {"name": "智能制造", "department": "生产部", "role_prefix": "制造", "core_objective": "质量与效率"},
        "education": {"name": "在线教育", "department": "教学部", "role_prefix": "教育", "core_objective": "学习效果"},
        "content": {"name": "内容安全", "department": "运营部", "role_prefix": "审核", "core_objective": "内容安全"},
        "logistics": {"name": "智慧物流", "department": "物流部", "role_prefix": "物流", "core_objective": "配送时效"},
        "human_resource": {"name": "人力资源", "department": "人事部", "role_prefix": "HR", "core_objective": "人才发展"},
        "enterprise": {"name": "企业管理", "department": "企管部", "role_prefix": "企业", "core_objective": "数字化转型"},
        "marketing": {"name": "数字营销", "department": "市场部", "role_prefix": "营销", "core_objective": "增长与转化"},
        "energy": {"name": "新能源", "department": "能源部", "role_prefix": "能源", "core_objective": "绿色低碳发展"},
        "real_estate": {"name": "房地产", "department": "房产部", "role_prefix": "房产", "core_objective": "资产运营"},
        "general": {"name": "企业服务", "department": "业务部", "role_prefix": "业务", "core_objective": "效率提升"},
    }

    _KEYWORD_DOMAIN_COUNT: Dict[str, int] = {}
    _AVG_KEYWORD_LENGTH: float = 0.0

    @classmethod
    def _precompute_keyword_stats(cls):
        """预计算关键词统计信息：关键词出现的域名数量、平均关键词长度"""
        if cls._KEYWORD_DOMAIN_COUNT:
            return

        kw_to_domains = {}
        total_length = 0
        total_count = 0

        for domain, keywords in cls.DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw not in kw_to_domains:
                    kw_to_domains[kw] = set()
                kw_to_domains[kw].add(domain)
                total_length += len(kw)
                total_count += 1

        cls._KEYWORD_DOMAIN_COUNT = {kw: len(domains) for kw, domains in kw_to_domains.items()}
        cls._AVG_KEYWORD_LENGTH = total_length / total_count if total_count > 0 else 4.0

    PROVIDERS: Dict[str, Dict[str, str]] = {
        "deepseek": {
            "env_key": "DEEPSEEK_API_KEY",
            "env_url": "DEEPSEEK_BASE_URL",
            "env_model": "DEEPSEEK_MODEL",
            "default_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-chat",
        },
        "doubao": {
            "env_key": "DOUBAO_API_KEY",
            "env_url": "DOUBAO_BASE_URL",
            "env_model": "DOUBAO_MODEL",
            "default_url": "https://ark.cn-beijing.volces.com/api/v3",
            "default_model": "doubao-pro-32k",
        },
        "yuanbao": {
            "env_key": "YUANBAO_API_KEY",
            "env_url": "YUANBAO_BASE_URL",
            "env_model": "YUANBAO_MODEL",
            "default_url": "https://api.hunyuan.cloud.tencent.com/v1",
            "default_model": "hunyuan-pro",
        },
        "qwen": {
            "env_key": "QWEN_API_KEY",
            "env_url": "QWEN_BASE_URL",
            "env_model": "QWEN_MODEL",
            "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "qwen-plus",
        },
        "ollama": {
            "env_key": "",
            "env_url": "OLLAMA_BASE_URL",
            "env_model": "OLLAMA_MODEL",
            "default_url": "http://localhost:11434/v1",
            "default_model": "qwen2.5:7b",
        },
        "vllm": {
            "env_key": "",
            "env_url": "VLLM_BASE_URL",
            "env_model": "VLLM_MODEL",
            "default_url": "http://localhost:8000/v1",
            "default_model": "",
        },
        "localai": {
            "env_key": "",
            "env_url": "LOCALAI_BASE_URL",
            "env_model": "LOCALAI_MODEL",
            "default_url": "http://localhost:8080/v1",
            "default_model": "gpt-4",
        },
    }

    AGENT_ROUTING: Dict[str, AgentType] = {
        "SOP Agent": AgentType.ANALYSIS,
        "Risk Agent": AgentType.ANALYSIS,
        "Strategy Agent": AgentType.ANALYSIS,
        "Optimization Agent": AgentType.ANALYSIS,
        "Business Understanding Agent": AgentType.GENERATION,
        "Report Composer": AgentType.GENERATION,
    }

    def __init__(self, provider: str = None):
        self.provider = provider or settings.LLM_PROVIDER
        self._configure()
        self._request_id = f"req-{threading.current_thread().ident}-{int(time.time() * 1000)}"

    def _get_provider_config(self, provider_name: str) -> Dict[str, str]:
        """从settings获取Provider配置"""
        config = self.PROVIDERS.get(provider_name)
        if not config:
            return {}

        return {
            "api_key": getattr(settings, config["env_key"], ""),
            "base_url": getattr(settings, config["env_url"], config["default_url"]),
            "model": getattr(settings, config["env_model"], config["default_model"]),
        }

    LOCAL_PROVIDERS = {"ollama", "vllm", "localai"}
    
    def _configure(self):
        """根据provider配置API参数"""
        if self.provider == ProviderType.MOCK.value:
            self.api_key = ""
            self.base_url = ""
            self.model = ProviderType.MOCK.value
            return

        config = self._get_provider_config(self.provider)
        if not config:
            logger.warning(f"Unknown provider: {self.provider}, fallback to mock")
            self.provider = ProviderType.MOCK.value
            self._configure()
            return

        self.api_key = config["api_key"]
        self.base_url = config["base_url"]
        self.model = config["model"]

        if not self.api_key and self.provider not in self.LOCAL_PROVIDERS:
            logger.warning(f"{self.provider} API key not set, fallback to mock")
            self.provider = ProviderType.MOCK.value
            self.model = ProviderType.MOCK.value
        elif self.provider in self.LOCAL_PROVIDERS:
            logger.info(f"Using local provider: {self.provider}, model: {self.model}")

    def _get_provider_for_agent(self, system_prompt: str) -> str:
        """根据Agent名称自动选择Provider（使用枚举+字典映射）"""
        agent_type = self._get_agent_type(system_prompt)
        
        if agent_type == AgentType.ANALYSIS:
            provider = settings.ANALYSIS_PROVIDER
            default_provider = ProviderType.DEEPSEEK.value
        elif agent_type == AgentType.GENERATION:
            provider = settings.GENERATION_PROVIDER
            default_provider = ProviderType.DOUBAO.value
        else:
            return self.provider
        
        if provider in self.PROVIDERS or provider == ProviderType.MOCK.value:
            logger.debug(f"Routing {agent_type.value} agent to {provider}")
            return provider
        
        logger.warning(f"Invalid provider '{provider}', using default {default_provider}")
        return default_provider

    def _get_agent_type(self, system_prompt: str) -> Optional[AgentType]:
        """快速判断Agent类型（O(1)查找）"""
        prefix_map = [
            ("你是SOP Agent", AgentType.ANALYSIS),
            ("你是Risk Agent", AgentType.ANALYSIS),
            ("你是Strategy Agent", AgentType.ANALYSIS),
            ("你是Optimization Agent", AgentType.ANALYSIS),
            ("你是Business Understanding Agent", AgentType.GENERATION),
            ("你是Report Composer", AgentType.GENERATION),
        ]
        for prefix, agent_type in prefix_map:
            if system_prompt.startswith(prefix):
                return agent_type
        return None

    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = None, max_tokens: int = None,
             use_cache: bool = True) -> dict:
        """
        调用大模型，返回结构化JSON

        Args:
            system_prompt: 系统提示词（定义Agent角色和输出格式）
            user_prompt: 用户输入（PRD内容+上下文）
            temperature: 温度（0.1=精确，0.7=创意），默认使用配置值
            max_tokens: 最大输出长度，默认使用配置值
            use_cache: 是否使用缓存，默认True

        Returns:
            dict: 大模型返回的结构化JSON，包含错误上下文（如有）
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS
        t0 = time.perf_counter()
        provider = self._get_provider_for_agent(system_prompt)
        agent_type = self._get_agent_type(system_prompt)
        
        context_info = {
            "request_id": self._request_id,
            "thread_id": threading.current_thread().ident,
            "provider": provider,
            "agent_type": agent_type.value if agent_type else "unknown",
        }

        cache_key = self._build_llm_cache_key(provider, system_prompt, user_prompt, temperature, max_tokens)
        
        if use_cache:
            cached_result = self._get_cache_result(cache_key)
            if cached_result:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                cached_result["_meta"] = {
                    **context_info, 
                    "mode": "cache", 
                    "elapsed_ms": elapsed_ms,
                    "cache_key": cache_key,
                }
                try:
                    from app.core.metrics import record_cache_operation
                    record_cache_operation("llm", hit=True)
                except Exception as e:
                    logger.warning(f"Failed to record cache hit metric: {e}")
                return cached_result

        if provider == ProviderType.MOCK.value or self.provider == ProviderType.MOCK.value:
            result = self._mock(system_prompt, user_prompt)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            result["_meta"] = {**context_info, "mode": ProviderType.MOCK.value, "elapsed_ms": elapsed_ms}
            if use_cache:
                self._set_cache_result(cache_key, result)
            return result

        try:
            result = self._call_api_with_provider(provider, system_prompt, user_prompt, temperature, max_tokens)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            result["_meta"] = {**context_info, "mode": "api", "elapsed_ms": elapsed_ms}
            
            if use_cache:
                self._set_cache_result(cache_key, result)
            
            try:
                from app.core.metrics import record_llm_call, record_cache_operation
                record_llm_call(provider, self.model, elapsed_ms)
                record_cache_operation("llm", hit=False)
            except Exception as e:
                logger.warning(f"Failed to record LLM metrics: {e}")
            
            return result
            
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            error_details = self._format_error(e)
            
            logger.error(
                f"LLM call failed - Request: {self._request_id}, "
                f"Provider: {provider}, AgentType: {agent_type}, "
                f"Error: {error_details['error']}, "
                f"Code: {error_details.get('code', 'unknown')}, "
                f"Elapsed: {elapsed_ms}ms",
                exc_info=True
            )

            fallback_result = self._mock(system_prompt, user_prompt)
            fallback_result["_meta"] = {
                **context_info,
                "mode": "fallback",
                "elapsed_ms": elapsed_ms,
                "error": error_details,
                "warning": "API call failed, using fallback mock data",
            }
            
            return fallback_result

    def _build_llm_cache_key(self, provider: str, system_prompt: str, user_prompt: str,
                             temperature: float, max_tokens: int) -> str:
        """构建LLM缓存键"""
        import hashlib
        content = f"{provider}:{system_prompt}:{user_prompt}:{temperature}:{max_tokens}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return f"llm:{provider}:{content_hash}"

    def _get_cache_result(self, cache_key: str):
        """从缓存获取结果"""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            if cache and cache.exists(cache_key):
                return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Failed to get cached result: {e}")
        return None

    def _set_cache_result(self, cache_key: str, result: dict):
        """设置缓存结果"""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            if cache:
                cache.set(cache_key, result, ttl=3600)
        except Exception as e:
            logger.warning(f"Failed to set cached result: {e}")

    def _format_error(self, exc: Exception) -> dict:
        """格式化错误信息，保留完整上下文"""
        return {
            "error": str(exc),
            "code": type(exc).__name__,
            "traceback": traceback.format_exc()[:2000],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _call_api(self, system_prompt: str, user_prompt: str,
                  temperature: float, max_tokens: int) -> dict:
        """调用API（DeepSeek/豆包/元宝都兼容OpenAI格式）"""
        return self._call_api_with_provider(self.provider, system_prompt, user_prompt, temperature, max_tokens)

    def ocr_image(self, image_base64: str, image_format: str = "png") -> dict:
        """
        使用大模型进行图片OCR识别
        
        Args:
            image_base64: 图片的base64编码字符串
            image_format: 图片格式（png/jpg/jpeg）
        
        Returns:
            dict: {"success": bool, "text": str, "error": str}
        """
        t0 = time.perf_counter()
        
        if self.provider == "mock":
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "success": True,
                "text": "【Mock OCR结果】这是一张文档图片，包含业务流程描述、风险评估内容和战略规划方案。文档标题为'企业数字化转型PRD'，主要内容涉及系统架构设计、数据流程和技术实现方案。",
                "error": "",
                "_meta": {"mode": "mock", "elapsed_ms": elapsed_ms},
            }

        try:
            return self._call_ocr_api(image_base64, image_format)
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"OCR API call failed: {e}")
            return {
                "success": True,
                "text": "【Mock OCR结果】这是一张文档图片，包含业务流程描述、风险评估内容和战略规划方案。文档标题为'企业数字化转型PRD'，主要内容涉及系统架构设计、数据流程和技术实现方案。",
                "error": str(e),
                "_meta": {"mode": "fallback", "elapsed_ms": elapsed_ms},
            }

    def _call_ocr_api(self, image_base64: str, image_format: str) -> dict:
        """调用多模态API进行OCR识别"""
        from openai import OpenAI

        provider = settings.OCR_PROVIDER
        config = self.PROVIDERS.get(provider)
        
        if not config:
            logger.warning(f"Unknown OCR provider: {provider}, fallback to doubao")
            provider = "doubao"
            config = self.PROVIDERS["doubao"]

        provider_config = self._get_provider_config(provider)
        api_key = provider_config["api_key"]
        base_url = provider_config["base_url"]
        model = provider_config["model"]

        if not api_key:
            raise ValueError(f"{provider} API key not set for OCR")

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=settings.LLM_TIMEOUT)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的OCR识别助手。请识别图片中的所有文字内容，并按照原有的格式和结构输出。保持段落、表格和列表的格式。不要添加任何额外的解释或分析。",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别图片中的所有文字内容。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_base64}",
                            },
                        },
                    ],
                },
            ],
            temperature=0,
            max_tokens=8000,
        )

        text = response.choices[0].message.content.strip()
        
        return {
            "success": True,
            "text": text,
            "error": "",
            "_meta": {
                "provider": provider,
                "mode": "api",
            },
        }

    def _call_api_with_provider(self, provider: str, system_prompt: str, user_prompt: str,
                                temperature: float, max_tokens: int) -> dict:
        """使用指定Provider调用API"""
        from openai import OpenAI, APIError, APIConnectionError, RateLimitError

        config = self.PROVIDERS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")

        provider_config = self._get_provider_config(provider)
        api_key = provider_config["api_key"]
        base_url = provider_config["base_url"]
        model = provider_config["model"]

        if not api_key:
            raise ValueError(f"{provider} API key not set")

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=settings.LLM_TIMEOUT)

        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except APIConnectionError as e:
            raise ConnectionError(f"API connection failed for {provider}: {e}") from e
        except RateLimitError as e:
            raise RuntimeError(f"Rate limit exceeded for {provider}: {e}") from e
        except APIError as e:
            raise RuntimeError(f"API error for {provider}: {e}") from e

        raw = response.choices[0].message.content.strip()
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """解析LLM返回的JSON（兼容markdown代码块）"""
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}, raw: {raw[:500]}")
            raise

    def _mock(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Mock模式 - 不调用API
        
        根据system_prompt中的Agent名称和user_prompt内容动态生成响应
        """
        sp = system_prompt
        domain_info = self._analyze_input_domain(user_prompt)

        agent_mock_map = [
            ("你是SOP Agent", self._mock_sop),
            ("你是Risk Agent", self._mock_risk),
            ("你是Strategy Agent", self._mock_strategy),
            ("你是Optimization Agent", self._mock_optimization),
            ("你是Business Understanding Agent", self._mock_business_understanding),
            ("你是Report Composer", self._mock_report_composer),
            ("你是一个专业的产品需求分析师", lambda d: self._mock_dialog_question(user_prompt)),
            ("你是一个资深的产品经理", lambda d: self._mock_prd_generation(user_prompt)),
        ]

        for agent_prefix, mock_method in agent_mock_map:
            if sp.startswith(agent_prefix):
                return mock_method(domain_info)

        return {"content": "mock response", "note": "未匹配到Agent类型"}

    def _analyze_input_domain(self, user_prompt: str) -> dict:
        """分析输入内容，提取业务领域信息"""
        domain_keywords = {
            "finance": ["金融", "银行", "支付", "保险", "理财", "证券", "基金", "贷款",
                        "投资", "股票", "债券", "信托", "租赁", "征信", "结算", "交易",
                        "bank", "payment", "insurance", "finance", "investment", "stock",
                        "securities", "fund", "loan", "credit", "trade"],
            "healthcare": ["医疗", "健康", "医院", "医生", "病人", "药品", "诊断",
                           "挂号", "诊疗", "病历", "医保", "体检", "康复", "疫苗", "药房",
                           "问诊", "门诊", "住院", "手术", "护理", "影像", "检验",
                           "healthcare", "hospital", "doctor", "patient", "medicine", "diagnosis",
                           "treatment", "medical", "pharmacy", "health", "consultation", "clinic"],
            "retail": ["零售", "电商", "购物", "商品", "订单", "物流", "库存",
                       "购物车", "优惠券", "促销", "会员", "店铺", "商品管理", "供应链",
                       "retail", "e-commerce", "shopping", "product", "order", "logistics",
                       "inventory", "cart", "coupon", "promotion", "supply"],
            "manufacturing": ["制造", "生产", "工厂", "供应链", "质检", "仓库",
                              "工艺", "设备", "产能", "工单", "装配", "零部件", "质量控制",
                              "manufacturing", "production", "factory", "supply", "quality",
                              "assembly", "equipment", "workshop"],
            "education": ["教育", "培训", "学校", "课程", "学生", "老师",
                          "学习", "考试", "作业", "在线教育", "MOOC", "题库", "培训课程",
                          "education", "training", "school", "course", "student", "teacher",
                          "learning", "exam", "online", "elearning", "tutorial"],
            "content": ["内容", "审核", "视频", "图片", "文本", "安全",
                        "媒体", "直播", "短视频", "社区", "论坛", "UGC", "PGC",
                        "content", "moderation", "video", "image", "text", "safety",
                        "media", "live", "streaming", "community", "forum"],
            "logistics": ["物流", "快递", "配送", "运输", "仓储",
                          "货运", "报关", "分拣", "冷链", "干线", "末端", "物流中心",
                          "logistics", "delivery", "shipping", "transport", "warehouse",
                          "freight", "courier"],
            "human_resource": ["人力", "招聘", "员工", "绩效", "薪酬", "考勤",
                               "HR", "入职", "离职", "培训", "福利", "社保", "人才",
                               "human resource", "HR", "recruitment", "employee", "performance",
                               "salary", "attendance", "talent"],
            "enterprise": ["企业", "公司", "组织", "管理", "办公", "OA", "ERP",
                           "CRM", "SaaS", "业务系统", "数字化", "信息化", "协作",
                           "enterprise", "company", "organization", "management", "ERP",
                           "CRM", "SaaS", "digital", "collaboration"],
            "marketing": ["营销", "广告", "推广", "品牌", "渠道", "获客",
                          "投放", "转化", "KOL", "裂变", "私域", "增长黑客",
                          "marketing", "advertising", "promotion", "brand", "channel",
                          "conversion", "campaign", "growth"],
            "energy": ["能源", "电力", "光伏", "风电", "储能", "电网",
                       "新能源", "充电桩", "碳中和", "环保", "节能减排",
                       "energy", "power", "solar", "wind", "storage", "grid",
                       "renewable", "charging", "carbon", "green"],
            "real_estate": ["房地产", "物业", "楼盘", "销售", "租赁", "中介",
                            "建筑", "装修", "物业管理", "房产交易",
                            "real estate", "property", "housing", "construction",
                            "building", "rental", "broker"],
        }

        user_lower = user_prompt.lower()
        matched_domain = "general"
        matched_keywords = []

        for domain, keywords in domain_keywords.items():
            found = [kw for kw in keywords if kw in user_lower]
            if found:
                matched_domain = domain
                matched_keywords.extend(found)
                break

        domain_templates = {
            "finance": {"name": "金融服务", "department": "金融部", "role_prefix": "金融", "core_objective": "风险管理与合规"},
            "healthcare": {"name": "医疗健康", "department": "医疗部", "role_prefix": "医疗", "core_objective": "患者安全与疗效"},
            "retail": {"name": "零售电商", "department": "电商部", "role_prefix": "电商", "core_objective": "用户体验与转化"},
            "manufacturing": {"name": "智能制造", "department": "生产部", "role_prefix": "制造", "core_objective": "质量与效率"},
            "education": {"name": "在线教育", "department": "教学部", "role_prefix": "教育", "core_objective": "学习效果"},
            "content": {"name": "内容安全", "department": "运营部", "role_prefix": "审核", "core_objective": "内容安全"},
            "logistics": {"name": "智慧物流", "department": "物流部", "role_prefix": "物流", "core_objective": "配送时效"},
            "human_resource": {"name": "人力资源", "department": "人事部", "role_prefix": "HR", "core_objective": "人才发展"},
            "enterprise": {"name": "企业管理", "department": "企管部", "role_prefix": "企业", "core_objective": "数字化转型"},
            "marketing": {"name": "数字营销", "department": "市场部", "role_prefix": "营销", "core_objective": "增长与转化"},
            "energy": {"name": "新能源", "department": "能源部", "role_prefix": "能源", "core_objective": "绿色低碳发展"},
            "real_estate": {"name": "房地产", "department": "房产部", "role_prefix": "房产", "core_objective": "资产运营"},
            "general": {"name": "企业服务", "department": "业务部", "role_prefix": "业务", "core_objective": "效率提升"},
        }

        template = domain_templates.get(matched_domain, domain_templates["general"])

        return {
            "domain": matched_domain,
            "domain_name": template["name"],
            "department": template["department"],
            "role_prefix": template["role_prefix"],
            "core_objective": template["core_objective"],
            "keywords": matched_keywords[:5],
            "prompt_length": len(user_prompt),
        }

    def _mock_analysis(self, domain_info: dict) -> dict:
        """生成分析类Agent的默认mock数据"""
        return {"analysis_result": f"Analysis for {domain_info['domain_name']}"}

    def _mock_generation(self, domain_info: dict) -> dict:
        """生成生成类Agent的默认mock数据"""
        return {"generation_result": f"Generation for {domain_info['domain_name']}"}

    def _mock_business_understanding(self, domain_info: dict) -> dict:
        """生成业务理解mock数据"""
        return {
            "business_domain": domain_info["domain_name"],
            "core_objectives": [
                {"objective": f"{domain_info['core_objective']}", "target": "达成年度目标", "priority": "high"},
                {"objective": "流程自动化", "target": "降低人工成本60%", "priority": "high"},
                {"objective": "数据驱动决策", "target": "关键指标可视化", "priority": "medium"},
            ],
            "key_entities": [
                {"entity": "业务请求", "type": "核心数据"},
                {"entity": f"{domain_info['role_prefix']}专员", "type": "角色", "count": 15},
                {"entity": "处理结果", "type": "核心数据"},
                {"entity": "业务系统", "type": "系统组件"},
            ],
            "process_flow": ["接收请求", "分类处理", "审核校验", "完成交付"],
            "success_metrics": ["处理准确率", "响应时效", "用户满意度"],
            "constraints": ["24小时服务", "99%准确率", "成本控制"],
            "industry_context": f"{domain_info['domain_name']}行业数字化转型",
        }

    def _mock_sop(self, domain_info: dict) -> dict:
        """生成SOP mock数据"""
        return {
            "workflow": [
                {"step": 1, "name": "请求接收", "action": f"用户提交{domain_info['role_prefix']}请求", "input": "原始请求", "output": "请求记录", "role": "用户"},
                {"step": 2, "name": "智能分类", "action": "系统自动分类请求类型", "input": "请求记录", "output": "分类结果", "role": "系统"},
                {"step": 3, "name": "专业处理", "action": f"{domain_info['role_prefix']}专员执行处理", "input": "分类结果", "output": "处理结果", "role": f"{domain_info['role_prefix']}专员"},
                {"step": 4, "name": "质量审核", "action": "质检员审核处理质量", "input": "处理结果", "output": "审核结论", "role": "质检员"},
                {"step": 5, "name": "结果交付", "action": "系统交付处理结果", "input": "审核结论", "output": "交付记录", "role": "系统"},
            ],
            "roles": [
                {"role": f"{domain_info['role_prefix']}专员", "department": domain_info["department"], "level": "L4", "headcount": 15},
                {"role": "质检员", "department": domain_info["department"], "level": "L5", "headcount": 2},
                {"role": f"{domain_info['role_prefix']}经理", "department": domain_info["department"], "level": "L6", "headcount": 1},
            ],
            "responsibilities": [
                {"role": f"{domain_info['role_prefix']}专员", "duties": [f"执行{domain_info['role_prefix']}处理", "确保处理质量", "日处理量>=200条"]},
                {"role": "质检员", "duties": ["抽检已处理内容", "校准处理标准", "输出质检报告"]},
                {"role": f"{domain_info['role_prefix']}经理", "duties": ["监控SLA", "团队管理", "处理升级问题"]},
            ],
            "sla": [
                {"metric": "低优先级处理时效", "target": "<30分钟", "owner": "系统"},
                {"metric": "高优先级处理时效", "target": "<4小时", "owner": f"{domain_info['role_prefix']}专员"},
                {"metric": "SLA达标率", "target": ">=95%", "owner": f"{domain_info['role_prefix']}经理"},
            ],
            "kpi": [
                {"name": "处理准确率", "formula": "(正确数/总数)*100", "target": ">=98%", "owner": "质检员"},
                {"name": "自动化率", "formula": "(系统处理数/总数)*100", "target": ">=60%", "owner": f"{domain_info['role_prefix']}经理"},
                {"name": "单次成本", "formula": "总成本/处理量", "target": "<=1.00元", "owner": f"{domain_info['role_prefix']}经理"},
            ],
        }

    def _mock_risk(self, domain_info: dict) -> dict:
        """生成风险分析mock数据"""
        return {
            "process_risks": [
                {"risk": f"{domain_info['role_prefix']}专员处理瓶颈导致SLA违约", "severity": "critical", "probability": "high", "mitigation": "提升自动化率+优先级队列"},
                {"risk": "流程串行设计导致时效过长", "severity": "high", "probability": "high", "mitigation": "并行化改造"},
            ],
            "organization_risks": [
                {"risk": f"{domain_info['role_prefix']}专员工作负荷过高", "severity": "critical", "probability": "high", "mitigation": "合理排班+自动化减负"},
                {"risk": "人员流失风险", "severity": "high", "probability": "medium", "mitigation": "薪酬优化+职业发展"},
            ],
            "system_risks": [
                {"risk": "业务系统单点故障", "severity": "critical", "probability": "medium", "mitigation": "双活架构+自动降级"},
                {"risk": "系统性能衰减", "severity": "high", "probability": "medium", "mitigation": "性能监控+容量规划"},
            ],
            "compliance_risks": [
                {"risk": "处理标准不一致", "severity": "high", "probability": "medium", "mitigation": "标准化指南+定期校准"},
                {"risk": "合规风险", "severity": "critical", "probability": "medium", "mitigation": "双重审核+合规审查"},
            ],
        }

    def _mock_strategy(self, domain_info: dict) -> dict:
        """生成战略分析mock数据"""
        return {
            "growth_opportunities": [
                {"opportunity": "自动化率提升", "potential": "100万元/年", "priority": "高", "timeline": "3个月"},
                {"opportunity": f"{domain_info['domain_name']}品类扩展", "potential": "180万元/年", "priority": "中", "timeline": "6个月"},
                {"opportunity": "区域市场扩张", "potential": "400万元/年", "priority": "低", "timeline": "12个月"},
            ],
            "efficiency_opportunities": [
                {"opportunity": "流程并行化", "impact": "时效-50%", "effort": "中"},
                {"opportunity": "人机协同", "impact": "人工量-45%", "effort": "中"},
                {"opportunity": "弹性调度", "impact": "负荷-40%", "effort": "低"},
            ],
            "automation_opportunities": [
                {"process": "智能分类", "current": "30%", "target": "70%", "impact": "成本-50%"},
                {"process": f"{domain_info['role_prefix']}处理", "current": "0%", "target": "40%", "impact": "人效+1.5倍"},
                {"process": "质检抽检", "current": "5%", "target": "40%", "impact": "效率+2倍"},
            ],
            "strategic_path": [
                {"phase": "第一阶段", "theme": "效率提升", "timeline": "0-3月", "goal": "成本-50%, SLA 95%+"},
                {"phase": "第二阶段", "theme": "能力升级", "timeline": "3-6月", "goal": "准确率98%+, 品类扩展"},
                {"phase": "第三阶段", "theme": "市场扩张", "timeline": "6-12月", "goal": "覆盖新区域, 收入+40%"},
            ],
        }

    def _mock_optimization(self, domain_info: dict) -> dict:
        """生成优化建议mock数据"""
        return {
            "recommendations": [
                {"id": "REC-1", "title": f"自动化率提升至70%", "category": "自动化", "priority": "P0",
                 "description": f"更新AI模型和规则引擎，将{domain_info['role_prefix']}处理自动化率从30%提升至70%",
                 "actions": ["AI模型重训练", "规则引擎更新", "阈值动态调优", "AB测试验证"],
                 "timeline": "3周", "investment": "30000元",
                 "addresses": ["SLA违约", "成本偏高", f"{domain_info['role_prefix']}处理瓶颈"]},
                {"id": "REC-2", "title": "SLA预警+优先级队列", "category": "流程", "priority": "P0",
                 "description": "建立SLA实时预警机制，按紧急度分级处理",
                 "actions": ["配置SLA预警规则", "实施优先级队列", "超时自动升级"],
                 "timeline": "2周", "investment": "6000元",
                 "addresses": ["SLA违约", "高紧急请求阻塞"]},
            ],
            "roi_estimation": [
                {"recommendation": "REC-1", "investment": 30000, "monthly_savings": 120000,
                 "annual_savings": 1440000, "roi_pct": 4800, "payback_months": 0.3},
                {"recommendation": "REC-2", "investment": 6000, "monthly_savings": 45000,
                 "annual_savings": 540000, "roi_pct": 9000, "payback_months": 0.1},
            ],
        }

    def _mock_report_composer(self, domain_info: dict) -> dict:
        """生成报告mock数据"""
        return {
            "title": f"{domain_info['domain_name']}业务分析报告",
            "executive_summary": f"本报告基于PRD分析，提出了完整的{domain_info['domain_name']}业务系统方案。通过自动化处理，可将人工成本降低60%，同时保障98%的处理准确率和24小时SLA。",
            "sections": [
                {"section": "1. 业务目标", "content": f"{domain_info['core_objective']}、流程自动化、数据驱动决策"},
                {"section": "2. 流程设计", "content": "接收请求→智能分类→专业处理→质量审核→结果交付"},
                {"section": "3. 风险分析", "content": "识别8项风险，含2项critical风险"},
                {"section": "4. 战略机会", "content": "3项增长机会，年潜力680万元"},
                {"section": "5. 优化建议", "content": "2项高优先级优化方案，ROI高达4800%"},
            ],
            "key_findings": [
                {"finding": f"自动化率提升至70%可节省144万元/年", "impact": "高", "category": "成本"},
                {"finding": "流程并行化可将时效降低50%", "impact": "高", "category": "效率"},
                {"finding": "当前存在2项critical风险需优先处理", "impact": "高", "category": "风险"},
            ],
        }

    def _mock_dialog_question(self, user_prompt: str) -> dict:
        """生成对话问题mock数据"""
        import re
        import json
        
        input_text = ""
        collected = {}
        question_type = "业务目标"
        
        input_match = re.search(r"用户输入：(.+?)\n", user_prompt)
        if input_match:
            input_text = input_match.group(1).strip()
        
        collected_match = re.search(r"已收集信息：(.+?)\n", user_prompt)
        if collected_match:
            try:
                collected = json.loads(collected_match.group(1).strip())
            except:
                collected = {}
        
        type_match = re.search(r"当前问题类型：(.+?)\n", user_prompt)
        if type_match:
            question_type = type_match.group(1).strip()
        
        if not input_text:
            input_text = user_prompt
        
        retail_questions = {
            "业务目标": "这个零售电商系统的核心业务目标是什么？比如是提升用户转化率、降低运营成本还是增加用户粘性？",
            "核心功能": "为了达成业务目标，你认为电商系统需要哪些核心功能模块？比如商品管理、订单系统、会员体系等？",
            "用户角色": "这个零售电商系统主要服务哪些用户角色？是消费者、商家还是平台运营人员？",
            "特殊要求": "有没有特殊的技术或业务要求？比如支付安全、物流对接等？",
            "非功能需求": "对系统性能、安全等非功能需求有什么要求？比如响应时间、可用性等？",
            "成功标准": "如何衡量这个电商系统的成功？有哪些关键指标？",
        }
        
        healthcare_questions = {
            "业务目标": "这个医疗健康系统的核心业务目标是什么？比如是提升患者就医体验、优化医疗资源配置还是提高诊疗效率？",
            "核心功能": "为了达成目标，你认为医疗系统需要哪些核心功能模块？比如在线挂号、电子病历、远程问诊等？",
            "用户角色": "这个医疗系统主要服务哪些用户角色？是患者、医生、护士还是医院管理人员？",
            "特殊要求": "有没有特殊的医疗行业要求？比如数据隐私保护、医疗合规等？",
            "非功能需求": "对系统性能、安全等有什么要求？比如系统可用性、数据加密等？",
            "成功标准": "如何衡量医疗系统的成功？有哪些关键指标？",
        }
        
        finance_questions = {
            "业务目标": "这个金融系统的核心业务目标是什么？比如是提升交易效率、降低风险还是提高客户满意度？",
            "核心功能": "为了达成目标，你认为金融系统需要哪些核心功能模块？比如交易处理、风控系统、报表分析等？",
            "用户角色": "这个金融系统主要服务哪些用户角色？是商户、风控人员还是系统管理员？",
            "特殊要求": "有没有特殊的金融合规要求？比如等保认证、反洗钱等？",
            "非功能需求": "对系统性能、安全有什么要求？比如交易响应时间、系统可用性等？",
            "成功标准": "如何衡量金融系统的成功？有哪些关键指标？",
        }
        
        general_questions = {
            "业务目标": "这个产品的核心业务目标是什么？比如是提升效率、降低成本还是增加收益？",
            "核心功能": "为了达成目标，你认为系统需要哪些核心功能模块？",
            "用户角色": "系统主要服务哪些用户角色？",
            "特殊要求": "有没有特殊的技术或业务要求？",
            "非功能需求": "对系统性能、安全等非功能需求有什么要求？",
            "成功标准": "如何衡量项目成功？有哪些关键指标？",
        }
        
        domain = self._analyze_input_domain(input_text)["domain"]
        
        question_map = {
            "retail": retail_questions,
            "healthcare": healthcare_questions,
            "finance": finance_questions,
        }
        
        questions = question_map.get(domain, general_questions)
        question = questions.get(question_type, general_questions.get(question_type, general_questions["业务目标"]))
        
        if collected:
            if "业务目标" in collected:
                if question_type == "核心功能":
                    question = f"为了达成「{collected['业务目标']}」的目标，你认为系统需要哪些核心功能模块？"
                elif question_type == "用户角色":
                    question = f"为了实现「{collected['业务目标']}」，系统需要服务哪些用户角色？"
        
        return {"content": question}

    def _mock_prd_generation(self, user_prompt: str) -> dict:
        """生成PRD文档mock数据"""
        import re
        import json
        
        input_text = ""
        industry = "general"
        collected = {}
        
        name_match = re.search(r"产品名称：(.+?)(?:\n|$)", user_prompt)
        if name_match:
            input_text = name_match.group(1).strip()
        
        industry_match = re.search(r"行业：(.+?)(?:\n|$)", user_prompt)
        if industry_match:
            industry = industry_match.group(1).strip()
        
        collected_match = re.search(r"收集到的需求信息：(.+?)(?:\n\n|$)", user_prompt, re.DOTALL)
        if collected_match:
            try:
                collected = json.loads(collected_match.group(1).strip())
            except:
                collected = {}
        
        if not input_text:
            input_text = user_prompt[:50] + "..." if len(user_prompt) > 50 else user_prompt
        
        domain_info = self._analyze_input_domain(input_text)
        domain = domain_info["domain"]
        
        retail_prd = f"""# {input_text}产品PRD

## 一、产品概述

本产品是一款面向零售行业的电商系统，旨在通过数字化手段提升用户购物体验，优化商家运营效率，实现平台增长目标。

## 二、业务目标

{collected.get('business_objectives', '待确认')}

建议按照SMART原则细化：
- 短期目标：完成MVP版本上线，验证商业模式
- 中期目标：获取10万种子用户，日活用户达到2万
- 长期目标：实现盈利，建立行业影响力

## 三、核心功能模块

{collected.get('core_features', '''### 商品管理模块
- 商品发布：支持多规格商品、图片上传、库存管理
- 商品搜索：支持关键词搜索、分类筛选、智能推荐
- 商品管理：上下架管理、价格调整、促销活动设置

### 订单系统模块
- 订单创建：支持多种支付方式、地址管理、优惠券使用
- 订单履约：自动化配送流程、物流追踪、退换货管理

### 用户中心模块
- 会员体系：积分和等级制度、成长值计算
- 优惠券：营销活动支持、优惠券发放和使用''')}

## 四、用户角色与权限

{collected.get('user_roles', '''### 消费者
- 职责：浏览商品、下单购买、评价反馈
- 权限：查看商品、提交订单、管理账户

### 商家
- 职责：商品管理、订单处理、数据分析
- 权限：商品上下架、订单处理、数据查看

### 平台运营
- 职责：活动策划、商家管理、平台监控
- 权限：活动配置、商家审核、数据统计''')}

## 五、业务流程图

```mermaid
flowchart TD
    A[用户浏览] --> B[搜索/筛选商品]
    B --> C[查看商品详情]
    C --> D[加入购物车]
    D --> E[提交订单]
    E --> F[选择支付方式]
    F --> G[支付成功]
    G --> H[商家发货]
    H --> I[用户收货]
    I --> J[评价反馈]
```

## 六、非功能需求

{collected.get('non_functional', '''### 性能要求
- 页面响应时间：<1秒
- 峰值QPS：>10000
- 系统可用性：99.9%

### 安全要求
- 支付安全：符合PCI-DSS标准
- 数据加密：传输和存储加密
- 防攻击：防DDoS、防SQL注入

### 合规要求
- 消费者保护：符合消费者权益保护法
- 数据合规：符合个人信息保护法''')}

## 七、成功标准

{collected.get('success_criteria', '''### 业务指标
- 转化率：>5%
- 复购率：>30%
- GMV增长率：>30%/月

### 技术指标
- 页面响应时间：<1秒
- 系统可用性：99.9%
- 订单成功率：>99.5%

### 用户指标
- 用户满意度：>4.5分
- NPS评分：>50''')}

## 八、项目里程碑

{collected.get('milestones', '''### Phase 1：基础电商（第1-4周）
- 商品管理、订单系统开发
- 支付接口集成
- 目标：基础购物流程打通

### Phase 2：用户体系（第5-8周）
- 会员体系开发
- 优惠券系统开发
- 目标：用户运营能力完善

### Phase 3：数据分析（第9-12周）
- 数据报表开发
- 智能推荐上线
- 目标：数据驱动运营''')}"""
        
        healthcare_prd = f"""# {input_text}产品PRD

## 一、产品概述

本产品是一款面向医疗健康行业的数字化系统，旨在提升患者就医体验，优化医疗资源配置，实现医疗服务的智能化升级。

## 二、业务目标

{collected.get('business_objectives', '待确认')}

### 目标拆解
- 提升患者就医体验，减少排队时间50%
- 优化医疗资源配置，提升医生工作效率20%
- 医疗数据安全合规率100%
- 患者满意度提升至90分

## 三、核心功能模块

{collected.get('core_features', '''### 在线挂号模块
- 科室选择：支持多科室挂号、医生筛选
- 预约管理：选择医生和时间、预约确认

### 电子病历模块
- 病历管理：电子病历的创建和查看
- 数据共享：跨机构数据共享、隐私保护

### 远程问诊模块
- 视频问诊：在线视频咨询医生
- 处方管理：在线开具电子处方''')}

## 四、用户角色与权限

{collected.get('user_roles', '''### 患者
- 职责：预约挂号、查看病历、在线问诊
- 权限：预约挂号、查看病历、在线问诊

### 医生
- 职责：接诊患者、开具处方、管理病历
- 权限：接诊患者、开具处方、查看患者信息

### 医院管理人员
- 职责：医院运营、资源调配、数据监控
- 权限：管理医院配置、查看运营数据''')}

## 五、业务流程图

```mermaid
flowchart TD
    A[选择科室] --> B[选择医生]
    B --> C[预约时间]
    C --> D[确认预约]
    D --> E[按时就诊]
    E --> F[医生诊断]
    F --> G[开具处方]
    G --> H[取药/治疗]
```

## 六、非功能需求

{collected.get('non_functional', '''### 性能要求
- 页面响应时间：<2秒
- 系统可用性：99.9%
- 数据存储：医疗数据长期存储

### 安全要求
- 数据加密：传输和存储加密
- 访问控制：基于角色的权限控制
- 审计日志：完整的操作审计记录

### 合规要求
- 医疗合规：符合医疗行业监管要求
- 数据隐私：患者隐私数据保护''')}

## 七、成功标准

{collected.get('success_criteria', '''### 业务指标
- 挂号成功率：>95%
- 患者满意度：>90分
- 平均就诊时长缩短：>30%

### 技术指标
- 系统可用性：>99.9%
- 响应时间：<2秒
- 数据安全：0安全事故''')}

## 八、项目里程碑

{collected.get('milestones', '''### Phase 1：基础功能（第1-4周）
- 在线挂号、电子病历开发
- 目标：基础医疗服务流程打通

### Phase 2：高级功能（第5-8周）
- 远程问诊、处方管理开发
- 目标：服务能力完善

### Phase 3：优化迭代（第9-12周）
- 用户反馈收集和分析
- Bug修复和体验优化''')}"""
        
        finance_prd = f"""# {input_text}产品PRD

## 一、产品概述

本产品是一款面向金融行业的交易系统，旨在提供安全、高效的交易处理能力，实现业务增长和风险控制的平衡。

## 二、业务目标

{collected.get('business_objectives', '待确认')}

### 目标拆解
- 交易成功率提升至99.9%
- 降低欺诈风险损失率至0.01%
- 合规达标率100%
- 客户满意度提升至95分

## 三、核心功能模块

{collected.get('core_features', '''### 交易处理模块
- 支付接口：支持多种支付渠道、交易路由
- 清算结算：自动清算和结算流程、对账处理

### 风控模块
- 实时风控：毫秒级风险识别、规则引擎
- 反欺诈：多维度欺诈检测、设备指纹

### 报表分析模块
- 数据报表：交易统计、趋势分析
- 监控预警：异常交易监控、风险预警''')}

## 四、用户角色与权限

{collected.get('user_roles', '''### 商户
- 职责：发起交易、查看报表、管理账户
- 权限：交易操作、报表查看、账户管理

### 风控人员
- 职责：风险监控、规则配置、异常处理
- 权限：风险监控、规则管理、异常处理

### 管理员
- 职责：系统管理、用户管理、配置管理
- 权限：全部权限''')}

## 五、业务流程图

```mermaid
flowchart TD
    A[发起交易] --> B[风险评估]
    B --> C{{风险通过?}}
    C -->|是| D[执行交易]
    C -->|否| E[交易拒绝]
    D --> F[清算结算]
    F --> G[完成]
```

## 六、非功能需求

{collected.get('non_functional', '''### 性能要求
- 交易响应时间：<500ms
- 峰值TPS：>10000
- 系统可用性：99.99%

### 安全要求
- 等保合规：等保三级认证
- 数据加密：金融级加密标准
- 访问控制：多重身份认证

### 合规要求
- 监管合规：符合行业监管要求
- 审计日志：完整的操作审计记录''')}

## 七、成功标准

{collected.get('success_criteria', '''### 业务指标
- 交易成功率：>99.9%
- 欺诈损失率：<0.01%
- 客户增长率：>20%/月

### 技术指标
- 交易响应时间：<500ms
- 系统可用性：99.99%
- 错误率：<0.01%''')}

## 八、项目里程碑

{collected.get('milestones', '''### Phase 1：基础交易（第1-4周）
- 支付接口开发
- 清算结算开发
- 目标：基础交易流程打通

### Phase 2：风控体系（第5-8周）
- 风控规则引擎开发
- 反欺诈系统开发
- 目标：风控能力完善

### Phase 3：合规审计（第9-12周）
- 合规功能开发
- 审计日志系统开发
- 目标：合规达标''')}"""
        
        general_prd = f"""# {input_text}产品PRD

## 一、产品概述

本产品是一款面向{domain_info['domain_name']}领域的业务系统，旨在提升业务效率，优化用户体验，实现数字化转型目标。

## 二、业务目标

{collected.get('business_objectives', '待确认')}

### 目标拆解
- 短期目标（1-3个月）：完成MVP版本上线，验证商业模式
- 中期目标（3-6个月）：获取目标用户，建立产品口碑
- 长期目标（6-12个月）：实现盈利，建立行业影响力

## 三、核心功能模块

{collected.get('core_features', '''### 核心功能模块1
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用

### 核心功能模块2
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用''')}

## 四、用户角色与权限

{collected.get('user_roles', '''### 管理员
- 职责：系统管理、用户管理、配置管理
- 权限：全部权限

### 普通用户
- 职责：使用系统核心功能
- 权限：只读和操作权限

### 运营人员
- 职责：业务运营、数据监控
- 权限：运营相关权限''')}

## 五、业务流程图

```mermaid
flowchart TD
    A[用户访问] --> B[浏览产品]
    B --> C[选择功能]
    C --> D[完成操作]
    D --> E[获取结果]
```

## 六、非功能需求

{collected.get('non_functional', '''### 性能要求
- 响应时间：核心页面<2秒，API<500ms
- QPS：峰值>1000
- 可用性：99.9%

### 安全要求
- 数据加密：传输加密（HTTPS）、存储加密
- 访问控制：基于角色的权限控制
- 日志审计：完整的操作日志记录

### 合规要求
- 数据合规：符合行业数据保护规范
- 隐私保护：用户隐私数据保护措施''')}

## 七、成功标准

{collected.get('success_criteria', '''### 业务指标
- 用户增长：月活用户增长率>20%
- 转化率：注册转化率>10%
- 留存率：7日留存>40%

### 技术指标
- 系统可用性：>99.9%
- 响应时间：<2秒
- 错误率：<0.1%

### 用户指标
- 用户满意度：>4.5分（5分制）
- NPS评分：>50''')}

## 八、项目里程碑

{collected.get('milestones', '''### Phase 1：基础功能（第1-4周）
- 完成核心功能开发
- 内部测试通过
- 目标：MVP版本上线

### Phase 2：高级功能（第5-8周）
- 完成高级功能开发
- 性能优化
- 目标：功能完善版本上线

### Phase 3：优化迭代（第9-12周）
- 用户反馈收集和分析
- Bug修复和体验优化
- 目标：稳定运营版本''')}"""
        
        prd_map = {
            "retail": retail_prd,
            "healthcare": healthcare_prd,
            "finance": finance_prd,
        }
        
        prd_content = prd_map.get(domain, general_prd)
        
        return {"content": prd_content}

    def status(self) -> dict:
        """返回Provider状态"""
        status = {
            "default_provider": self.provider,
            "default_model": self.model,
            "default_api_key_set": bool(self.api_key),
            "default_base_url": self.base_url or "N/A",
            "providers": {},
            "routing": {},
        }

        for provider, config in self.PROVIDERS.items():
            provider_config = self._get_provider_config(provider)
            status["providers"][provider] = {
                "api_key_set": bool(provider_config["api_key"]),
                "base_url": provider_config["base_url"],
                "model": provider_config["model"],
            }

        status["routing"] = {
            "analysis_provider": settings.ANALYSIS_PROVIDER,
            "generation_provider": settings.GENERATION_PROVIDER,
            "ocr_provider": settings.OCR_PROVIDER,
            "analysis_agents": [k for k, v in self.AGENT_ROUTING.items() if v == AgentType.ANALYSIS],
            "generation_agents": [k for k, v in self.AGENT_ROUTING.items() if v == AgentType.GENERATION],
        }

        return status

    def stream_chat(self, system_prompt: str, user_prompt: str,
                   temperature: float = None, max_tokens: int = None) -> iter:
        """
        同步流式调用大模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            迭代器，每次返回一个token
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS
        
        provider = self._get_provider_for_agent(system_prompt)
        
        if provider == ProviderType.MOCK.value or self.provider == ProviderType.MOCK.value:
            result = self._mock(system_prompt, user_prompt)
            content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            for chunk in content.split("\n"):
                yield chunk + "\n"
            return
        
        try:
            yield from self._call_api_streaming_with_provider(provider, system_prompt, user_prompt, temperature, max_tokens)
        except Exception as e:
            logger.error(f"Streaming LLM call failed: {e}")
            result = self._mock(system_prompt, user_prompt)
            content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            for chunk in content.split("\n"):
                yield chunk + "\n"

    async def async_chat(self, system_prompt: str, user_prompt: str,
                         temperature: float = None, max_tokens: int = None,
                         use_cache: bool = True) -> dict:
        """
        异步调用大模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            use_cache: 是否使用缓存
            
        Returns:
            dict: 大模型返回的结构化JSON
        """
        import asyncio
        
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS
        
        result = await asyncio.to_thread(
            self.chat,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            use_cache=use_cache,
        )
        
        if "_meta" in result:
            result["_meta"]["async"] = True
        
        return result

    async def async_stream_chat(self, system_prompt: str, user_prompt: str,
                                temperature: float = None, max_tokens: int = None):
        """
        异步流式调用大模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            异步迭代器，每次返回一个token
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS
        
        provider = self._get_provider_for_agent(system_prompt)
        
        if provider == ProviderType.MOCK.value or self.provider == ProviderType.MOCK.value:
            result = self._mock(system_prompt, user_prompt)
            content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            for chunk in content.split("\n"):
                yield chunk + "\n"
            return
        
        try:
            async for chunk in self._call_api_async_streaming_with_provider(provider, system_prompt, user_prompt, temperature, max_tokens):
                yield chunk
        except Exception as e:
            logger.error(f"Async streaming LLM call failed: {e}")
            result = self._mock(system_prompt, user_prompt)
            content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            for chunk in content.split("\n"):
                yield chunk + "\n"

    def _call_api_streaming_with_provider(self, provider: str, system_prompt: str, user_prompt: str,
                                          temperature: float, max_tokens: int):
        """使用指定Provider进行同步流式API调用"""
        from openai import OpenAI
        
        config = self.PROVIDERS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")
        
        provider_config = self._get_provider_config(provider)
        api_key = provider_config["api_key"]
        base_url = provider_config["base_url"]
        model = provider_config["model"]
        
        if not api_key:
            raise ValueError(f"{provider} API key not set")
        
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=settings.LLM_TIMEOUT)
        
        stream = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _call_api_async_streaming_with_provider(self, provider: str, system_prompt: str, user_prompt: str,
                                                       temperature: float, max_tokens: int):
        """使用指定Provider进行异步流式API调用"""
        from openai import AsyncOpenAI
        
        config = self.PROVIDERS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")
        
        provider_config = self._get_provider_config(provider)
        api_key = provider_config["api_key"]
        base_url = provider_config["base_url"]
        model = provider_config["model"]
        
        if not api_key:
            raise ValueError(f"{provider} API key not set")
        
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=settings.LLM_TIMEOUT)
        
        stream = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def is_ready(self) -> bool:
        """检查LLM服务是否就绪"""
        if self.provider == "mock":
            return True
        return bool(self.api_key) and bool(self.base_url)


_thread_local = threading.local()


def get_thread_local_service() -> LLMService:
    """获取线程本地的LLM服务实例（每个线程独立）"""
    if not hasattr(_thread_local, 'llm_service'):
        _thread_local.llm_service = LLMService()
    return _thread_local.llm_service


_global_llm_service = None
_global_lock = threading.Lock()


def get_llm_service() -> LLMService:
    """
    获取LLM服务实例（线程安全的工厂函数）
    
    优先使用线程本地实例，确保并发安全。
    """
    try:
        return get_thread_local_service()
    except Exception as e:
        logger.debug(f"Thread-local LLM service not available: {e}, using global instance")
        global _global_llm_service
        if _global_llm_service is None:
            with _global_lock:
                if _global_llm_service is None:
                    _global_llm_service = LLMService()
        return _global_llm_service


class LLMServiceFactory:
    """
    LLM服务工厂类（推荐用于依赖注入）
    
    提供线程安全的实例创建和管理，支持：
    - 线程本地实例（每个线程独立，推荐）
    - 全局单例（共享实例，不推荐并发场景）
    - 独立实例（每次创建新实例）
    """
    
    def get_thread_local_instance(self) -> LLMService:
        """获取线程本地实例（推荐）"""
        return get_thread_local_service()
    
    def get_global_instance(self) -> LLMService:
        """获取全局共享实例"""
        return get_llm_service()
    
    def create_instance(self, **kwargs) -> LLMService:
        """创建独立的LLM服务实例"""
        return LLMService(**kwargs)


__all__ = ["LLMService", "ProviderType", "AgentType", "LLMServiceFactory", 
           "get_llm_service", "get_thread_local_service"]