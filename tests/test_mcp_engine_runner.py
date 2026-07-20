import json
import subprocess
import sys

import pytest

from app.mcp import server


def test_engine_subprocess_preserves_structured_child_failure(monkeypatch):
    monkeypatch.setattr(server, "_get_windows_job_object", lambda: None)

    def fake_run(*args, **kwargs):
        assert kwargs["timeout"] == 12
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=json.dumps({
                "error": "provider unavailable",
                "error_code": "transient",
                "mode": "compile",
            }),
            stderr="provider connection reset",
        )

    monkeypatch.setattr(server.subprocess, "run", fake_run)

    with pytest.raises(server.MCPExecutionError, match=r"\[transient\]") as error:
        server._run_engine_subprocess("compile", {"description": "x"}, timeout=12)

    assert error.value.mode == "compile"
    assert error.value.error_code == "transient"
    assert error.value.stderr == "provider connection reset"


def test_engine_subprocess_rejects_invalid_success_output(monkeypatch):
    monkeypatch.setattr(server, "_get_windows_job_object", lambda: None)

    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="not-json",
            stderr="",
        ),
    )

    with pytest.raises(server.MCPExecutionError, match="invalid_runner_output") as error:
        server._run_engine_subprocess("ask", {"question": "x"})

    assert error.value.error_code == "invalid_runner_output"


def test_engine_subprocess_returns_json_object(monkeypatch):
    monkeypatch.setattr(server, "_get_windows_job_object", lambda: None)

    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"answer": "ok"}),
            stderr="",
        ),
    )

    assert server._run_engine_subprocess("ask", {"question": "x"}) == {"answer": "ok"}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object behavior")
def test_windows_engine_process_is_not_started_suspended(monkeypatch):
    captured = {}

    class FakeProcess:
        returncode = 0
        _handle = 1

        def communicate(self, timeout):
            return json.dumps({"answer": "ok"}), ""

    class FakeKernel32:
        def AssignProcessToJobObject(self, job_handle, process_handle):
            captured["assigned"] = (job_handle, process_handle)
            return 1

        def CloseHandle(self, job_handle):
            captured["closed"] = job_handle
            return 1

    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "_get_windows_job_object", lambda: 99)
    monkeypatch.setattr(server.subprocess, "Popen", lambda *args, **kwargs: (
        captured.update(kwargs) or FakeProcess()
    ))
    monkeypatch.setattr(
        "ctypes.WinDLL",
        lambda *args, **kwargs: FakeKernel32(),
    )

    assert server._run_engine_subprocess("ask", {"question": "x"}) == {"answer": "ok"}
    assert captured["assigned"] == (99, 1)
    assert captured["closed"] == 99
    assert captured["creationflags"] == server.subprocess.CREATE_NEW_PROCESS_GROUP
