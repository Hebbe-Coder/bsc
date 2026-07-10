def test_ingest_file(client):
    resp = client.post(
        "/knowledge/ingest",
        files={"files": ("doc.txt", "内容安全平台过滤违规信息。审核效率提升。", "text/plain")},
        data={"project_id": "p1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["count"] == 1
    lst = client.get("/knowledge/documents").json()
    assert lst["data"]["total"] == 1


def test_ingest_text(client):
    resp = client.post("/knowledge/ingest", data={"text": "咖啡烘焙风味分析流程。", "project_id": "p1"})
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["count"] == 1


def test_ingest_multi_file(client):
    resp = client.post(
        "/knowledge/ingest",
        files=[
            ("files", ("a.txt", "内容安全。", "text/plain")),
            ("files", ("b.txt", "咖啡烘焙。", "text/plain")),
        ],
        data={"project_id": "p1"})
    assert resp.json()["data"]["count"] == 2


def test_ingest_unsupported_format(client):
    resp = client.post(
        "/knowledge/ingest",
        files={"files": ("x.xyz", "hello", "application/octet-stream")})
    # single file fails to parse and no successful unit -> 400
    assert resp.json()["code"] == 400


def test_ingest_empty(client):
    resp = client.post("/knowledge/ingest", data={})
    assert resp.json()["code"] == 400
