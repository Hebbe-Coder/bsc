import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.service import KnowledgeService
from app.knowledge.tool import RetrieveKnowledgeTool

def _tmp_tool():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return RetrieveKnowledgeTool(service=KnowledgeService(db_path=f.name))

def test_retrieve_tool_format():
    tool = _tmp_tool()
    tool._service.ingest("内容安全平台用于过滤违规信息。", project_id="p1", title="文档A")
    out = tool._run("内容安全")
    assert "[知识 1]" in out
    assert "出处：文档A" in out
    assert "内容安全平台" in out

def test_retrieve_tool_empty():
    tool = _tmp_tool()
    out = tool._run("任何查询")
    assert "未检索到相关知识" in out
