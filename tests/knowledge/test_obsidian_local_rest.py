from types import SimpleNamespace

import httpx

from app.knowledge.obsidian_local_rest import ObsidianLocalRestConfiguration, ObsidianLocalRestProbe


def _probe(configuration: ObsidianLocalRestConfiguration, handler):
    return ObsidianLocalRestProbe(configuration, transport=httpx.MockTransport(handler))


def test_unconfigured_local_rest_does_not_make_a_network_request():
    def fail(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("unconfigured Local REST must not request a service")

    result = _probe(ObsidianLocalRestConfiguration(), fail).probe()

    assert result == {
        "state": "unconfigured",
        "detail_code": "disabled",
        "transport": "not_configured",
        "plugin_id": "obsidian-local-rest-api",
        "plugin_version": "",
    }


def test_loopback_manifest_probe_is_authenticated_without_exposing_runtime_token():
    token = "local-rest-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == httpx.URL("https://127.0.0.1:27124/")
        assert request.headers["authorization"] == f"Bearer {token}"
        return httpx.Response(200, json={
            "status": "OK",
            "authenticated": True,
            "manifest": {"id": "obsidian-local-rest-api", "version": "5.0.2"},
        })

    result = _probe(ObsidianLocalRestConfiguration(True, "https://127.0.0.1:27124", token), handler).probe()

    assert result == {
        "state": "connected",
        "detail_code": "authenticated_manifest_verified",
        "transport": "loopback_tls",
        "plugin_id": "obsidian-local-rest-api",
        "plugin_version": "5.0.2",
    }
    assert token not in str(result)


def test_probe_rejects_nonlocal_or_non_tls_endpoints_before_requesting_them():
    def fail(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid endpoint must not be requested")

    result = _probe(ObsidianLocalRestConfiguration(True, "http://example.test", "secret"), fail).probe()

    assert result["state"] == "configuration_invalid"
    assert result["detail_code"] == "endpoint_not_local_tls"


def test_probe_maps_authentication_rejection_without_returning_service_body():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="token value must never be returned")

    result = _probe(ObsidianLocalRestConfiguration(True, "https://localhost:27124", "secret"), handler).probe()

    assert result["state"] == "authentication_failed"
    assert result["detail_code"] == "authorization_rejected"
    assert "token value" not in str(result)


def test_configuration_reads_runtime_only_settings():
    settings = SimpleNamespace(
        OBSIDIAN_LOCAL_REST_ENABLED=True,
        OBSIDIAN_LOCAL_REST_URL="https://host.docker.internal:27124",
        OBSIDIAN_LOCAL_REST_API_KEY="runtime-only",
        OBSIDIAN_LOCAL_REST_TIMEOUT_SECONDS=4.5,
        OBSIDIAN_LOCAL_REST_ALLOW_INSECURE_TLS=True,
    )

    configuration = ObsidianLocalRestConfiguration.from_settings(settings)

    assert configuration.enabled is True
    assert configuration.base_url == "https://host.docker.internal:27124"
    assert configuration.timeout_seconds == 4.5
    assert configuration.allow_insecure_tls is True
