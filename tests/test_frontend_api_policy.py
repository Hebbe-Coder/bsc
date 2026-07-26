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
    assert "processEnv.BSC_VITE_API_PROXY_TARGET" in source
    assert "processEnv.VITE_API_PROXY_TARGET" in source
    assert "fileEnv.BSC_VITE_API_PROXY_TARGET" in source
    assert "fileEnv.VITE_API_PROXY_TARGET" in source
    assert "|| 'http://localhost:8000';" in source
    assert "target: apiProxyTarget" in source


def test_agent_os_ui_uses_backend_status_and_trusted_audit():
    workspace = (SRC / "components" / "UnifiedWorkspace.tsx").read_text(encoding="utf-8")
    adapter = (SRC / "utils" / "agentOsAdapter.ts").read_text(encoding="utf-8")

    assert "if (result.status !== 'completed')" in workspace
    assert workspace.index("if (result.status !== 'completed')") < workspace.index(
        "setDashData(adaptAgentOsToDashboard(result))"
    )
    assert "isTrustedAudit(resp.trusted_audit)" in adapter
    assert "agent-os-chain-" not in adapter


def test_agent_os_uses_an_extended_request_budget():
    wrapper = (SRC / "api" / "fetchWrapper.ts").read_text(encoding="utf-8")
    agent_api = (SRC / "api" / "agentOsApi.ts").read_text(encoding="utf-8")
    config = (SRC / "config.ts").read_text(encoding="utf-8")

    assert "timeout?: number;" in wrapper
    assert "timeout ?? this.timeout" in wrapper
    assert "AGENT_OS_TIMEOUT" in agent_api
    assert "timeout: AGENT_OS_TIMEOUT" in agent_api
    assert "const DEFAULT_AGENT_OS_TIMEOUT = 600000;" in config
    assert "resolveAgentOsTimeout(import.meta.env.VITE_AGENT_OS_TIMEOUT)" in config


def test_evaluation_dimensions_have_unique_react_keys():
    source = (SRC / "components" / "CompilerEvalPanel.tsx").read_text(encoding="utf-8")

    assert ".map((dimension, index) =>" in source
    assert "key={`${dimension.name}-${index}`}" in source


def test_agent_os_results_render_the_generated_business_brief():
    workspace = (SRC / "components" / "UnifiedWorkspace.tsx").read_text(encoding="utf-8")
    brief = (SRC / "components" / "AgentBriefPanel.tsx").read_text(encoding="utf-8")

    assert "<AgentBriefPanel businessModel={dashData.business_model} />" in workspace
    assert "Critical Assumptions" in brief
    assert "Operating Constraints" in brief


def test_agent_os_dashboard_keeps_decision_readiness_and_source_evidence_honest():
    adapter = (SRC / "utils" / "agentOsAdapter.ts").read_text(encoding="utf-8")
    readiness = (SRC / "components" / "CompilerEvalPanel.tsx").read_text(encoding="utf-8")
    citations = (SRC / "components" / "CitationPanel.tsx").read_text(encoding="utf-8")

    assert "const citationCoverage: CitationCoverage" in adapter
    assert "coverage: sops.length > 0 ? Math.round" in adapter
    assert "is_passed: overallScore >= 70 && criticalGapCount === 0" in adapter
    assert "决策就绪度" in readiness
    assert "不等同于模型输出文本质量" in readiness
    assert "raw <= 1 ? raw * 100 : raw" in citations
    assert "待补外部证据" in citations


def test_result_panels_expose_visual_decision_signals():
    coverage = (SRC / "components" / "ConstraintCoveragePanel.tsx").read_text(encoding="utf-8")
    audit = (SRC / "components" / "TrustedAuditPanel.tsx").read_text(encoding="utf-8")

    assert "coverage-ring" in coverage
    assert "优先补证" in coverage
    assert "完整性已验证" in audit
    assert "审计事件" in audit


def test_workspace_waits_for_terminal_event_before_loading_dashboard():
    source = (SRC / "components" / "UnifiedWorkspace.tsx").read_text(encoding="utf-8")

    assert "setTimeout(" not in source
    assert "if (!event.terminal) return;" in source
    assert "if (event.type === 'pipeline.completed')" in source
    assert "fetchCompilerDashboard(res.session_id)" in source
    assert "applyDashboard(dashboard)" in source


def test_agent_os_pipeline_uses_real_capability_execution_metadata():
    source = (SRC / "components" / "UnifiedWorkspace.tsx").read_text(encoding="utf-8")

    assert "function projectAgentPipeline" in source
    assert "result.runtime.capability_executions" in source
    assert "setPipelineStages(projectAgentPipeline" in source
