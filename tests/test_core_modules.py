"""
核心模块单元测试

测试覆盖：
- LLMService: 缓存功能、Agent路由、Mock模式、OCR功能
- BSCPipeline: 完整流程执行、缓存验证、阶段执行
- 异常处理: 错误格式化、异常回退机制
"""
import pytest
from app.core.config import settings


class TestLLMServiceCache:
    """LLM服务缓存功能测试"""

    def test_llm_cache_hit(self, mock_llm_service):
        """测试LLM调用缓存命中"""
        system_prompt = "你是SOP Agent"
        user_prompt = "测试PRD内容"
        
        result1 = mock_llm_service.chat(system_prompt, user_prompt, use_cache=True)
        result2 = mock_llm_service.chat(system_prompt, user_prompt, use_cache=True)
        
        assert result2["_meta"]["mode"] == "cache"
        assert "workflow" in result1
        assert "workflow" in result2
        assert result1["workflow"] == result2["workflow"]

    def test_llm_cache_disabled(self, mock_llm_service):
        """测试禁用缓存"""
        system_prompt = "你是SOP Agent"
        user_prompt = "测试PRD内容"
        
        result1 = mock_llm_service.chat(system_prompt, user_prompt, use_cache=False)
        result2 = mock_llm_service.chat(system_prompt, user_prompt, use_cache=False)
        
        assert result1["_meta"]["mode"] == "mock"
        assert result2["_meta"]["mode"] == "mock"

    def test_llm_cache_different_prompts(self, mock_llm_service):
        """测试不同prompt不共享缓存"""
        system_prompt = "你是SOP Agent"
        user_prompt1 = "测试PRD内容1"
        user_prompt2 = "测试PRD内容2"
        
        result1 = mock_llm_service.chat(system_prompt, user_prompt1, use_cache=True)
        result2 = mock_llm_service.chat(system_prompt, user_prompt2, use_cache=True)
        
        assert result1["_meta"]["mode"] == "mock"
        assert result2["_meta"]["mode"] == "mock"

    def test_llm_cache_key_generation(self, mock_llm_service):
        """测试缓存键生成"""
        cache_key1 = mock_llm_service._build_llm_cache_key(
            "mock", "system1", "user1", 0.7, 8000
        )
        cache_key2 = mock_llm_service._build_llm_cache_key(
            "mock", "system1", "user1", 0.7, 8000
        )
        cache_key3 = mock_llm_service._build_llm_cache_key(
            "deepseek", "system1", "user1", 0.7, 8000
        )
        
        assert cache_key1 == cache_key2
        assert cache_key1 != cache_key3


class TestLLMServiceRouting:
    """LLM服务路由功能测试"""

    def test_analysis_agent_routing(self, mock_llm_service, monkeypatch):
        """分析类Agent应路由到ANALYSIS_PROVIDER（设计默认deepseek）"""
        monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "deepseek")
        system_prompt = "你是SOP Agent"
        provider = mock_llm_service._get_provider_for_agent(system_prompt)

        assert provider == "deepseek"

    def test_generation_agent_routing(self, mock_llm_service, monkeypatch):
        """生成类Agent应路由到GENERATION_PROVIDER（设计默认doubao）"""
        monkeypatch.setattr(settings, "GENERATION_PROVIDER", "doubao")
        system_prompt = "你是Business Understanding Agent"
        provider = mock_llm_service._get_provider_for_agent(system_prompt)

        assert provider == "doubao"

    def test_agent_type_detection(self, mock_llm_service):
        """测试Agent类型检测"""
        assert mock_llm_service._get_agent_type("你是SOP Agent") == "analysis"
        assert mock_llm_service._get_agent_type("你是Risk Agent") == "analysis"
        assert mock_llm_service._get_agent_type("你是Business Understanding Agent") == "generation"
        assert mock_llm_service._get_agent_type("未知Agent") is None


class TestLLMServiceMock:
    """LLM服务Mock模式测试"""

    def test_mock_business_understanding(self, mock_llm_service):
        """测试业务理解Mock数据"""
        result = mock_llm_service._mock_business_understanding({
            "domain_name": "零售电商",
            "core_objective": "用户体验与转化",
            "role_prefix": "电商",
        })
        
        assert result["business_domain"] == "零售电商"
        assert len(result["core_objectives"]) >= 2
        assert len(result["key_entities"]) >= 3

    def test_mock_sop(self, mock_llm_service):
        """测试SOP Mock数据"""
        result = mock_llm_service._mock_sop({
            "domain_name": "金融服务",
            "role_prefix": "金融",
            "department": "金融部",
        })
        
        assert len(result["workflow"]) == 5
        assert len(result["roles"]) == 3
        assert len(result["sla"]) >= 2

    def test_mock_risk(self, mock_llm_service):
        """测试风险分析Mock数据"""
        result = mock_llm_service._mock_risk({
            "role_prefix": "业务",
        })
        
        assert len(result["process_risks"]) >= 1
        assert len(result["organization_risks"]) >= 1
        assert len(result["system_risks"]) >= 1
        assert len(result["compliance_risks"]) >= 1

    def test_mock_strategy(self, mock_llm_service):
        """测试战略分析Mock数据"""
        result = mock_llm_service._mock_strategy({
            "domain_name": "智能制造",
            "role_prefix": "制造",
        })
        
        assert len(result["growth_opportunities"]) >= 2
        assert len(result["strategic_path"]) == 3

    def test_mock_optimization(self, mock_llm_service):
        """测试优化建议Mock数据"""
        result = mock_llm_service._mock_optimization({
            "role_prefix": "业务",
        })
        
        assert len(result["recommendations"]) >= 1
        assert len(result["roi_estimation"]) >= 1

    def test_mock_report_composer(self, mock_llm_service):
        """测试报告生成Mock数据"""
        result = mock_llm_service._mock_report_composer({
            "domain_name": "企业服务",
            "core_objective": "效率提升",
        })
        
        assert "业务分析报告" in result["title"]
        assert len(result["sections"]) >= 3


class TestLLMServiceOCR:
    """LLM服务OCR功能测试"""

    def test_ocr_mock_mode(self, mock_llm_service):
        """测试OCR Mock模式"""
        result = mock_llm_service.ocr_image("dummy_base64_image", "png")
        
        assert result["success"] is True
        assert len(result["text"]) > 0
        assert result["_meta"]["mode"] == "mock"


class TestBSCPipeline:
    """BSC Pipeline流程测试"""

    def test_pipeline_basic_execution(self, mock_llm_service):
        """测试Pipeline基本执行流程"""
        from app.core.bsc_pipeline import BSCPipeline
        
        pipeline = BSCPipeline(llm_service=mock_llm_service)
        result = pipeline.execute("这是一份测试PRD文档，关于零售电商业务系统。")
        
        assert "business_understanding" in result
        assert "sop" in result
        assert "risk" in result
        assert "strategy" in result
        assert "composed" in result
        assert "workspace" in result

    def test_pipeline_stages_executed(self, mock_llm_service):
        """测试所有阶段都被执行"""
        from app.core.bsc_pipeline import BSCPipeline
        
        pipeline = BSCPipeline(llm_service=mock_llm_service)
        result = pipeline.execute("测试PRD内容")
        
        stages = result.get("stages", [])
        stage_keys = [stage.get("key") for stage in stages]
        
        assert "business_understanding" in stage_keys
        assert "sop" in stage_keys
        assert "risk" in stage_keys
        assert "strategy" in stage_keys
        assert "composer" in stage_keys

    def test_pipeline_plan_generated(self, mock_llm_service):
        """测试Planner生成执行计划"""
        from app.core.bsc_pipeline import BSCPipeline
        
        pipeline = BSCPipeline(llm_service=mock_llm_service)
        result = pipeline.execute("测试PRD内容")
        
        plan = result.get("plan", {})
        assert "agents" in plan
        assert "execution_order" in plan
        assert len(plan["agents"]) > 0

    def test_pipeline_workspace_generated(self, mock_llm_service):
        """测试Workspace数据生成"""
        from app.core.bsc_pipeline import BSCPipeline
        
        pipeline = BSCPipeline(llm_service=mock_llm_service)
        result = pipeline.execute("测试PRD内容")
        
        workspace = result.get("workspace", {})
        assert "dashboard" in workspace
        assert "report" in workspace
        assert "ppt_blueprint" in workspace
        
        dashboard = workspace["dashboard"]
        assert "business_domain" in dashboard
        assert "objectives_count" in dashboard
        assert "risk_count" in dashboard

    def test_pipeline_compile_function(self, mock_llm_service):
        """测试compile_to_business_system函数"""
        from app.core.bsc_pipeline import compile_to_business_system
        
        result = compile_to_business_system("测试PRD内容", llm_service=mock_llm_service)
        
        assert "business_system" in result
        assert "pipeline" in result
        assert "summary" in result
        
        bs = result["business_system"]
        assert "business_domain" in bs
        assert "objectives" in bs
        assert "workflow" in bs
        assert "risks" in bs


class TestBSCPipelineCache:
    """BSC Pipeline缓存功能测试"""

    def test_pipeline_cache_enabled(self, mock_llm_service):
        """测试Pipeline缓存功能"""
        from app.core.bsc_pipeline import BSCPipeline
        
        pipeline = BSCPipeline(llm_service=mock_llm_service)
        
        result1 = pipeline.execute("测试PRD内容")
        result2 = pipeline.execute("测试PRD内容")
        
        assert result1["total_ms"] > 0
        assert "workspace" in result1
        assert "workspace" in result2


class TestExceptionHandling:
    """异常处理测试"""

    def test_error_formatting(self, mock_llm_service):
        """测试错误格式化"""
        try:
            raise ValueError("测试错误")
        except ValueError as e:
            error_info = mock_llm_service._format_error(e)
            
            assert "error" in error_info
            assert "code" in error_info
            assert "traceback" in error_info
            assert "timestamp" in error_info
            assert error_info["error"] == "测试错误"
            assert error_info["code"] == "ValueError"

    def test_llm_fallback_to_mock(self, mock_llm_service):
        """测试LLM调用失败时回退到Mock模式"""
        mock_llm_service.provider = "deepseek"
        
        result = mock_llm_service.chat("你是SOP Agent", "测试内容")
        
        assert result["_meta"]["mode"] == "mock" or result["_meta"]["mode"] == "fallback"


class TestThreadSafety:
    """线程安全测试"""

    def test_thread_local_service(self):
        """测试线程本地服务获取"""
        from app.core.llm_service import get_thread_local_service
        
        service1 = get_thread_local_service()
        service2 = get_thread_local_service()
        
        assert service1 is service2

    def test_llm_service_factory(self):
        """测试LLM服务工厂"""
        from app.core.llm_service import LLMServiceFactory
        
        factory = LLMServiceFactory()
        
        thread_local = factory.get_thread_local_instance()
        global_instance = factory.get_global_instance()
        independent = factory.create_instance(provider="mock")
        
        assert thread_local is not None
        assert global_instance is not None
        assert independent is not None
        assert independent.provider == "mock"