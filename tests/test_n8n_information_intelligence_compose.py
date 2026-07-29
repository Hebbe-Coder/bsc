import json
from pathlib import Path

import yaml


def test_n8n_is_opt_in_loopback_only_and_uses_a_durable_volume():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    n8n = compose["services"]["n8n"]
    assert n8n["profiles"] == ["n8n"]
    assert "127.0.0.1:${N8N_PORT:-5678}:5678" in n8n["ports"]
    assert "n8n-data:/home/node/.n8n" in n8n["volumes"]
    assert "./n8n/workflows:/opt/bsc-workflows:ro" in n8n["volumes"]
    assert "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY:-}" in n8n["environment"]
    assert "N8N_RUNNERS_ENABLED=true" in n8n["environment"]
    assert "EXECUTIONS_DATA_SAVE_ON_SUCCESS=none" in n8n["environment"]
    assert "EXECUTIONS_DATA_SAVE_ON_ERROR=none" in n8n["environment"]
    assert "EXECUTIONS_DATA_SAVE_ON_PROGRESS=false" in n8n["environment"]
    assert "EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=false" in n8n["environment"]
    assert any(item.startswith("BSC_INFORMATION_SOURCE_MANIFEST_URL=") for item in n8n["environment"])
    assert n8n["entrypoint"] == ["/bin/sh", "-c"]
    assert len(n8n["command"]) == 1
    assert "N8N_ENCRYPTION_KEY must be set" in n8n["command"][0]
    assert n8n["healthcheck"]["test"] == ["CMD-SHELL", "wget -qO- http://127.0.0.1:5678/healthz >/dev/null"]
    assert "n8n-data" in compose["volumes"]


def test_governed_rss_workflow_is_disabled_and_has_no_imported_credentials_or_direct_feishu_delivery():
    workflow_text = Path("n8n/workflows/bsc-governed-rss-intelligence.json").read_text(encoding="utf-8")
    workflow = json.loads(workflow_text)
    nodes = {node["name"]: node for node in workflow["nodes"]}

    assert workflow["active"] is False
    assert workflow["settings"]["saveExecutionProgress"] is False
    assert workflow["settings"]["saveManualExecutions"] is False
    assert workflow["settings"]["saveExecutionDataSuccess"] == "none"
    assert workflow["settings"]["saveExecutionDataError"] == "none"
    assert "Submit to BSC and require receipt" in nodes
    assert "Validate BSC receipt before notification" in nodes
    assert "Load BSC source manifest" in nodes
    assert "Expand enabled BSC sources" in nodes
    assert "Read registered RSS or YouTube Channel feed" in nodes
    assert "credentials" not in workflow_text
    assert "feishu" not in workflow_text.lower()
    assert "reddit" not in workflow_text.lower()
    assert "tiktok" not in workflow_text.lower()
    assert "N8N_RSS_FEED_URL" not in workflow_text
    assert "N8N_BSC_PROJECT_ID" not in workflow_text
    assert "N8N_BSC_RSS_REGISTRY_ID" not in workflow_text

    # The all-items mode must retain each feed item's linked registry context,
    # discard stale entries, and emit one signed batch for every fresh item.
    for node_name in (
        "Normalize evidence or lead only",
        "Build BSC SignalBatch v1",
        "Validate BSC receipt before notification",
    ):
        assert nodes[node_name]["parameters"]["mode"] == "runOnceForAllItems"
    normalizer = nodes["Normalize evidence or lead only"]["parameters"]["jsCode"]
    assert "freshness_hours" in normalizer
    assert "$input.all()" in normalizer
    assert "itemMatching(index)" in normalizer

    manifest_request = nodes["Load BSC source manifest"]["parameters"]
    manifest_headers = {item["name"]: item["value"] for item in manifest_request["headerParameters"]["parameters"]}
    assert manifest_request["method"] == "GET"
    assert manifest_request["url"] == "={{ $env.BSC_INFORMATION_SOURCE_MANIFEST_URL }}"
    assert manifest_headers["Authorization"] == "=Bearer {{ $env.BSC_PROJECT_INGRESS_KEY }}"

    signature = nodes["Sign exact SignalBatch body"]["parameters"]
    assert signature["action"] == "hmac"
    assert signature["type"] == "SHA256"
    assert signature["binaryData"] is False
    assert signature["value"] == "={{ $json.body }}"
    assert signature["dataPropertyName"] == "signature"
    assert signature["encoding"] == "hex"

    request = nodes["Submit to BSC and require receipt"]["parameters"]
    headers = {item["name"]: item["value"] for item in request["headerParameters"]["parameters"]}
    assert request["contentType"] == "raw"
    assert request["rawContentType"] == "application/json"
    assert request["body"] == "={{ $json.body }}"
    assert headers["X-BSC-Signal-Signature"] == "={{ $json.signature }}"
