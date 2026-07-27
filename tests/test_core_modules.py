"""
核心模块单元测试

测试覆盖：
- LLMService: 缓存功能、Agent路由、Mock模式、OCR功能
- BSCPipeline: 完整流程执行、缓存验证、阶段执行
- 异常处理: 错误格式化、异常回退机制
"""
from app.core.config import settings


class TestLLMServiceCache:
    """LLM服务缓存功能测试"""

    def test_llm_cache_hit(self, mock_llm_service):
        """测试LLM调用缓存命中"""
        system_prompt = "你是SOP Agent"
        user_prompt = "测试PRD内容"
        
        result1 = mock_llm_service.chat(system_prompt, user_prompt, use_cache=True)
        result2 = mock_llm_service.chat(system_prompt, user_prompt, use_cache=True)
        
        assert result2["_meta"]["mode"] == "mock"
        assert result2["_meta"]["cache_hit"] is True
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
        from app.services.llm_service import LLMService

        provider = LLMService(provider="deepseek")._get_provider_for_agent(system_prompt)

        assert provider == "deepseek"

    def test_generation_agent_routing(self, mock_llm_service, monkeypatch):
        """生成类Agent应路由到GENERATION_PROVIDER（设计默认doubao）"""
        monkeypatch.setattr(settings, "GENERATION_PROVIDER", "doubao")
        system_prompt = "你是Business Understanding Agent"
        from app.services.llm_service import LLMService

        provider = LLMService(provider="deepseek")._get_provider_for_agent(system_prompt)

        assert provider == "doubao"

    def test_mock_mode_overrides_agent_specific_provider_routing(self, mock_llm_service, monkeypatch):
        monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "deepseek")
        monkeypatch.setattr(settings, "GENERATION_PROVIDER", "doubao")

        assert mock_llm_service._get_provider_for_agent("浣犳槸SOP Agent") == "mock"
        assert mock_llm_service._get_provider_for_agent("浣犳槸Business Understanding Agent") == "mock"

    def test_explicit_mock_mode_wins_for_recognized_agent_prompts(self, mock_llm_service):
        analysis_prompt = "\u4f60\u662fSOP Agent"
        generation_prompt = "\u4f60\u662fBusiness Understanding Agent"

        assert mock_llm_service._get_provider_for_agent(analysis_prompt) == "mock"
        assert mock_llm_service._get_provider_for_agent(generation_prompt) == "mock"

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


class TestBusinessSystemSmoke:
    """Business System核心字段完整性测试（Smoke测试）"""

    def test_business_system_core_fields_not_empty(self, mock_llm_service):
        """测试business_system核心字段非空"""
        from app.core.bsc_pipeline import compile_to_business_system
        
        prd = """# 零售电商系统PRD
业务目标：提升用户转化率至3%
核心功能：商品管理、订单管理、用户管理
"""
        
        result = compile_to_business_system(prd, llm_service=mock_llm_service)
        bs = result["business_system"]
        
        assert bs.get("business_domain"), "business_domain不能为空"
        assert len(bs.get("objectives", [])) > 0, "objectives不能为空列表"
        assert len(bs.get("workflow", [])) > 0, "workflow不能为空列表"
        assert len(bs.get("roles", [])) > 0, "roles不能为空列表"
        assert len(bs.get("kpi", [])) > 0 or len(bs.get("metrics", [])) > 0, "kpi或metrics至少有一个非空"
        assert len(bs.get("risks", [])) > 0 or len(bs.get("risk", {}).get("process_risks", [])) > 0, "risks不能为空"
        assert bs.get("composed", {}).get("report", {}).get("title"), "composed.report.title不能为空"

    def test_business_system_fallback_on_empty(self, mock_llm_service):
        """测试空数据时的回退机制"""
        from app.core.bsc_pipeline import _validate_business_system_integrity, _generate_fallback_business_system
        
        empty_bs = {
            "business_domain": "",
            "objectives": [],
            "workflow": [],
            "roles": [],
            "kpi": [],
            "risks": [],
            "risk": {},
            "composed": {},
            "report": {},
        }
        
        assert _validate_business_system_integrity(empty_bs) is False, "空数据应返回False"
        
        fallback_bs = _generate_fallback_business_system("在线教育平台PRD")
        assert fallback_bs.get("business_domain"), "回退数据business_domain不应为空"
        assert len(fallback_bs.get("objectives", [])) > 0, "回退数据objectives不应为空"
        assert len(fallback_bs.get("workflow", [])) > 0, "回退数据workflow不应为空"
        assert _validate_business_system_integrity(fallback_bs) is True, "回退数据应通过完整性校验"

    def test_business_system_risks_structure(self, mock_llm_service):
        """测试risks数据结构一致性"""
        from app.core.bsc_pipeline import compile_to_business_system
        
        prd = """# 金融风控系统PRD
业务目标：建立实时风控体系
核心功能：交易监控、风险评估
"""
        
        result = compile_to_business_system(prd, llm_service=mock_llm_service)
        bs = result["business_system"]
        
        all_risks = bs.get("risks", [])
        risk_breakdown = bs.get("risk", {})
        
        assert isinstance(all_risks, list), "risks应为列表"
        assert isinstance(risk_breakdown, dict), "risk应为字典"
        
        for risk_item in all_risks:
            assert isinstance(risk_item, dict), "每个risk应为字典"
            assert "risk" in risk_item, "risk项应包含risk字段"
            assert "severity" in risk_item or "level" in risk_item, "risk项应包含severity或level字段"

    def test_business_system_workflow_structure(self, mock_llm_service):
        """测试workflow数据结构"""
        from app.core.bsc_pipeline import compile_to_business_system
        
        prd = """# 客服工单系统PRD
业务目标：提升客户满意度
核心功能：工单创建、工单分配、工单处理
"""
        
        result = compile_to_business_system(prd, llm_service=mock_llm_service)
        workflow = result["business_system"].get("workflow", [])
        
        assert isinstance(workflow, list)
        assert len(workflow) > 0
        
        for step in workflow:
            assert isinstance(step, dict)
            assert "step" in step, "步骤应包含step序号"
            assert "name" in step, "步骤应包含name"
            assert "action" in step, "步骤应包含action"


class TestBSCPipelineCache:
    """BSC Pipeline缓存功能测试"""

    def test_pipeline_cache_enabled(self, mock_llm_service):
        """测试Pipeline缓存功能"""
        from app.core.bsc_pipeline import BSCPipeline
        
        pipeline = BSCPipeline(llm_service=mock_llm_service)
        
        result1 = pipeline.execute("测试PRD内容")
        result2 = pipeline.execute("测试PRD内容")
        
        assert result1["total_ms"] >= 0
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
        from app.services.llm_service import LLMServiceFactory
        
        factory = LLMServiceFactory()
        
        thread_local = factory.get_thread_local_instance()
        global_instance = factory.get_global_instance()
        independent = factory.create_instance(provider="mock")
        
        assert thread_local is not None
        assert global_instance is not None
        assert independent is not None
        assert independent.provider == "mock"
