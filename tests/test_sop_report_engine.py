"""
SOP Report Engine测试用例

测试覆盖：
- SOPReportEngine类：各个汇报模块生成方法
- HTML/Markdown导出功能
- 异常处理和边界情况
"""
import pytest
from datetime import datetime


class TestSOPReportEngine:
    """SOP汇报引擎测试"""

    @pytest.fixture
    def engine(self):
        """创建SOPReportEngine实例"""
        from app.engines.sop_report_engine import SOPReportEngine
        return SOPReportEngine()

    @pytest.fixture
    def mock_business_system(self, mock_llm_service):
        """创建Mock业务系统数据"""
        llm = mock_llm_service
        
        bs = {
            "business_domain": "金融服务",
            "objectives": [
                {"objective": "提升交易处理效率"},
                {"objective": "降低风险损失"},
                {"objective": "优化客户体验"},
            ],
            "workflow": [
                {
                    "step": 1,
                    "name": "交易提交",
                    "action": "客户提交交易请求",
                    "role": "客户经理",
                    "input": "交易信息、客户身份",
                    "output": "交易申请单",
                    "sla": "5分钟",
                },
                {
                    "step": 2,
                    "name": "风险评估",
                    "action": "系统自动评估交易风险",
                    "role": "风控专员",
                    "input": "交易申请单",
                    "output": "风险评估报告",
                    "sla": "15分钟",
                },
                {
                    "step": 3,
                    "name": "审批决策",
                    "action": "审批人员做出审批决定",
                    "role": "审批主管",
                    "input": "风险评估报告",
                    "output": "审批结果",
                    "sla": "30分钟",
                },
                {
                    "step": 4,
                    "name": "执行交易",
                    "action": "执行交易并记录",
                    "role": "交易员",
                    "input": "审批结果",
                    "output": "交易完成凭证",
                    "sla": "10分钟",
                },
                {
                    "step": 5,
                    "name": "升级处理",
                    "action": "异常情况升级至上级处理",
                    "role": "高级审批",
                    "input": "异常交易信息",
                    "output": "升级处理结果",
                    "sla": "2小时",
                },
            ],
            "roles": [
                {
                    "role": "客户经理",
                    "department": "业务部",
                    "level": "初级",
                    "headcount": 10,
                },
                {
                    "role": "风控专员",
                    "department": "风控部",
                    "level": "中级",
                    "headcount": 5,
                },
                {
                    "role": "审批主管",
                    "department": "审批部",
                    "level": "高级",
                    "headcount": 3,
                },
                {
                    "role": "交易员",
                    "department": "交易部",
                    "level": "初级",
                    "headcount": 8,
                },
                {
                    "role": "高级审批",
                    "department": "管理层",
                    "level": "总监",
                    "headcount": 2,
                },
            ],
            "responsibilities": [
                {
                    "role": "客户经理",
                    "duties": [
                        "客户需求收集",
                        "交易信息审核",
                        "客户关系维护",
                    ],
                },
                {
                    "role": "风控专员",
                    "duties": [
                        "风险评估",
                        "异常检测",
                        "风险报告编制",
                    ],
                },
            ],
            "sla": [
                {"metric": "交易处理时间", "target": "< 60分钟", "owner": "交易部"},
                {"metric": "风险评估准确率", "target": "> 95%", "owner": "风控部"},
                {"metric": "客户满意度", "target": "> 90%", "owner": "业务部"},
            ],
            "kpi": [
                {"name": "交易量", "target": "1000笔/天", "owner": "交易部", "formula": "每日交易笔数"},
                {"name": "风险控制率", "target": "99.9%", "owner": "风控部", "formula": "风险事件控制数/总交易数"},
            ],
            "risks": [
                {"risk": "交易提交延迟", "severity": "high", "probability": "medium", "mitigation": "优化提交流程"},
                {"risk": "风险评估不准确", "severity": "critical", "probability": "low", "mitigation": "定期培训"},
                {"risk": "审批超时", "severity": "medium", "probability": "medium", "mitigation": "设置提醒机制"},
            ],
            "risk": {
                "process_risks": [
                    {"risk": "流程瓶颈导致延迟", "severity": "medium", "probability": "high", "mitigation": "流程优化"},
                ],
                "organization_risks": [
                    {"risk": "人员不足", "severity": "low", "probability": "medium", "mitigation": "招聘计划"},
                ],
                "system_risks": [
                    {"risk": "系统宕机", "severity": "critical", "probability": "low", "mitigation": "容灾备份"},
                ],
                "compliance_risks": [
                    {"risk": "合规违规", "severity": "high", "probability": "medium", "mitigation": "合规检查"},
                ],
            },
        }
        
        return bs

    def test_generate_overview(self, engine, mock_business_system):
        """测试流程概览生成"""
        overview = engine.generate_overview(mock_business_system)
        
        assert overview["title"] == "流程概览"
        assert overview["business_domain"] == "金融服务"
        assert overview["total_steps"] == 5
        assert overview["total_roles"] == 5
        assert overview["total_sla_items"] == 3
        assert overview["has_escalation"] is True
        assert len(overview["core_objectives"]) == 3
        assert overview["estimated_duration"] is not None

    def test_generate_workflow_detail(self, engine, mock_business_system):
        """测试详细流程生成"""
        workflow = engine.generate_workflow_detail(mock_business_system)
        
        assert workflow["title"] == "详细流程"
        assert workflow["total_steps"] == 5
        assert len(workflow["steps"]) == 5
        
        for step in workflow["steps"]:
            assert "step" in step
            assert "name" in step
            assert "action" in step
            assert "role" in step
            assert "input" in step
            assert "output" in step
            assert "sla" in step

    def test_generate_role_responsibilities(self, engine, mock_business_system):
        """测试角色职责生成"""
        roles = engine.generate_role_responsibilities(mock_business_system)
        
        assert roles["title"] == "角色职责"
        assert roles["total_roles"] == 5
        
        role_names = [r["name"] for r in roles["roles"]]
        assert "客户经理" in role_names
        assert "风控专员" in role_names
        assert "审批主管" in role_names
        
        for role in roles["roles"]:
            assert "name" in role
            assert "department" in role
            assert "level" in role
            assert "headcount" in role
            assert "responsible_steps" in role
            assert "responsibilities" in role

    def test_generate_sla_summary(self, engine, mock_business_system):
        """测试SLA汇总生成"""
        sla = engine.generate_sla_summary(mock_business_system)
        
        assert sla["title"] == "SLA汇总"
        assert sla["total_sla_items"] == 5
        assert sla["total_step_slas"] == 5
        assert sla["estimated_total_duration"] is not None
        
        for item in sla["sla_items"]:
            assert "metric" in item
            assert "target" in item
            assert "owner" in item
            assert "type" in item

    def test_generate_risk_assessment(self, engine, mock_business_system):
        """测试风险评估生成"""
        risk = engine.generate_risk_assessment(mock_business_system)
        
        assert risk["title"] == "风险评估"
        assert risk["total_risks"] >= 1
        assert "severity_distribution" in risk
        
        for r in risk["risks"]:
            assert "risk" in r
            assert "severity" in r
            assert "probability" in r
            assert "mitigation" in r
            assert "category" in r

    def test_generate_flowchart(self, engine, mock_business_system):
        """测试流程图数据生成"""
        flowchart = engine.generate_flowchart(mock_business_system)
        
        assert flowchart["title"] == "流程图"
        assert flowchart["total_nodes"] == 5
        assert flowchart["total_edges"] == 4
        assert len(flowchart["nodes"]) == 5
        assert len(flowchart["edges"]) == 4
        
        for node in flowchart["nodes"]:
            assert "id" in node
            assert "step" in node
            assert "name" in node
            assert "role" in node
        
        for edge in flowchart["edges"]:
            assert "from" in edge
            assert "to" in edge

    def test_generate_full_sop_report(self, engine, mock_business_system):
        """测试完整SOP汇报生成"""
        report = engine.generate_full_sop_report(mock_business_system)
        
        assert "title" in report
        assert "金融服务SOP汇报" in report["title"]
        assert "generated_at" in report
        assert "overview" in report
        assert "workflow_detail" in report
        assert "role_responsibilities" in report
        assert "sla_summary" in report
        assert "risk_assessment" in report
        assert "flowchart" in report

    def test_export_to_markdown(self, engine, mock_business_system):
        """测试Markdown导出"""
        report = engine.generate_full_sop_report(mock_business_system)
        md_content = engine.export_to_markdown(report)
        
        assert isinstance(md_content, str)
        assert len(md_content) > 0
        assert "# " in md_content
        assert "##" in md_content
        assert "流程概览" in md_content
        assert "详细流程" in md_content
        assert "角色职责" in md_content
        assert "SLA汇总" in md_content
        assert "风险评估" in md_content
        assert "流程图" in md_content
        assert "mermaid" in md_content

    def test_export_to_html(self, engine, mock_business_system):
        """测试HTML导出"""
        report = engine.generate_full_sop_report(mock_business_system)
        html_content = engine.export_to_html(report)
        
        assert isinstance(html_content, str)
        assert len(html_content) > 0
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "<head>" in html_content
        assert "<body>" in html_content
        assert "流程概览" in html_content
        assert "详细流程" in html_content
        assert "角色职责" in html_content
        assert "SLA汇总" in html_content
        assert "风险评估" in html_content
        assert "流程图" in html_content

    def test_export_to_pptx(self, engine, mock_business_system):
        """测试PPTX导出"""
        report = engine.generate_full_sop_report(mock_business_system)
        pptx_path = engine.export_to_pptx(report)
        
        assert isinstance(pptx_path, str)
        assert pptx_path.endswith(".pptx")
        import os
        assert os.path.exists(pptx_path)
        assert os.path.getsize(pptx_path) > 0
        
        os.remove(pptx_path)

    def test_export_to_pptx_with_custom_path(self, engine, mock_business_system):
        """测试自定义路径PPTX导出"""
        import os
        import tempfile
        
        report = engine.generate_full_sop_report(mock_business_system)
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            custom_path = f.name
        
        try:
            pptx_path = engine.export_to_pptx(report, output_path=custom_path)
            assert pptx_path == custom_path
            assert os.path.exists(pptx_path)
            assert os.path.getsize(pptx_path) > 0
        finally:
            if os.path.exists(custom_path):
                os.remove(custom_path)

    def test_estimate_total_duration(self, engine):
        """测试总耗时估算"""
        workflow = [
            {"sla": "5分钟"},
            {"sla": "15分钟"},
            {"sla": "2小时"},
            {"sla": "1天"},
        ]
        
        duration = engine._estimate_total_duration(workflow)
        
        assert isinstance(duration, str)
        assert "天" in duration or "小时" in duration or "分钟" in duration

    def test_get_step_risks(self, engine):
        """测试步骤风险匹配"""
        step = {"name": "风险评估", "action": "评估交易风险", "role": "风控专员"}
        risks = [
            {"risk": "风险评估不准确"},
            {"risk": "交易提交延迟"},
            {"risk": "风控专员操作失误"},
        ]
        
        step_risks = engine._get_step_risks(step, risks)
        
        assert len(step_risks) >= 1
        assert any("风险评估" in r.get("risk", "") for r in step_risks)
        assert any("风控专员" in r.get("risk", "") for r in step_risks)


class TestSOPReportEngineEdgeCases:
    """SOP汇报引擎边界情况测试"""

    @pytest.fixture
    def engine(self):
        from app.engines.sop_report_engine import SOPReportEngine
        return SOPReportEngine()

    def test_empty_business_system(self, engine):
        """测试空业务系统数据"""
        empty_bs = {}
        
        overview = engine.generate_overview(empty_bs)
        assert overview["total_steps"] == 0
        assert overview["total_roles"] == 0
        assert overview["total_sla_items"] == 0
        
        workflow = engine.generate_workflow_detail(empty_bs)
        assert workflow["total_steps"] == 0
        
        roles = engine.generate_role_responsibilities(empty_bs)
        assert roles["total_roles"] == 0

    def test_missing_workflow(self, engine):
        """测试缺失workflow数据"""
        bs = {
            "business_domain": "测试领域",
            "roles": [{"role": "测试角色"}],
        }
        
        workflow = engine.generate_workflow_detail(bs)
        assert workflow["total_steps"] == 0
        
        flowchart = engine.generate_flowchart(bs)
        assert flowchart["total_nodes"] == 0

    def test_missing_roles(self, engine):
        """测试缺失roles数据"""
        bs = {
            "business_domain": "测试领域",
            "workflow": [{"step": 1, "name": "测试步骤", "action": "测试动作"}],
        }
        
        roles = engine.generate_role_responsibilities(bs)
        assert roles["total_roles"] == 0

    def test_empty_risks(self, engine):
        """测试空风险数据"""
        bs = {
            "business_domain": "测试领域",
            "risks": [],
            "risk": {},
        }
        
        risk = engine.generate_risk_assessment(bs)
        assert risk["total_risks"] == 0

    def test_export_empty_report(self, engine):
        """测试导出空汇报"""
        empty_report = {
            "title": "空汇报",
            "generated_at": datetime.now().isoformat(),
            "overview": {"title": "流程概览", "description": "", "business_domain": "", "core_objectives": [], "total_steps": 0, "total_roles": 0, "total_sla_items": 0, "has_escalation": False, "estimated_duration": ""},
            "workflow_detail": {"title": "详细流程", "description": "", "steps": [], "total_steps": 0},
            "role_responsibilities": {"title": "角色职责", "description": "", "roles": [], "total_roles": 0},
            "sla_summary": {"title": "SLA汇总", "description": "", "sla_items": [], "step_slas": [], "total_sla_items": 0, "total_step_slas": 0, "estimated_total_duration": ""},
            "risk_assessment": {"title": "风险评估", "description": "", "risks": [], "total_risks": 0, "severity_distribution": {}},
            "flowchart": {"title": "流程图", "description": "", "nodes": [], "edges": [], "total_nodes": 0, "total_edges": 0},
        }
        
        md_content = engine.export_to_markdown(empty_report)
        assert isinstance(md_content, str)
        
        html_content = engine.export_to_html(empty_report)
        assert isinstance(html_content, str)
        assert "<!DOCTYPE html>" in html_content


class TestSOPReportAPI:
    """SOP汇报API测试"""

    @pytest.fixture
    def client(self):
        """创建FastAPI测试客户端"""
        from fastapi.testclient import TestClient
        from app.main import app
        
        return TestClient(app)

    @pytest.fixture
    def mock_business_system_data(self):
        """Mock业务系统数据"""
        return {
            "business_domain": "测试领域",
            "objectives": [{"objective": "测试目标"}],
            "workflow": [
                {"step": 1, "name": "步骤1", "action": "动作1", "role": "角色A", "input": "输入1", "output": "输出1", "sla": "10分钟"},
            ],
            "roles": [{"role": "角色A", "department": "测试部", "level": "初级", "headcount": 1}],
            "sla": [{"metric": "测试指标", "target": "目标值", "owner": "测试部"}],
            "risks": [{"risk": "测试风险", "severity": "medium", "probability": "low", "mitigation": "缓解措施"}],
        }

    def test_generate_report_endpoint(self, client, mock_business_system_data):
        """测试生成汇报接口"""
        response = client.post(
            "/sop-report/generate",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "data" in data
        report = data["data"]
        assert "title" in report
        assert "overview" in report
        assert "workflow_detail" in report

    def test_export_markdown_endpoint(self, client, mock_business_system_data):
        """测试导出Markdown接口"""
        response = client.post(
            "/sop-report/export",
            json={"business_system": mock_business_system_data, "format": "markdown"},
        )
        
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "Content-Disposition" in response.headers
        assert ".md" in response.headers["Content-Disposition"]

    def test_export_html_endpoint(self, client, mock_business_system_data):
        """测试导出HTML接口"""
        response = client.post(
            "/sop-report/export",
            json={"business_system": mock_business_system_data, "format": "html"},
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Content-Disposition" in response.headers
        assert ".html" in response.headers["Content-Disposition"]

    def test_export_invalid_format(self, client, mock_business_system_data):
        """测试无效导出格式"""
        response = client.post(
            "/sop-report/export",
            json={"business_system": mock_business_system_data, "format": "pdf"},
        )
        
        assert response.status_code == 422

    def test_export_pptx_endpoint(self, client, mock_business_system_data):
        """测试导出PPTX接口"""
        response = client.post(
            "/sop-report/export",
            json={"business_system": mock_business_system_data, "format": "pptx"},
        )
        
        assert response.status_code == 200
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in response.headers["content-type"]
        assert "Content-Disposition" in response.headers
        assert ".pptx" in response.headers["Content-Disposition"]
        assert len(response.content) > 0

    def test_overview_endpoint(self, client, mock_business_system_data):
        """测试流程概览接口"""
        response = client.post(
            "/sop-report/overview",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "流程概览"

    def test_workflow_endpoint(self, client, mock_business_system_data):
        """测试详细流程接口"""
        response = client.post(
            "/sop-report/workflow",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "详细流程"

    def test_roles_endpoint(self, client, mock_business_system_data):
        """测试角色职责接口"""
        response = client.post(
            "/sop-report/roles",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "角色职责"

    def test_sla_endpoint(self, client, mock_business_system_data):
        """测试SLA汇总接口"""
        response = client.post(
            "/sop-report/sla",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "SLA汇总"

    def test_risk_endpoint(self, client, mock_business_system_data):
        """测试风险评估接口"""
        response = client.post(
            "/sop-report/risk",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "风险评估"

    def test_flowchart_endpoint(self, client, mock_business_system_data):
        """测试流程图数据接口"""
        response = client.post(
            "/sop-report/flowchart",
            json={"business_system": mock_business_system_data},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "流程图"

    def test_preview_endpoint(self, client):
        """测试预览接口"""
        response = client.get("/sop-report/preview")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def test_generate_ai_summary_schema_under_mock():
    from app.engines.sop_report_engine import SOPReportEngine

    engine = SOPReportEngine()
    bs = {
        "business_domain": "测试业务",
        "workflow": [{"name": "步骤1", "owner": "角色A", "duration": "2h"}],
        "roles": [{"role": "角色A", "department": "测试部", "headcount": 1}],
        "risks": [{"risk": "风险X", "severity": "高", "mitigation": "加强监控"}],
    }
    out = engine.generate_ai_summary(bs)
    assert out["title"] == "智能摘要"
    assert isinstance(out["executive_summary"], str) and out["executive_summary"]
    assert isinstance(out["key_findings"], list)
    assert isinstance(out["recommendations"], list)
    assert isinstance(out["risk_highlights"], list)


def test_generate_full_report_includes_ai_when_enabled():
    from app.engines.sop_report_engine import SOPReportEngine

    engine = SOPReportEngine()
    bs = {
        "business_domain": "测试业务",
        "workflow": [{"name": "步骤1", "owner": "角色A", "duration": "2h"}],
        "roles": [{"role": "角色A", "department": "测试部", "headcount": 1}],
        "risks": [{"risk": "风险X", "severity": "高", "mitigation": "加强监控"}],
    }
    report = engine.generate_full_sop_report(bs, enable_ai_analysis=True)
    assert "ai_summary" in report
    assert "ai_recommendations" in report
    assert report["ai_summary"]["executive_summary"]
    assert report["ai_recommendations"]["optimization_suggestions"]