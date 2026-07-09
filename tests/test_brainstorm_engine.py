"""
Brainstorm Engine测试用例

测试覆盖：
- BrainstormEngine类：创意生成、链式头脑风暴、思维导图、问题分析
- 创意评估和导出功能
- API接口测试
- 异常处理和边界情况
"""
import pytest


class TestBrainstormEngine:
    """头脑风暴引擎测试"""

    @pytest.fixture
    def engine(self, mock_llm_service):
        """创建BrainstormEngine实例"""
        from app.engines.brainstorm_engine import BrainstormEngine
        return BrainstormEngine(llm_service=mock_llm_service)

    def test_generate_ideas(self, engine):
        """测试创意生成"""
        result = engine.generate_ideas(
            business_domain="金融服务",
            problem="如何提升客户满意度",
            context="当前客户满意度为85%，目标95%",
            num_ideas=5,
            mode="divergent",
        )
        
        assert "task_id" in result
        assert "generated_at" in result
        assert result["business_domain"] == "金融服务"
        assert result["problem"] == "如何提升客户满意度"
        assert result["mode"] == "divergent"
        assert result["total_ideas"] > 0
        assert isinstance(result["ideas"], list)
        assert isinstance(result["categories"], list)
        assert isinstance(result["impact_distribution"], dict)
        assert isinstance(result["feasibility_distribution"], dict)

    def test_generate_ideas_with_context(self, engine):
        """测试带背景信息的创意生成"""
        result = engine.generate_ideas(
            business_domain="电商",
            problem="如何降低退货率",
            context="当前退货率为15%，主要原因是尺寸不符和质量问题",
            num_ideas=8,
        )
        
        assert result["total_ideas"] > 0
        for idea in result["ideas"]:
            assert "id" in idea
            assert "title" in idea
            assert "description" in idea
            assert "category" in idea
            assert "score" in idea

    def test_chain_brainstorm(self, engine):
        """测试链式头脑风暴"""
        result = engine.chain_brainstorm(
            business_domain="教育",
            problem="如何提升在线课程完成率",
            rounds=2,
            num_ideas_per_round=3,
        )
        
        assert "task_id" in result
        assert result["rounds"] == 2
        assert len(result["round_results"]) == 2
        assert result["total_ideas"] > 0
        assert result["final_summary"] is not None

    def test_converge_ideas(self, engine):
        """测试收敛创意"""
        ideas = [
            {"idea": "方案A", "category": "技术创新", "impact": "高", "feasibility": "高"},
            {"idea": "方案B", "category": "流程优化", "impact": "中", "feasibility": "高"},
            {"idea": "方案C", "category": "商业模式", "impact": "高", "feasibility": "中"},
        ]
        
        result = engine.converge_ideas(
            business_domain="科技",
            ideas=ideas,
            top_n=2,
        )
        
        assert "top_ideas" in result
        assert isinstance(result["top_ideas"], list)
        assert len(result["top_ideas"]) <= 2

    def test_generate_mindmap(self, engine):
        """测试生成思维导图"""
        result = engine.generate_mindmap(
            topic="数字化转型战略",
            business_domain="金融",
        )
        
        assert "topic" in result
        assert result["topic"] == "数字化转型战略"
        assert "mindmap" in result
        assert "center" in result["mindmap"]
        assert "branches" in result["mindmap"]
        assert isinstance(result["mindmap"]["branches"], list)

    def test_analyze_problem(self, engine):
        """测试问题分析"""
        result = engine.analyze_problem(
            problem="客户投诉率持续上升",
            business_domain="零售",
        )
        
        assert "problem" in result
        assert "analysis" in result
        assert isinstance(result["analysis"], dict)
        assert isinstance(result["root_causes"], list)
        assert isinstance(result["solution_directions"], list)

    def test_evaluate_ideas(self, engine):
        """测试创意评估"""
        ideas = [
            {"idea": "方案A", "category": "技术创新", "impact": "高", "feasibility": "高", "keywords": ["AI", "自动化", "效率"]},
            {"idea": "方案B", "category": "流程优化", "impact": "中", "feasibility": "中", "keywords": ["流程", "简化"]},
            {"idea": "方案C", "category": "用户体验", "impact": "低", "feasibility": "高", "keywords": ["UI"]},
        ]
        
        evaluated = engine.evaluate_ideas(ideas)
        
        assert len(evaluated) == 3
        for idea in evaluated:
            assert "scores" in idea
            assert "total_score" in idea
            assert "rank" in idea
            assert idea["rank"] > 0
        
        assert evaluated[0]["rank"] == 1
        assert evaluated[1]["rank"] == 2
        assert evaluated[2]["rank"] == 3

    def test_evaluate_custom_criteria(self, engine):
        """测试自定义评估标准"""
        ideas = [
            {"idea": "方案A", "impact": "高", "feasibility": "高"},
        ]
        
        evaluated = engine.evaluate_ideas(
            ideas,
            criteria=["创新性", "可行性", "影响力"],
        )
        
        assert len(evaluated) == 1
        assert "scores" in evaluated[0]
        assert "创新性" in evaluated[0]["scores"]
        assert "可行性" in evaluated[0]["scores"]
        assert "影响力" in evaluated[0]["scores"]

    def test_export_to_markdown(self, engine):
        """测试Markdown导出"""
        result = engine.generate_ideas(
            business_domain="测试",
            problem="测试问题",
            num_ideas=3,
        )
        
        md_content = engine.export_to_markdown(result)
        
        assert isinstance(md_content, str)
        assert len(md_content) > 0
        assert "#" in md_content
        assert "测试问题" in md_content
        assert "测试" in md_content

    def test_export_to_json(self, engine):
        """测试JSON导出"""
        result = engine.generate_ideas(
            business_domain="测试",
            problem="测试问题",
            num_ideas=3,
        )
        
        json_content = engine.export_to_json(result)
        
        assert isinstance(json_content, str)
        assert len(json_content) > 0
        
        import json
        parsed = json.loads(json_content)
        assert "task_id" in parsed
        assert "ideas" in parsed


class TestBrainstormEngineEdgeCases:
    """头脑风暴引擎边界情况测试"""

    @pytest.fixture
    def engine(self, mock_llm_service):
        from app.engines.brainstorm_engine import BrainstormEngine
        return BrainstormEngine(llm_service=mock_llm_service)

    def test_empty_problem(self, engine):
        """测试空问题描述"""
        result = engine.generate_ideas(
            business_domain="测试",
            problem="",
            num_ideas=3,
        )
        
        assert "ideas" in result
        assert isinstance(result["ideas"], list)

    def test_empty_domain(self, engine):
        """测试空业务领域"""
        result = engine.generate_ideas(
            business_domain="",
            problem="测试问题",
            num_ideas=3,
        )
        
        assert "ideas" in result
        assert result["business_domain"] == ""

    def test_zero_rounds_chain(self, engine):
        """测试链式头脑风暴零轮数"""
        result = engine.chain_brainstorm(
            business_domain="测试",
            problem="测试问题",
            rounds=0,
        )
        
        assert result["rounds"] == 0
        assert len(result["round_results"]) == 0
        assert result["total_ideas"] == 0

    def test_empty_ideas_for_converge(self, engine):
        """测试空创意列表收敛"""
        result = engine.converge_ideas(
            business_domain="测试",
            ideas=[],
            top_n=5,
        )
        
        assert "top_ideas" in result
        assert isinstance(result["top_ideas"], list)

    def test_empty_mindmap(self, engine):
        """测试空主题思维导图"""
        result = engine.generate_mindmap(topic="")
        
        assert "mindmap" in result
        assert result["mindmap"]["center"] == ""

    def test_empty_ideas_for_evaluate(self, engine):
        """测试空创意列表评估"""
        evaluated = engine.evaluate_ideas([])
        
        assert evaluated == []

    def test_export_empty_result(self, engine):
        """测试导出空结果"""
        empty_result = {
            "task_id": "test",
            "generated_at": "2024-01-01",
            "business_domain": "",
            "problem": "",
            "ideas": [],
        }
        
        md_content = engine.export_to_markdown(empty_result)
        assert isinstance(md_content, str)
        
        json_content = engine.export_to_json(empty_result)
        assert isinstance(json_content, str)


class TestBrainstormAPI:
    """头脑风暴API测试"""

    @pytest.fixture
    def client(self):
        """创建FastAPI测试客户端"""
        from fastapi.testclient import TestClient
        from app.main import app
        
        return TestClient(app)

    def test_generate_ideas_endpoint(self, client):
        """测试生成创意接口"""
        response = client.post(
            "/brainstorm/generate",
            json={
                "business_domain": "金融",
                "problem": "如何提升客户体验",
                "num_ideas": 5,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "data" in data
        assert "ideas" in data["data"]

    def test_chain_brainstorm_endpoint(self, client):
        """测试链式头脑风暴接口"""
        response = client.post(
            "/brainstorm/chain",
            json={
                "business_domain": "科技",
                "problem": "创新产品开发",
                "rounds": 2,
                "num_ideas_per_round": 3,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "round_results" in data["data"]

    def test_converge_ideas_endpoint(self, client):
        """测试收敛创意接口"""
        response = client.post(
            "/brainstorm/converge",
            json={
                "ideas": [
                    {"idea": "方案A", "category": "技术", "impact": "高", "feasibility": "高"},
                    {"idea": "方案B", "category": "流程", "impact": "中", "feasibility": "中"},
                ],
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "top_ideas" in data["data"]

    def test_converge_empty_ideas(self, client):
        """测试空创意列表收敛"""
        response = client.post(
            "/brainstorm/converge",
            json={"ideas": []},
        )
        
        assert response.status_code == 400

    def test_mindmap_endpoint(self, client):
        """测试思维导图接口"""
        response = client.post(
            "/brainstorm/mindmap",
            json={"topic": "商业战略", "business_domain": "金融"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "mindmap" in data["data"]

    def test_analyze_problem_endpoint(self, client):
        """测试问题分析接口"""
        response = client.post(
            "/brainstorm/analyze",
            json={"problem": "销售下降", "business_domain": "零售"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "analysis" in data["data"]

    def test_evaluate_ideas_endpoint(self, client):
        """测试评估创意接口"""
        response = client.post(
            "/brainstorm/evaluate",
            json={
                "ideas": [
                    {"idea": "方案A", "impact": "高", "feasibility": "高"},
                    {"idea": "方案B", "impact": "低", "feasibility": "高"},
                ],
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2

    def test_evaluate_empty_ideas(self, client):
        """测试空创意列表评估"""
        response = client.post(
            "/brainstorm/evaluate",
            json={"ideas": []},
        )
        
        assert response.status_code == 400

    def test_export_markdown_endpoint(self, client):
        """测试导出Markdown接口"""
        response = client.post(
            "/brainstorm/export",
            json={
                "result": {
                    "problem": "测试问题",
                    "business_domain": "测试",
                    "ideas": [{"idea": "测试创意", "category": "测试"}],
                },
                "format": "markdown",
            },
        )
        
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]

    def test_export_json_endpoint(self, client):
        """测试导出JSON接口"""
        response = client.post(
            "/brainstorm/export",
            json={
                "result": {
                    "problem": "测试问题",
                    "business_domain": "测试",
                    "ideas": [{"idea": "测试创意", "category": "测试"}],
                },
                "format": "json",
            },
        )
        
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_invalid_export_format(self, client):
        """测试无效导出格式"""
        response = client.post(
            "/brainstorm/export",
            json={
                "result": {"ideas": []},
                "format": "pdf",
            },
        )
        
        assert response.status_code == 422