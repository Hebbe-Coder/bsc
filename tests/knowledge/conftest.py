import pytest, tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.knowledge.service import KnowledgeService
from app.api.knowledge_api import get_knowledge_service


@pytest.fixture
def client():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    tmp = f.name
    app.dependency_overrides[get_knowledge_service] = (
        lambda: KnowledgeService(db_path=tmp))
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
