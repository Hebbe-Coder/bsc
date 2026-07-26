"""Static, fail-closed quality checks for BSC-managed method packages.

The method registry materializes a proposal as ``SKILL.md`` in a project Vault.
This auditor deliberately does not execute the proposed instructions, scripts, or
links. It only inspects the exact body and manifest that BSC will persist.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


AUDIT_REVISION = "method-package-audit-v1"
_REQUIRED_MANIFEST_FIELDS = (
    "task_family",
    "applicability",
    "exclusions",
    "inputs",
    "outputs",
    "steps",
    "evidence_rules",
    "failure_handling",
    "eval_cases",
)
_NONEMPTY_MANIFEST_FIELDS = {
    "task_family", "applicability", "inputs", "outputs", "steps",
    "evidence_rules", "failure_handling",
}
_SHELL_PIPE = re.compile(r"(?i)(?:curl|wget|iwr|irm)\b[^\n|]{0,240}\|\s*(?:sudo\s+)?(?:ba|z|fi|da)?sh\b|\|\s*iex\b")
_DECODE_EXEC = re.compile(r"(?i)(?:eval|exec|invoke-expression|new\s+function)\s*\([^\n]{0,220}(?:base64|b64decode|atob|fromhex)")
_SECRET = re.compile(r"\b(?:sk|rk|api)[-_][A-Za-z0-9_-]{20,}\b")
_ESCAPING_REFERENCE = re.compile(r"(?<![A-Za-z0-9_.-])(?:scripts|references|assets|evals)/(?:[^\s`)]*/)?\.\.[^\s`)]*")
_UNSAFE_INSTRUCTION = re.compile(r"(?i)\b(?:ignore|bypass|disable)\b[^\n]{0,80}\b(?:security|safety|guardrail|previous instructions?)\b")
_PRIVILEGED_KEYS = {
    "commands", "command", "hooks", "agents", "requires_code",
    "requires_filesystem", "requires_network", "requires_mcp_permission",
    "mcp_permissions", "capabilities",
}


class MethodPackageAuditor:
    """Audit BSC method content before evaluation or publication."""

    def audit(self, *, body: str, manifest: dict[str, Any]) -> dict[str, Any]:
        canonical = json.dumps(
            {"body": body, "manifest": manifest},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        findings: list[dict[str, str]] = []
        if not isinstance(manifest, dict):
            findings.append(self._finding("PKG001", "error", "manifest must be a JSON object"))
            manifest = {}

        if not body.strip():
            findings.append(self._finding("PKG002", "error", "method body must not be blank"))
        body_lines = body.splitlines()
        if len(body_lines) > 500:
            findings.append(self._finding("PKG003", "error", "method body exceeds the 500-line package budget"))
        for field in _REQUIRED_MANIFEST_FIELDS:
            if field not in manifest:
                findings.append(self._finding("PKG004", "error", f"manifest field {field!r} is required"))
                continue
            if field in _NONEMPTY_MANIFEST_FIELDS and manifest.get(field) in (None, "", [], {}):
                findings.append(self._finding("PKG005", "error", f"manifest field {field!r} must not be empty"))

        if _SHELL_PIPE.search(body):
            findings.append(self._finding("SEC001", "critical", "remote content is piped directly into a shell"))
        if _DECODE_EXEC.search(body):
            findings.append(self._finding("SEC002", "critical", "decoded content is passed to dynamic execution"))
        if _SECRET.search(body):
            findings.append(self._finding("SEC003", "critical", "method body appears to contain a provider credential"))
        if _ESCAPING_REFERENCE.search(body):
            findings.append(self._finding("SEC004", "critical", "method body contains a resource path that escapes its package"))
        if _UNSAFE_INSTRUCTION.search(body):
            findings.append(self._finding("SEC005", "error", "method body instructs the runtime to bypass safety or prior instructions"))

        for key, value in self._walk_manifest(manifest):
            if key in _PRIVILEGED_KEYS and value not in (None, False, "", [], {}):
                findings.append(self._finding(
                    "POL001", "warning",
                    f"manifest declares privileged capability {key!r}; system-admin approval remains required",
                ))

        blocking = any(item["severity"] in {"critical", "error"} for item in findings)
        return {
            "revision": AUDIT_REVISION,
            "content_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "passed": not blocking,
            "blocking": blocking,
            "findings": findings,
            "counts": {
                severity: sum(item["severity"] == severity for item in findings)
                for severity in ("critical", "error", "warning")
            },
        }

    @staticmethod
    def _finding(rule: str, severity: str, message: str) -> dict[str, str]:
        return {"rule": rule, "severity": severity, "message": message}

    @classmethod
    def _walk_manifest(cls, value: Any):
        if isinstance(value, dict):
            for key, item in value.items():
                yield str(key), item
                yield from cls._walk_manifest(item)
        elif isinstance(value, list):
            for item in value:
                yield from cls._walk_manifest(item)
