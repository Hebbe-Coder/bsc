"""
集成测试 - 端到端流程测试

测试覆盖：
- API编译流程（同步/异步）
- 文件上传编译
- 阶段单独执行
- 导出功能
- 健康检查
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def test_client():
    """创建测试客户端"""
    from app.main import app
    return TestClient(app)


class TestAPIIntegration:
    """API集成测试"""

    def test_health_check(self, test_client):
        """测试健康检查接口"""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "version" in data

    def test_compile_sync(self, test_client):
        """测试同步编译接口"""
        test_prd = """# 零售电商系统PRD

## 业务目标
- 提升用户转化率至3%
- 优化供应链效率

## 核心功能
- 商品管理
- 订单管理
- 用户管理
"""
        
        response = test_client.post(
            "/bsc/compile/sync",
            json={"input": test_prd, "output_types": ["json"]},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        
        result = data["data"]
        assert "business_system" in result
        assert "pipeline" in result
        assert "composed" in result
        assert "workspace" in result
        assert result.get("parallel") is False

    def test_compile_async(self, test_client):
        """测试异步编译接口"""
        test_prd = """# 内容审核系统PRD

## 业务目标
- 建立完善的内容审核体系
- 确保平台内容合规性

## 核心功能
- 图片审核
- 文本审核
"""
        
        response = test_client.post(
            "/bsc/compile",
            json={"input": test_prd, "output_types": ["json"]},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        
        result = data["data"]
        assert "business_system" in result
        assert "pipeline" in result
        assert result.get("parallel") is True

    def test_compile_missing_input(self, test_client):
        """测试缺少输入的情况"""
        response = test_client.post(
            "/bsc/compile",
            json={"input": "", "output_types": ["json"]},
        )
        
        assert response.status_code == 422

    def test_compile_too_short_input(self, test_client):
        """测试输入过短的情况"""
        response = test_client.post(
            "/bsc/compile",
            json={"input": "test", "output_types": ["json"]},
        )
        
        assert response.status_code == 422

    def test_stage_execution(self, test_client):
        """测试单独执行阶段"""
        test_prd = """# 测试PRD
业务目标：测试
"""
        
        response = test_client.post(
            "/bsc/stage",
            json={"input": test_prd, "stage_key": "business_understanding"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    def test_list_stages(self, test_client):
        """测试获取阶段列表"""
        response = test_client.get("/bsc/stages")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stages" in data["data"]

    def test_export_json(self, test_client):
        """测试JSON导出"""
        test_prd = """# 测试PRD
业务目标：测试导出功能
"""
        
        response = test_client.post(
            "/bsc/export",
            json={"input": test_prd, "output_types": ["json"]},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "exports" in data["data"]
        assert "json" in data["data"]["exports"]

    def test_metrics_endpoint(self, test_client):
        """测试指标接口"""
        response = test_client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "uptime_sec" in data
        assert "total_requests" in data

    def test_metrics_prometheus(self, test_client):
        """测试Prometheus格式指标接口"""
        response = test_client.get("/metrics/prometheus")
        assert response.status_code == 200
        assert "bsc_uptime_seconds" in response.text


class TestPipelineStages:
    """Pipeline阶段集成测试"""

    def test_business_understanding_stage(self, test_client):
        """测试业务理解阶段"""
        test_prd = """# 金融风控系统PRD

## 业务目标
- 建立实时风控体系
- 降低欺诈损失

## 核心功能
- 交易监控
- 风险评估
"""
        
        response = test_client.post(
            "/bsc/stage",
            json={"input": test_prd, "stage_key": "business_understanding"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        stage_data = data["data"]
        result = stage_data.get("data", {}).get("result", {})
        assert "business_domain" in result

    def test_sop_stage(self, test_client):
        """测试SOP阶段"""
        test_prd = """# 客服工单系统PRD

## 业务目标
- 提升客户满意度
- 优化工单处理效率

## 核心功能
- 工单创建
- 工单分配
- 工单处理
"""
        
        response = test_client.post(
            "/bsc/stage",
            json={"input": test_prd, "stage_key": "sop"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_risk_stage(self, test_client):
        """测试风险分析阶段"""
        test_prd = """# 数据安全系统PRD

## 业务目标
- 确保数据安全合规
- 保护用户隐私

## 核心功能
- 数据加密
- 访问控制
"""
        
        response = test_client.post(
            "/bsc/stage",
            json={"input": test_prd, "stage_key": "risk"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestCompileWorkflow:
    """完整编译工作流测试"""

    def test_full_compile_workflow(self, test_client):
        """测试完整编译工作流"""
        test_prd = """# 电商订单管理系统PRD

## 1. 业务目标
- 提升订单处理效率
- 降低库存积压风险
- 优化客户体验

## 2. 核心功能模块
- 订单创建与管理
- 库存管理
- 物流跟踪
- 退货退款

## 3. 性能要求
- 订单处理响应时间 < 1秒
- 支持日均10万+订单量

## 4. 安全要求
- 支付信息加密存储
- 权限分级管理
"""
        
        response = test_client.post(
            "/bsc/compile",
            json={"input": test_prd, "output_types": ["json", "html"]},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        result = data["data"]
        
        assert "business_system" in result
        bs = result["business_system"]
        
        assert bs.get("business_domain") is not None
        assert isinstance(bs.get("objectives"), list)
        assert isinstance(bs.get("workflow"), list)
        assert isinstance(bs.get("roles"), list)
        assert isinstance(bs.get("kpi"), list) or isinstance(bs.get("metrics"), list)
        
        assert "pipeline" in result
        pipeline = result["pipeline"]
        assert isinstance(pipeline.get("stages"), list)
        assert pipeline.get("total_ms") > 0
        
        assert "composed" in result
        assert "workspace" in result
        
        workspace = result["workspace"]
        assert "dashboard" in workspace
        assert "report" in workspace
        assert "ppt_blueprint" in workspace