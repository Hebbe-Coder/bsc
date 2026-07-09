def test_list_documents_empty(client):
    resp = client.get("/knowledge/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 0


def test_documents_endpoint_structure(client):
    resp = client.get("/knowledge/documents")
    body = resp.json()
    assert "documents" in body["data"]
    assert "total" in body["data"]
    assert isinstance(body["data"]["documents"], list)
