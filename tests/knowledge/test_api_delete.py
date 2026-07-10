def test_delete_success(client):
    r = client.post("/knowledge/ingest",
                    data={"text": "内容安全平台过滤违规信息。", "title": "A", "project_id": "p1"}).json()
    doc_id = r["data"]["docs"][0]["doc_id"]
    resp = client.delete(f"/knowledge/documents/{doc_id}")
    assert resp.json()["code"] == 200
    assert client.get("/knowledge/documents").json()["data"]["total"] == 0


def test_delete_missing(client):
    resp = client.delete("/knowledge/documents/nope")
    assert resp.json()["code"] == 404
