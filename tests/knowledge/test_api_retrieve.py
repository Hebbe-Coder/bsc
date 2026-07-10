def test_retrieve_hit(client):
    client.post("/knowledge/ingest",
                data={"text": "内容安全平台用于过滤违规信息。审核效率需要提升。",
                      "title": "A", "project_id": "p1"})
    resp = client.post("/knowledge/retrieve", json={"query": "内容安全 审核", "project_id": "p1"})
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["results"]
    assert "内容安全" in body["data"]["results"][0]["content"]
    assert body["data"]["results"][0]["doc_title"] == "A"


def test_retrieve_empty_query(client):
    resp = client.post("/knowledge/retrieve", json={"query": ""})
    assert resp.json()["code"] == 400
