from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_frontend_network_calls_use_the_single_fetch_wrapper():
    direct_fetches = []
    for path in SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or path.name == "fetchWrapper.ts":
            continue
        if "fetch(" in path.read_text(encoding="utf-8"):
            direct_fetches.append(path.relative_to(ROOT))

    assert direct_fetches == []


def test_orchestrator_sse_uses_browser_session_credentials():
    source = (SRC / "api" / "orchestrateApi.ts").read_text(encoding="utf-8")

    assert "new EventSource(url, { withCredentials: true })" in source


def test_fetch_wrapper_defaults_to_same_origin_credentials():
    source = (SRC / "api" / "fetchWrapper.ts").read_text(encoding="utf-8")

    assert "credentials: options.credentials ?? 'same-origin'" in source


def test_fetch_wrapper_consumes_error_body_once():
    source = (SRC / "api" / "fetchWrapper.ts").read_text(encoding="utf-8")
    parser = source.split("private async parseErrorResponse", 1)[1].split(
        "private async delay", 1
    )[0]

    assert parser.count("response.text()") == 1
    assert "response.json()" not in parser
    assert "JSON.parse(body)" in parser


def test_vite_proxies_agent_os_routes_to_backend():
    source = (ROOT / "vite.config.ts").read_text(encoding="utf-8")

    assert "'/agent':" in source
    assert "target: 'http://localhost:8000'" in source


def test_workspace_waits_for_terminal_event_before_loading_dashboard():
    source = (SRC / "components" / "UnifiedWorkspace.tsx").read_text(encoding="utf-8")

    assert "setTimeout(" not in source
    assert "if (!event.terminal) return;" in source
    assert "if (event.type === 'pipeline.completed')" in source
    assert "fetchCompilerDashboard(res.session_id)" in source
    assert "applyDashboard(dashboard)" in source
