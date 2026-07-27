from __future__ import annotations
import json
import time
import logging
import re
import threading
import copy
import hashlib
import traceback
from enum import Enum
from typing import Dict, Optional, Any, List
import numpy as np
from app.core.config import settings
from app.core.llm_usage import ModelUsage, extract_model_usage
logger = logging.getLogger(__name__)

class ProviderType(str, Enum):
    DEEPSEEK = "deepseek"
    DOUBAO = "doubao"
    YUANBAO = "yuanbao"
    QWEN = "qwen"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LOCALAI = "localai"
    MOCK = "mock"

class AgentType(str, Enum):
    ANALYSIS = "analysis"
    GENERATION = "generation"

class LLMService:
    DOMAIN_CONFIG = {"general": {"keywords": [], "template": {"name": "企业服务", "department": "业务部", "role_prefix": "业务", "core_objective": "效率提升"}, "specificity": 0}}
    PROVIDERS = {"deepseek": {"env_key": "DEEPSEEK_API_KEY", "env_url": "DEEPSEEK_BASE_URL", "env_model": "DEEPSEEK_MODEL", "default_url": "https://api.deepseek.com/v1", "default_model": "deepseek-v4-flash"}, "doubao": {"env_key": "DOUBAO_API_KEY", "env_url": "DOUBAO_BASE_URL", "env_model": "DOUBAO_MODEL", "default_url": "https://ark.cn-beijing.volces.com/api/v3", "default_model": "doubao-pro-32k"}, "yuanbao": {"env_key": "YUANBAO_API_KEY", "env_url": "YUANBAO_BASE_URL", "env_model": "YUANBAO_MODEL", "default_url": "https://api.hunyuan.cloud.tencent.com/v1", "default_model": "hunyuan-pro"}, "qwen": {"env_key": "QWEN_API_KEY", "env_url": "QWEN_BASE_URL", "env_model": "QWEN_MODEL", "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "default_model": "qwen-plus"}, "kimi": {"env_key": "KIMI_API_KEY", "env_url": "KIMI_BASE_URL", "env_model": "KIMI_MODEL", "default_url": "https://api.moonshot.cn/v1", "default_model": "moonshot-v1-8k"}, "ollama": {"env_key": "", "env_url": "OLLAMA_BASE_URL", "env_model": "OLLAMA_MODEL", "default_url": "http://localhost:11434/v1", "default_model": "qwen2.5:7b"}, "vllm": {"env_key": "", "env_url": "VLLM_BASE_URL", "env_model": "VLLM_MODEL", "default_url": "http://localhost:8000/v1", "default_model": ""}, "localai": {"env_key": "", "env_url": "LOCALAI_BASE_URL", "env_model": "LOCALAI_MODEL", "default_url": "http://localhost:8080/v1", "default_model": "gpt-4"}}
    
    def __init__(self, provider=None, force_mock=False):
        self.provider = provider or settings.LLM_PROVIDER
        self.force_mock = force_mock
        self._configure()
    
    def _configure(self):
        if self.provider == ProviderType.MOCK.value:
            self.api_key = ""
            self.base_url = ""
            self.model = ProviderType.MOCK.value
            return
        config = self.PROVIDERS.get(self.provider)
        if not config:
            self.provider = ProviderType.MOCK.value
            self._configure()
            return
        self.api_key = getattr(settings, config["env_key"], "")
        self.base_url = getattr(settings, config["env_url"], config["default_url"])
        self.model = getattr(settings, config["env_model"], config["default_model"])
        if not self.api_key and self.provider not in {"ollama", "vllm", "localai"}:
            self.provider = ProviderType.MOCK.value
            self.model = ProviderType.MOCK.value
    
    def is_ready(self):
        if self.force_mock or self.provider == ProviderType.MOCK.value:
            return self._mock_allowed()
        config = self.PROVIDERS.get(self.provider)
        if config is None:
            return False
        return bool(self.api_key) or self.provider in {"ollama", "vllm", "localai"}
    
    def _get_provider_for_agent(self, system_prompt):
        prefix_map = [("你是SOP Agent", AgentType.ANALYSIS), ("你是Risk Agent", AgentType.ANALYSIS), ("你是Strategy Agent", AgentType.ANALYSIS), ("你是Optimization Agent", AgentType.ANALYSIS), ("你是Business Understanding Agent", AgentType.GENERATION), ("你是Report Composer", AgentType.GENERATION)]
        for prefix, agent_type in prefix_map:
            if system_prompt.startswith(prefix):
                return settings.ANALYSIS_PROVIDER if agent_type == AgentType.ANALYSIS else settings.GENERATION_PROVIDER
        return self.provider
    
    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None, use_cache=True):
        if temperature is None: temperature = settings.LLM_TEMPERATURE
        if max_tokens is None: max_tokens = settings.LLM_MAX_TOKENS
        provider = self._get_provider_for_agent(system_prompt)
        if provider == ProviderType.MOCK.value or self.force_mock:
            result = self._mock(system_prompt, user_prompt)
            result["_meta"] = {"mode": ProviderType.MOCK.value, "elapsed_ms": int((time.time() * 1000) % 1000)}
            return result
        try:
            result = self._call_api_with_provider(provider, system_prompt, user_prompt, temperature, max_tokens)
            result["_meta"] = {"mode": "api", "elapsed_ms": int((time.time() * 1000) % 1000)}
            return result
        except Exception as e:
            fallback_result = self._mock(system_prompt, user_prompt)
            fallback_result["_meta"] = {"mode": "fallback", "elapsed_ms": int((time.time() * 1000) % 1000), "error": str(e)}
            return fallback_result
    
    def _call_api_with_provider(self, provider, system_prompt, user_prompt, temperature, max_tokens):
        from openai import OpenAI
        config = self.PROVIDERS.get(provider)
        api_key = getattr(settings, config["env_key"], "")
        base_url = getattr(settings, config["env_url"], config["default_url"])
        model = getattr(settings, config["env_model"], config["default_model"])
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=settings.LLM_TIMEOUT)
        response = client.chat.completions.create(model=model, temperature=temperature, max_tokens=max_tokens, response_format={"type": "json_object"}, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
        return (
            self._parse_json(response.choices[0].message.content.strip()),
            extract_model_usage(response, provider=provider, model=model),
        )
    
    @staticmethod
    def _parse_json(raw):
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"): raw = raw[4:]
        return json.loads(raw.strip())
    
    def _mock(self, system_prompt, user_prompt):
        agent_mock_map = [("你是SOP Agent", self._mock_sop), ("你是Risk Agent", self._mock_risk), ("你是Strategy Agent", self._mock_strategy), ("你是Optimization Agent", self._mock_optimization), ("你是Business Understanding Agent", self._mock_business_understanding), ("你是Report Composer", self._mock_report_composer), ("你是流程优化专家", self._mock_process_optimization), ("你是一个专业的产品需求分析师", lambda d: self._mock_dialog_question(user_prompt)), ("你是一个资深的产品经理", lambda d: self._mock_prd_generation(user_prompt)), ("你是一个创意专家", lambda d: self._mock_brainstorm_ideas(user_prompt)), ("你是一个战略分析师", lambda d: self._mock_brainstorm_ideas(user_prompt)), ("你是一个思维导图专家", lambda d: self._mock_brainstorm_mindmap(user_prompt)), ("你是一个问题分析专家", lambda d: self._mock_brainstorm_analysis(user_prompt)), ("你是 Reviewer Agent", lambda d: self._mock_reviewer(user_prompt)), ("你是 SOP Builder Agent", lambda d: self._mock_sop_builder(user_prompt))]
        for agent_prefix, mock_method in agent_mock_map:
            if system_prompt.startswith(agent_prefix):
                return mock_method({"domain_name": "测试", "role_prefix": "业务", "department": "业务部", "core_objective": "效率提升"})
        return {"content": "mock response"}
    
    def _mock_business_understanding(self, domain_info):
        return {"business_domain": domain_info["domain_name"], "core_objectives": [{"objective": domain_info["core_objective"], "target": "达成目标", "priority": "high"}], "key_entities": [{"entity": "业务请求", "type": "核心数据"}], "process_flow": ["接收请求", "分类处理", "审核校验", "完成交付"]}
    
    def _mock_sop(self, domain_info):
        return {"workflow": [{"step": 1, "name": "请求接收", "action": "用户提交请求"}, {"step": 2, "name": "智能分类", "action": "系统自动分类"}, {"step": 3, "name": "专业处理", "action": "专员执行处理"}, {"step": 4, "name": "质量审核", "action": "质检员审核"}, {"step": 5, "name": "结果交付", "action": "系统交付结果"}], "roles": [{"role": "专员", "department": domain_info["department"]}], "sla": [{"metric": "处理时效", "target": "<30分钟"}], "kpi": [{"name": "处理准确率", "target": ">=98%"}]}
    
    def _mock_risk(self, domain_info):
        return {"process_risks": [{"risk": "处理瓶颈", "severity": "critical", "probability": "high", "mitigation": "提升自动化率"}], "organization_risks": [{"risk": "人员流失", "severity": "high", "probability": "medium"}], "system_risks": [{"risk": "系统故障", "severity": "critical", "probability": "medium"}], "compliance_risks": [{"risk": "合规风险", "severity": "critical", "probability": "medium"}]}
    
    def _mock_strategy(self, domain_info):
        return {"growth_opportunities": [{"opportunity": "自动化提升", "potential": "100万元/年", "priority": "高"}], "strategic_path": [{"phase": "第一阶段", "theme": "效率提升", "timeline": "0-3月"}]}
    
    def _mock_optimization(self, domain_info):
        return {"recommendations": [{"id": "REC-1", "title": "自动化提升", "priority": "P0", "timeline": "3周"}], "roi_estimation": [{"recommendation": "REC-1", "investment": 30000, "annual_savings": 1440000}]}
    
    def _mock_process_optimization(self, domain_info):
        return {"optimization_suggestions": [{"id": "opt_001", "title": "流程自动化", "priority": "高"}], "prioritized_actions": [{"action": "自动化高频环节", "timeline": "1-2个月", "priority": "紧急"}]}
    
    def _mock_report_composer(self, domain_info):
        return {"title": "业务分析报告", "executive_summary": "完整的业务系统方案", "sections": [{"section": "1. 业务目标", "content": "效率提升"}], "key_findings": [{"finding": "自动化可节省成本", "impact": "高"}]}
    
    def _mock_sop_builder(self, user_prompt):
        fix_instructions = []
        try:
            fix_match = re.search(r"回环修复指令（必须逐条落实）：(.+?)(?:\n请在生成|$)", user_prompt, re.DOTALL)
            if fix_match: fix_instructions = json.loads(fix_match.group(1).strip())
        except: pass
        base_sops = [{"id": "SOP-001", "title": "业务处理流程", "owner_role": "业务专员", "trigger": "用户提交请求", "steps": [{"seq": 1, "action": "接收请求", "sla": "5分钟"}, {"seq": 2, "action": "智能分类", "sla": "2分钟"}, {"seq": 3, "action": "专业处理", "sla": "30分钟"}, {"seq": 4, "action": "质量审核", "sla": "10分钟"}, {"seq": 5, "action": "交付结果", "sla": "5分钟"}], "escalation": "超时升级", "review_cycle": "每日", "covers_constraints": ["R001-C1", "R001-C2", "R002-C1", "R002-C2"]}]
        if fix_instructions:
            for i, fix in enumerate(fix_instructions):
                if "内容合规" in fix:
                    base_sops.append({"id": f"SOP-{100+i}", "title": "内容合规闭环管控流程", "owner_role": "合规专员", "trigger": "内容发布", "steps": [{"seq": 1, "action": "自动审核", "sla": "5分钟"}, {"seq": 2, "action": "人工复核", "sla": "30分钟"}, {"seq": 3, "action": "违规处理", "sla": "15分钟"}, {"seq": 4, "action": "数据上报", "sla": "每日"}, {"seq": 5, "action": "月度复盘", "sla": "每月"}], "escalation": "重大违规升级", "review_cycle": "月度", "covers_constraints": ["R001-C3"]})
                elif "师资流失" in fix:
                    base_sops.append({"id": f"SOP-{100+i}", "title": "师资流失闭环管控流程", "owner_role": "HR经理", "trigger": "离职申请", "steps": [{"seq": 1, "action": "预警检测", "sla": "实时"}, {"seq": 2, "action": "离职面谈", "sla": "3天"}, {"seq": 3, "action": "挽留方案", "sla": "5天"}, {"seq": 4, "action": "原因分析", "sla": "1周"}, {"seq": 5, "action": "季度复盘", "sla": "每季度"}], "escalation": "核心人才升级CEO", "review_cycle": "季度", "covers_constraints": ["R002-C3"]})
                else:
                    base_sops.append({"id": f"SOP-{100+i}", "title": "补充流程", "owner_role": "业务经理", "trigger": "需求触发", "steps": [{"seq": 1, "action": "需求确认", "sla": "1天"}, {"seq": 2, "action": "方案制定", "sla": "3天"}, {"seq": 3, "action": "执行实施", "sla": "7天"}, {"seq": 4, "action": "效果评估", "sla": "1周"}, {"seq": 5, "action": "复盘优化", "sla": "2周"}], "escalation": "受阻升级", "review_cycle": "月度", "covers_constraints": []})
        return {"sop": {"sops": base_sops}}
    
    def _mock_reviewer(self, user_prompt):
        requirements = []
        try:
            req_match = re.search(r"需求/约束列表：(.+?)(?:\n业务模型|$)", user_prompt, re.DOTALL)
            if req_match: requirements = json.loads(req_match.group(1).strip())
        except: pass
        if not requirements:
            requirements = [{"id": "R001-C1", "title": "业务目标", "coverage": True}, {"id": "R001-C2", "title": "流程自动化", "coverage": True}, {"id": "R001-C3", "title": "内容合规", "coverage": False}, {"id": "R002-C1", "title": "成本控制", "coverage": True}, {"id": "R002-C2", "title": "质量保障", "coverage": True}, {"id": "R002-C3", "title": "师资流失", "coverage": False}]
        covered_by_sop = set()
        try:
            if "SOP：" in user_prompt:
                idx = user_prompt.find("SOP：") + 4
                sop_part = user_prompt[idx:].strip()
                if sop_part:
                    brace_count = 0
                    json_end = 0
                    for i, char in enumerate(sop_part):
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    if json_end > 0:
                        sop_str = sop_part[:json_end]
                        sop_data = json.loads(sop_str)
                        for sop in sop_data.get("sops", []):
                            covered_by_sop.update(sop.get("covers_constraints", []))
        except Exception as e:
            pass
        total = len(requirements)
        uncovered = [req for req in requirements if req["id"] not in covered_by_sop]
        coverage_pct = int((len(requirements)-len(uncovered))/total*100)
        gaps = [{"id": f"GAP-{i+1}", "severity": "high", "type": "constraint_uncovered", "desc": f"约束未覆盖：{req.get('title', '')}", "suggested_fix": f"在SOP中添加针对「{req.get('title', '')}」的闭环管控流程", "target": "sop", "constraint_id": req["id"]} for i, req in enumerate(uncovered)]
        loopback_fixes = [g["suggested_fix"] for g in gaps]
        summary = "约束覆盖率 100%，评审通过" if coverage_pct == 100 else f"约束覆盖率 {coverage_pct}%，{len(uncovered)} 项未覆盖"
        return {"review": {"approved": coverage_pct == 100, "constraint_coverage": {"total": total, "covered": total-len(uncovered), "uncovered_ids": [r["id"] for r in uncovered], "coverage_pct": coverage_pct}, "gaps": gaps, "loopback_target": "sop" if gaps else "null", "loopback_fixes": loopback_fixes, "summary": summary}}
    
    def _mock_dialog_question(self, user_prompt):
        return {"questions": [{"id": "q1", "question": "系统主要用户群体是谁？", "category": "用户需求"}, {"id": "q2", "question": "支持哪些核心业务流程？", "category": "业务流程"}]}
    
    def _mock_prd_generation(self, user_prompt):
        return {"prd": {"title": "产品需求文档", "version": "1.0", "sections": [{"section": "1. 项目背景", "content": "业务系统开发"}]}}
    
    def _mock_brainstorm_ideas(self, user_prompt):
        return {"ideas": [{"id": f"idea-{i+1}", "title": f"创意方案{i+1}", "description": "创新性解决方案", "impact": "高", "feasibility": "中"} for i in range(5)]}
    
    def _mock_brainstorm_mindmap(self, user_prompt):
        return {"mindmap": {"root": "核心主题", "nodes": [{"id": "node-1", "label": "分支1", "children": [{"id": "node-1-1", "label": "子节点1"}]}]}}
    
    def _mock_brainstorm_analysis(self, user_prompt):
        return {"analysis": {"problem": "核心问题", "causes": [{"cause": "原因1", "weight": 0.4}], "solutions": [{"solution": "解决方案1", "effectiveness": "高"}]}}
    
    # Compatibility implementations are intentionally defined last so they supersede
    # the earlier legacy methods without relying on damaged historical prompt text.
    def _get_agent_type(self, system_prompt: str) -> str | None:
        prompt = system_prompt.lower()
        if any(name in prompt for name in ("sop agent", "risk agent", "strategy agent", "optimization agent")):
            return AgentType.ANALYSIS.value
        if any(name in prompt for name in ("business understanding agent", "report composer")):
            return AgentType.GENERATION.value
        return None

    def _get_provider_for_agent(self, system_prompt: str) -> str:
        # Explicit mock mode is a hard execution policy, not a fallback
        # preference. Agent-specific defaults must not turn an offline test
        # or local dry run back into a real provider request.
        if self.force_mock or self.provider == ProviderType.MOCK.value:
            return ProviderType.MOCK.value
        agent_type = self._get_agent_type(system_prompt)
        if agent_type == AgentType.ANALYSIS.value:
            return settings.ANALYSIS_PROVIDER
        if agent_type == AgentType.GENERATION.value:
            return settings.GENERATION_PROVIDER
        return self.provider

    @staticmethod
    def _mock_allowed() -> bool:
        return not settings.is_production or settings.ALLOW_MOCK_LLM_IN_PRODUCTION

    @staticmethod
    def _fallback_allowed() -> bool:
        return not settings.is_production or settings.ALLOW_LLM_FALLBACK

    def _validate_execution_mode(self, provider: str) -> None:
        if (provider == ProviderType.MOCK.value or self.force_mock) and not self._mock_allowed():
            raise RuntimeError("mock LLM output is disabled in production")
        config = self.PROVIDERS.get(provider)
        if settings.is_production and provider != ProviderType.MOCK.value:
            if config is None:
                raise RuntimeError(f"unsupported production LLM provider: {provider}")
            if not getattr(settings, config["env_key"], "") and provider not in {"ollama", "vllm", "localai"}:
                raise RuntimeError(f"production LLM provider is not configured: {provider}")

    @staticmethod
    def _build_llm_cache_key(provider, system_prompt, user_prompt, temperature, max_tokens) -> str:
        payload = json.dumps(
            [provider, system_prompt, user_prompt, temperature, max_tokens],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None, use_cache=True):
        started = time.perf_counter()
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS
        provider = self._get_provider_for_agent(system_prompt)
        cache_key = self._build_llm_cache_key(provider, system_prompt, user_prompt, temperature, max_tokens)
        cache = getattr(self, "_response_cache", None)
        if cache is None:
            cache = self._response_cache = {}
        if use_cache and cache_key in cache:
            cached = copy.deepcopy(cache[cache_key])
            meta = cached.setdefault("_meta", {})
            mode = str(meta.get("mode", "api"))
            if mode == ProviderType.MOCK.value and not self._mock_allowed():
                raise RuntimeError("mock LLM output is disabled in production")
            if mode == "fallback" and not self._fallback_allowed():
                raise RuntimeError("LLM provider fallback is disabled in production")
            meta["cache_hit"] = True
            meta["elapsed_ms"] = 0
            return cached
        self._validate_execution_mode(provider)
        usage = ModelUsage(
            provider=provider,
            model=self._model_for_provider(provider),
        )
        if provider == ProviderType.MOCK.value or self.force_mock:
            result = self._mock(system_prompt, user_prompt)
            mode = ProviderType.MOCK.value
        else:
            try:
                result, usage = self._call_api_with_provider(
                    provider, system_prompt, user_prompt, temperature, max_tokens
                )
                mode = "api"
            except Exception as error:
                if not self._fallback_allowed():
                    raise RuntimeError("LLM provider failed; mock fallback is disabled") from error
                result = self._mock(system_prompt, user_prompt)
                mode = "fallback"
                result["_fallback_error"] = str(error)
        result["_meta"] = {
            "mode": mode,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "provider": usage.provider,
            "model": usage.model,
            "usage": usage.model_dump(mode="json"),
        }
        if use_cache:
            cache[cache_key] = copy.deepcopy(result)
        return result

    def _model_for_provider(self, provider: str) -> str:
        config = self.PROVIDERS.get(provider)
        if config is None:
            return self.model
        return getattr(settings, config["env_model"], config["default_model"])

    @staticmethod
    def _analyze_input_domain(text: str) -> dict:
        lowered = text.lower()
        if any(token in lowered for token in ("retail", "store", "ecommerce", "shop")):
            return {"domain_name": "Retail Operations", "department": "Operations", "role_prefix": "Store", "core_objective": "Improve conversion and service quality"}
        return {"domain_name": "Business Services", "department": "Operations", "role_prefix": "Business", "core_objective": "Improve operational efficiency"}

    def _mock(self, system_prompt, user_prompt):
        prompt = system_prompt.lower()
        domain_info = self._analyze_input_domain(user_prompt)
        if "sop builder agent" in prompt:
            return self._mock_sop_builder(user_prompt)
        if "reviewer agent" in prompt:
            return self._mock_reviewer(user_prompt)
        if "business understanding agent" in prompt:
            return self._mock_business_understanding(domain_info)
        if "sop agent" in prompt:
            return self._mock_sop(domain_info)
        if "risk agent" in prompt:
            return self._mock_risk(domain_info)
        if "strategy agent" in prompt:
            return self._mock_strategy(domain_info)
        if "optimization agent" in prompt:
            return self._mock_optimization(domain_info)
        if "report composer" in prompt:
            return self._mock_report_composer(domain_info)
        return {"content": "mock response"}

    def _mock_business_understanding(self, domain_info):
        return {
            "business_domain": domain_info["domain_name"],
            "core_objectives": [
                {"objective": domain_info["core_objective"], "target": "Improve by 20%", "priority": "high"},
                {"objective": "Reduce manual rework", "target": "Reduce by 30%", "priority": "medium"},
            ],
            "key_entities": [
                {"entity": "Customer request", "type": "input"},
                {"entity": "Business case", "type": "process"},
                {"entity": "Service outcome", "type": "output"},
            ],
            "process_flow": ["Receive request", "Classify request", "Process work", "Review quality", "Deliver outcome"],
            "success_metrics": [{"name": "Cycle time", "target": "< 30 minutes"}, {"name": "Quality rate", "target": ">= 98%"}],
            "constraints": ["Maintain service quality", "Protect customer data"],
            "industry_context": domain_info["domain_name"],
        }

    def _mock_sop(self, domain_info):
        workflow = [
            {"step": index, "name": name, "action": action}
            for index, (name, action) in enumerate(
                [("Intake", "Receive request"), ("Classify", "Classify request"), ("Process", "Complete work"), ("Review", "Validate quality"), ("Deliver", "Deliver result")],
                start=1,
            )
        ]
        return {
            "workflow": workflow,
            "roles": [
                {"role": "Operator", "department": domain_info["department"]},
                {"role": "Reviewer", "department": domain_info["department"]},
                {"role": "Manager", "department": domain_info["department"]},
            ],
            "sla": [{"metric": "Response time", "target": "< 5 minutes"}, {"metric": "Completion time", "target": "< 30 minutes"}],
            "kpi": [{"name": "Quality rate", "target": ">= 98%"}],
        }

    def _mock_risk(self, domain_info):
        return {
            "process_risks": [{"risk": "Processing bottleneck", "severity": "critical", "probability": "high", "mitigation": "Automate routing"}],
            "organization_risks": [{"risk": "Staff turnover", "severity": "high", "probability": "medium", "mitigation": "Cross-train staff"}],
            "system_risks": [{"risk": "Service outage", "severity": "critical", "probability": "medium", "mitigation": "Monitor and fail over"}],
            "compliance_risks": [{"risk": "Compliance gap", "severity": "critical", "probability": "medium", "mitigation": "Add review controls"}],
        }

    def _mock_strategy(self, domain_info):
        return {
            "growth_opportunities": [{"opportunity": "Workflow automation", "potential": "High", "priority": "high"}, {"opportunity": "Service analytics", "potential": "Medium", "priority": "medium"}],
            "strategic_path": [{"phase": "Foundation", "theme": "Standardize", "timeline": "0-3 months"}, {"phase": "Scale", "theme": "Automate", "timeline": "3-6 months"}, {"phase": "Optimize", "theme": "Improve", "timeline": "6-12 months"}],
        }

    def _mock_report_composer(self, domain_info):
        return {
            "title": "\u4e1a\u52a1\u5206\u6790\u62a5\u544a",
            "executive_summary": "A complete operating model proposal.",
            "sections": [{"section": "Objectives", "content": domain_info["core_objective"]}, {"section": "Process", "content": "Standardize and automate operations."}, {"section": "Risks", "content": "Review controls and monitor service quality."}],
            "key_findings": [{"finding": "Automation reduces rework", "impact": "high"}],
        }

    def ocr_image(self, image_base64: str, image_format: str = "png") -> dict:
        if self.force_mock or self.provider == ProviderType.MOCK.value:
            if not self._mock_allowed():
                raise RuntimeError("mock OCR output is disabled in production")
            return {"success": True, "text": "Mock OCR result", "_meta": {"mode": "mock"}}
        return {"success": False, "text": "", "_meta": {"mode": "unavailable"}}

    @staticmethod
    def _format_error(error: Exception) -> dict:
        return {"error": str(error), "code": type(error).__name__, "traceback": traceback.format_exc(), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

    def _mock(self, system_prompt, user_prompt):
        if (self.force_mock or self.provider == ProviderType.MOCK.value) and not self._mock_allowed():
            raise RuntimeError("mock LLM output is disabled in production")
        prompt = system_prompt.lower()
        domain_info = self._analyze_input_domain(user_prompt)
        if "planner agent" in prompt:
            return {"project": {"name": "Business Project", "goal": domain_info["core_objective"], "industry": domain_info["domain_name"], "scope": {"in_scope": ["Core workflow"], "out_scope": []}, "actors": [{"role": "Operator", "description": "Handles requests"}]}, "requirements": [{"id": "REQ-1", "text": domain_info["core_objective"], "priority": "high", "source": "user"}]}
        if "business architect agent" in prompt:
            return {"business_model": {"flows": [{"id": "flow-1", "name": "Request handling", "description": "Process an incoming request", "steps": ["intake", "review", "complete"], "input": "request", "output": "outcome", "source_ref": []}], "roles": [{"id": "role-1", "name": "Operator", "responsibility": "Handle requests", "belongs_to_flow": "flow-1", "source_ref": []}], "rules": []}}
        if "reviewer agent" in prompt:
            return {"review": {"approved": True, "constraint_coverage": {"total": 1, "covered": 1, "uncovered_ids": [], "coverage_pct": 100}, "gaps": [], "loopback_target": None, "loopback_fixes": [], "summary": "Constraints covered"}}
        if "sop builder agent" in prompt:
            return self._mock_sop_builder(user_prompt)
        if "business understanding agent" in prompt:
            return self._mock_business_understanding(domain_info)
        if "sop agent" in prompt:
            return self._mock_sop(domain_info)
        if "risk agent" in prompt:
            return self._mock_risk(domain_info)
        if "strategy agent" in prompt:
            return self._mock_strategy(domain_info)
        if "optimization agent" in prompt:
            return self._mock_optimization(domain_info)
        if "report composer" in prompt:
            return self._mock_report_composer(domain_info)
        return {"content": "mock response"}

    def stream_chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        if self.provider == ProviderType.MOCK.value:
            mock_result = self._mock(system_prompt, user_prompt)
            json_str = json.dumps(mock_result, ensure_ascii=False)
            for i in range(0, len(json_str), 50):
                yield json_str[i:i+50]
                time.sleep(0.05)
            return
        yield ""
    
    def status(self):
        return {"provider": self.provider, "model": self.model, "api_key_set": bool(self.api_key)}

_thread_local = threading.local()

def get_thread_local_service():
    if not hasattr(_thread_local, 'llm_service'):
        _thread_local.llm_service = LLMService()
    return _thread_local.llm_service

def get_llm_service():
    try: return get_thread_local_service()
    except: return LLMService()

class LLMServiceFactory:
    @staticmethod
    def create(provider=None, force_mock=False):
        return LLMService(provider, force_mock)
    @staticmethod
    def get_analysis_service():
        return LLMService(settings.ANALYSIS_PROVIDER)
    @staticmethod
    def get_generation_service():
        return LLMService(settings.GENERATION_PROVIDER)
    @staticmethod
    def get_thread_local_instance():
        return get_thread_local_service()
    @staticmethod
    def get_global_instance():
        return get_llm_service()
    @staticmethod
    def create_instance(provider=None, force_mock=False):
        return LLMService(provider=provider, force_mock=force_mock)

__all__ = ["LLMService", "LLMServiceFactory", "get_llm_service", "get_thread_local_service", "ProviderType"]
