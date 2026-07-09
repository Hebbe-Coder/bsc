def test_ingest_partial_failure(client):
    # 一个成功 + 一个不支持格式 → partial(207)
    resp = client.post(
        "/knowledge/ingest",
        files=[
            ("files", ("ok.txt", "内容安全平台。", "text/plain")),
            ("files", ("bad.xyz", "x", "application/octet-stream")),
        ])
    body = resp.json()
    assert body["code"] == 207
    assert body["data"]["count"] == 1
    assert client.get("/knowledge/documents").json()["data"]["total"] == 1


def test_ingest_project_filter_end_to_end(client):
    client.post("/knowledge/ingest",
                data={"text": "内容安全。", "project_id": "p1", "title": "A"})
    client.post("/knowledge/ingest",
                data={"text": "咖啡。", "project_id": "p2", "title": "B"})
    resp = client.get("/knowledge/documents", params={"project_id": "p1"})
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["documents"][0]["title"] == "A"


def test_retrieve_empty_corpus(client):
    resp = client.post("/knowledge/retrieve", json={"query": "任意"})
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["results"] == []


def test_ingest_oversized_text_skipped_not_crash(client):
    # 巨大文本仍应入库（KnowledgeService 内部有定界），不崩
    big = "内容安全。" * 5000
    resp = client.post("/knowledge/ingest", data={"text": big, "title": "BIG"})
    assert resp.json()["code"] == 200
    assert client.get("/knowledge/documents").json()["data"]["total"] == 1
