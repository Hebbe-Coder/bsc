import json

import pytest

from app.knowledge.horizon_client import HorizonClient, HorizonClientError


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _limit):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _RedirectResponse(_Response):
    def __init__(self, payload: bytes, final_url: str):
        super().__init__(payload)
        self.final_url = final_url

    def geturl(self):
        return self.final_url


def test_horizon_client_reads_filtered_items_with_injected_transport():
    received = []

    def opener(request, timeout):
        received.append((request.full_url, request.headers, timeout))
        return _Response(json.dumps({"data": {"items": [{"id": "item-1"}]}}).encode("utf-8"))

    client = HorizonClient(base_url="https://horizon.example", api_key="token", allow_private_network=True, opener=opener)
    result = client.fetch_stage(run_id="run-1", stage="filtered")

    assert result.items == [{"id": "item-1"}]
    assert received[0][0] == "https://horizon.example/api/runs/run-1/stages/filtered"
    assert received[0][2] == 20


def test_horizon_client_rejects_unbounded_or_malformed_stage_data():
    client = HorizonClient(base_url="https://horizon.example", allow_private_network=True, opener=lambda *_args, **_kwargs: _Response(b"{}"))

    with pytest.raises(HorizonClientError, match="items array"):
        client.fetch_stage(run_id="run-1", stage="filtered")
    with pytest.raises(HorizonClientError, match="filtered or enriched"):
        client.fetch_stage(run_id="run-1", stage="raw")


def test_horizon_client_rejects_a_protocol_relative_stage_escape():
    client = HorizonClient(
        base_url="https://horizon.example",
        stage_url_template="//attacker.example/{run_id}/{stage}",
        allow_private_network=True,
        opener=lambda *_args, **_kwargs: _Response(b"{}"),
    )

    with pytest.raises(HorizonClientError, match="escaped"):
        client.fetch_stage(run_id="run-1", stage="filtered")


def test_horizon_client_rejects_a_redirect_to_another_origin():
    client = HorizonClient(
        base_url="https://horizon.example",
        allow_private_network=True,
        opener=lambda *_args, **_kwargs: _RedirectResponse(
            b'{"items": []}', "https://attacker.example/redirect"
        ),
    )

    with pytest.raises(HorizonClientError, match="redirect"):
        client.fetch_stage(run_id="run-1", stage="filtered")
