import json
import socket
from pathlib import Path
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
        "configuration_source": "not_configured",
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
        "configuration_source": "not_configured",
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
        OBSIDIAN_VAULT_ROOT="",
    )

    configuration = ObsidianLocalRestConfiguration.from_settings(settings)

    assert configuration.enabled is True
    assert configuration.base_url == "https://host.docker.internal:27124"
    assert configuration.timeout_seconds == 4.5
    assert configuration.allow_insecure_tls is True
    assert configuration.configuration_source == "runtime_env"


def test_enabled_probe_recovers_only_local_rest_transport_settings_from_the_mounted_vault(tmp_path):
    settings_path = tmp_path / ".obsidian" / "plugins" / "obsidian-local-rest-api" / "data.json"
    settings_path.parent.mkdir(parents=True)
    token = "plugin-only-secret"
    settings_path.write_text(json.dumps({
        "apiKey": token,
        "port": 27124,
        "enableSecureServer": True,
    }), encoding="utf-8")
    (tmp_path / "notes.md").write_text("This note must never be read by the Local REST probe.", encoding="utf-8")
    settings = SimpleNamespace(
        OBSIDIAN_LOCAL_REST_ENABLED=True,
        OBSIDIAN_LOCAL_REST_URL="",
        OBSIDIAN_LOCAL_REST_API_KEY="",
        OBSIDIAN_LOCAL_REST_TIMEOUT_SECONDS=4.5,
        OBSIDIAN_LOCAL_REST_ALLOW_INSECURE_TLS=False,
        OBSIDIAN_VAULT_ROOT=str(tmp_path),
    )
    configuration = ObsidianLocalRestConfiguration.from_settings(settings)

    assert configuration.configuration_source == "plugin_config"
    assert configuration.base_url == "https://host.docker.internal:27124"
    assert configuration.allow_insecure_tls is True
    assert token not in repr(configuration)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://host.docker.internal:27124/")
        assert request.headers["authorization"] == f"Bearer {token}"
        return httpx.Response(200, json={
            "authenticated": True,
            "manifest": {"id": "obsidian-local-rest-api", "version": "5.0.2"},
        })

    result = _probe(configuration, handler).probe()

    assert result["state"] == "connected"
    assert result["configuration_source"] == "plugin_config"
    assert token not in str(result)


def test_enabled_plugin_fallback_rejects_an_insecure_or_incomplete_plugin_configuration_without_requesting_it(tmp_path):
    settings_path = tmp_path / ".obsidian" / "plugins" / "obsidian-local-rest-api" / "data.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"apiKey": "secret", "port": 27124, "enableSecureServer": False}), encoding="utf-8")
    settings = SimpleNamespace(
        OBSIDIAN_LOCAL_REST_ENABLED=True,
        OBSIDIAN_LOCAL_REST_URL="",
        OBSIDIAN_LOCAL_REST_API_KEY="",
        OBSIDIAN_LOCAL_REST_TIMEOUT_SECONDS=3,
        OBSIDIAN_LOCAL_REST_ALLOW_INSECURE_TLS=False,
        OBSIDIAN_VAULT_ROOT=str(tmp_path),
    )
    configuration = ObsidianLocalRestConfiguration.from_settings(settings)

    result = _probe(configuration, lambda _request: (_ for _ in ()).throw(AssertionError("invalid plugin config must not request a service"))).probe()

    assert result["state"] == "configuration_invalid"
    assert result["detail_code"] == "plugin_secure_server_disabled"
    assert result["configuration_source"] == "plugin_config"


def test_plugin_configuration_fallback_rejects_symlinked_source_without_reading_writing_or_network(tmp_path, monkeypatch):
    """The settings reader may inspect its own JSON, never a linked Vault note."""
    source = tmp_path / "01_Sources" / "private.md"
    source.parent.mkdir(parents=True)
    source.write_text("PRIVATE SOURCE BODY", encoding="utf-8")
    settings_path = tmp_path / ".obsidian" / "plugins" / "obsidian-local-rest-api" / "data.json"
    settings_path.parent.mkdir(parents=True)

    original_read_text = Path.read_text
    original_write_text = Path.write_text
    original_resolve = Path.resolve
    original_is_symlink = Path.is_symlink
    resolved_source = original_resolve(source)

    def redirected_resolve(path, *args, **kwargs):
        if path == settings_path:
            return resolved_source
        return original_resolve(path, *args, **kwargs)

    def simulated_symlink(path):
        return path == settings_path or original_is_symlink(path)

    def guarded_read_text(path, *args, **kwargs):
        if original_resolve(path) == resolved_source:
            raise AssertionError("Local REST configuration must not read a source body")
        return original_read_text(path, *args, **kwargs)

    def guarded_write_text(path, *args, **kwargs):
        if original_resolve(path) == resolved_source:
            raise AssertionError("Local REST configuration must not write a source file")
        return original_write_text(path, *args, **kwargs)

    class ForbiddenClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("Local REST configuration must stay offline")

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "resolve", redirected_resolve)
    monkeypatch.setattr(Path, "is_symlink", simulated_symlink)
    monkeypatch.setattr(httpx, "Client", ForbiddenClient)
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Local REST configuration must stay offline")
    ))
    settings = SimpleNamespace(
        OBSIDIAN_LOCAL_REST_ENABLED=True,
        OBSIDIAN_LOCAL_REST_URL="",
        OBSIDIAN_LOCAL_REST_API_KEY="",
        OBSIDIAN_LOCAL_REST_TIMEOUT_SECONDS=3,
        OBSIDIAN_LOCAL_REST_ALLOW_INSECURE_TLS=False,
        OBSIDIAN_VAULT_ROOT=str(tmp_path),
    )

    configuration = ObsidianLocalRestConfiguration.from_settings(settings)

    assert configuration.configuration_source == "plugin_config"
    assert configuration.configuration_error == "plugin_settings_unsafe_path"
