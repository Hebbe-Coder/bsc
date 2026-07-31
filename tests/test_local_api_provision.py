import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _env_values(path: Path, name: str) -> list[str]:
    prefix = f"{name}="
    return [
        line.split("=", 1)[1]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]


def test_provision_syncs_a_unique_backend_key_to_the_studio_proxy(tmp_path: Path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is required to verify the local provisioner")

    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    script = Path("scripts") / "provision_local_api_access.ps1"
    provisioner = scripts / script.name
    provisioner.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")

    (project / ".env").write_text(
        "API_KEY=backend-current-key\n"
        "AUTH_SESSION_SECRET=current-session-secret\n"
        "UNRELATED_BACKEND_SETTING=preserved\n",
        encoding="utf-8",
    )
    studio_env = project / ".env.development.local"
    studio_env.write_text(
        "BSC_LOCAL_API_KEY=stale-key-one\n"
        "BSC_LOCAL_API_KEY=stale-key-two\n"
        "VITE_BSC_LOCAL_PROXY_AUTH=false\n"
        "UNRELATED_STUDIO_SETTING=preserved\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(provisioner)],
        check=True,
        capture_output=True,
        text=True,
        cwd=project,
    )

    payload = json.loads(completed.stdout)
    assert payload == {
        "backend_env_updated": True,
        "studio_proxy_updated": True,
        "api_key_rotated": False,
        "restart_required": True,
    }
    assert "backend-current-key" not in completed.stdout
    assert _env_values(project / ".env", "API_KEY") == ["backend-current-key"]
    assert _env_values(studio_env, "BSC_LOCAL_API_KEY") == ["backend-current-key"]
    assert _env_values(studio_env, "VITE_BSC_LOCAL_PROXY_AUTH") == ["true"]
    assert "UNRELATED_STUDIO_SETTING=preserved" in studio_env.read_text(encoding="utf-8")
