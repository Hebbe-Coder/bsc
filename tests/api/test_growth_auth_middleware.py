import hashlib

import pytest
from fastapi.testclient import TestClient

import app.middleware.auth as auth_middleware
from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.schema import ensure_schema
from app.main import app
from app.repositories.knowledge_repository import KnowledgeRepository


@pytest.fixture
def middleware_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "API_KEY", "growth-global-admin")
    monkeypatch.setattr(settings, "API_KEY_READER", "growth-global-reader")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    repo = GrowthRepository(db_path=str(tmp_path / "growth-auth.db"))
    auth_repo = KnowledgeRepository(db_path=str(tmp_path / "growth-keys.db"))
    ensure_schema(auth_repo)
    auth_repo.create_project("project-a", "Project A")
    auth_repo.create_project_key(
        hashlib.sha256(b"project-a-reader").hexdigest(),
        "project-a",
        "project_reader",
        "reader",
    )
    auth_repo.create_project_key(
        hashlib.sha256(b"project-a-admin").hexdigest(),
        "project-a",
        "project_admin",
        "admin",
    )
    original_resolver = auth_middleware.resolve_knowledge_auth
    monkeypatch.setattr(
        auth_middleware,
        "resolve_knowledge_auth",
        lambda api_key: original_resolver(api_key, repo=auth_repo),
    )
    app.dependency_overrides[get_growth_repository] = lambda: repo
    try:
        yield TestClient(app), repo
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        auth_repo.close()
        repo.close()


def _auth(key):
    return {"Authorization": f"Bearer {key}"}


def test_global_reader_reaches_growth_reads_but_not_mutations(middleware_client):
    client, _repo = middleware_client
    read = client.get(
        "/knowledge/growth/project-a/profile",
        headers=_auth("growth-global-reader"),
    )
    write = client.patch(
        "/knowledge/growth/project-a/profile",
        headers=_auth("growth-global-reader"),
        json={"expected_revision": 0, "user_role": "forbidden"},
    )

    assert read.status_code == 200, read.text
    assert read.json()["data"]["access"]["role"] == "reader"
    assert write.status_code == 403
    assert write.json()["message"]["code"] == "growth_permission_denied"


def test_global_admin_reaches_growth_mutation(middleware_client):
    client, _repo = middleware_client
    response = client.patch(
        "/knowledge/growth/project-a/profile",
        headers=_auth("growth-global-admin"),
        json={"expected_revision": 0, "user_role": "operator"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["profile"]["user_role"] == "operator"


@pytest.mark.parametrize(
    ("key", "method", "expected"),
    [("project-a-reader", "GET", 200), ("project-a-admin", "PATCH", 200)],
)
def test_project_keys_reach_own_project(middleware_client, key, method, expected):
    client, _repo = middleware_client
    if method == "GET":
        response = client.get(
            "/knowledge/growth/project-a/profile",
            headers=_auth(key),
        )
    else:
        response = client.patch(
            "/knowledge/growth/project-a/profile",
            headers=_auth(key),
            json={"expected_revision": 0, "user_role": "project-operator"},
        )
    assert response.status_code == expected, response.text


@pytest.mark.parametrize("key", ["project-a-reader", "project-a-admin"])
def test_project_keys_cannot_cross_project(middleware_client, key):
    client, _repo = middleware_client
    response = client.get(
        "/knowledge/growth/project-b/profile",
        headers=_auth(key),
    )
    assert response.status_code == 403
    assert response.json()["message"]["code"] == "growth_project_scope_denied"
