import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_terminal_reducer_rejects_duplicate_stale_and_cross_session_events():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const ts = require('typescript');
const source = fs.readFileSync('src/store/terminalEventReducer.ts', 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
}).outputText;
const moduleRef = { exports: {} };
vm.runInNewContext(output, { module: moduleRef, exports: moduleRef.exports, require });
const reduce = moduleRef.exports.appendOrderedTerminalEvent;
const event = (session_id, seq) => ({ session_id, seq });
let state = { activeSessionId: 's1', events: [], seqBySession: { s1: 0 } };
state = reduce(state, event('s1', 1));
state = reduce(state, event('s1', 1));
state = reduce(state, event('s1', 3));
state = reduce(state, event('s1', 2));
state = reduce(state, event('s2', 4));
if (state.events.map(item => item.seq).join(',') !== '1,3') process.exit(2);
if (state.seqBySession.s1 !== 3) process.exit(3);
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_terminal_is_wired_to_sse_without_completion_timer():
    workspace = (ROOT / "src/components/UnifiedWorkspace.tsx").read_text(encoding="utf-8")
    terminal = (ROOT / "src/components/AgentTerminal.tsx").read_text(encoding="utf-8")

    assert "appendEvent(event);" in workspace
    assert "<AgentTerminal />" in workspace
    assert "setTimeout(" not in workspace
    assert "event.session_id}:${event.seq}" in terminal


def test_context_policy_control_is_wired_to_orchestrator_request():
    workspace = (ROOT / "src/components/UnifiedWorkspace.tsx").read_text(encoding="utf-8")
    api = (ROOT / "src/api/orchestrateApi.ts").read_text(encoding="utf-8")
    control = (ROOT / "src/components/ContextPolicyControl.tsx").read_text(encoding="utf-8")

    assert "<ContextPolicyControl" in workspace
    assert "contextPolicy," in workspace
    assert "parentSessionId:" in workspace
    assert "context_policy: options.contextPolicy || 'fresh'" in api
    assert "Parent session id" in control


def test_runtime_context_manifest_is_visible_without_prompt_body_rendering():
    workspace = (ROOT / "src/components/UnifiedWorkspace.tsx").read_text(encoding="utf-8")
    contracts = (ROOT / "src/api/generated/agentOsContracts.ts").read_text(encoding="utf-8")

    assert "setContextManifest(result.runtime.context_manifest);" in workspace
    assert "context-manifest-status" in workspace
    assert "interface AgentContextManifest" in contracts
    assert "context_manifest: AgentContextManifest | null;" in contracts
