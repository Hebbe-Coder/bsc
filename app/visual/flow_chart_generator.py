"""Generate Mermaid diagrams from a compiled business-system payload."""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any, Dict, Iterable, Optional


class FlowChartGenerator:
    """Generate flow, mind-map, sequence, and state Mermaid diagrams."""

    def __init__(self) -> None:
        self._mermaid_cli_path = self._find_mermaid_cli()

    def _find_mermaid_cli(self) -> Optional[str]:
        for command, value in ((["npx", "mmdc", "--version"], "npx mmdc"), (["mmdc", "--version"], "mmdc")):
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            except OSError:
                continue
            if result.returncode == 0:
                return value
        return None

    def generate_flowchart(self, business_system: Dict[str, Any]) -> str:
        workflow = _items(business_system.get("workflow"))
        objectives = _items(business_system.get("objectives"))
        lines = [
            "flowchart TD",
            "    classDef start fill:#4CAF50,color:#fff",
            "    classDef process fill:#2196F3,color:#fff",
            "    classDef end fill:#f44336,color:#fff",
        ]
        if not workflow:
            return "\n".join(lines + ["    start[Start]:::start", "    start --> finish[Complete]:::end"])

        for index, step in enumerate(workflow, 1):
            style = "start" if index == 1 else "end" if index == len(workflow) else "process"
            lines.append(f"    step{index}[{_label(step, f'Step {index}')}]:::{style}")
            if index > 1:
                lines.append(f"    step{index - 1} --> step{index}")
        if objectives:
            lines.append("    subgraph Objectives")
            for index, objective in enumerate(objectives[:3], 1):
                lines.append(f"        objective{index}[{_label(objective, f'Objective {index}')}]")
            lines.append("    end")
        return "\n".join(lines)

    def generate_mindmap(self, business_system: Dict[str, Any]) -> str:
        domain = str(business_system.get("business_domain") or "Business System")
        lines = ["mindmap", f"    root(({_clean(domain)}))"]
        self._mindmap_section(lines, "Objectives", _items(business_system.get("objectives")))
        self._mindmap_section(lines, "Workflow", _items(business_system.get("workflow")))
        self._mindmap_section(lines, "Modules", _items(business_system.get("modules")))
        self._mindmap_section(lines, "Risks", _items(business_system.get("risks")))
        return "\n".join(lines)

    def generate_sequence_diagram(self, business_system: Dict[str, Any]) -> str:
        workflow = _items(business_system.get("workflow"))
        roles = _items(business_system.get("roles"))
        participants = {"User", "System"}
        for item in [*workflow, *roles]:
            actor = str(item.get("actor") or item.get("role") or item.get("name") or "")
            if actor:
                participants.add(_clean(actor))
        lines = ["sequenceDiagram", *[f"    participant {participant}" for participant in sorted(participants)]]
        for index, step in enumerate(workflow[:15], 1):
            actor = _clean(str(step.get("actor") or step.get("role") or "User"))
            action = _label(step, f"Step {index}")
            arrow = "->>System" if index % 2 else "-->>System"
            lines.append(f"    {actor}{arrow}: {action}")
        if not workflow:
            lines.append("    User->>System: Start")
            lines.append("    System-->>User: Complete")
        return "\n".join(lines)

    def generate_state_diagram(self, business_system: Dict[str, Any]) -> str:
        workflow = _items(business_system.get("workflow"))
        if not workflow:
            return "\n".join(
                [
                    "stateDiagram-v2",
                    "    [*] --> Idle",
                    "    Idle --> Processing",
                    "    Processing --> Completed",
                    "    Completed --> [*]",
                ]
            )
        names = [_label(step, f"Step {index}") for index, step in enumerate(workflow[:10], 1)]
        lines = ["stateDiagram-v2", f"    [*] --> {names[0]}"]
        lines.extend(f"    {names[index]} --> {names[index + 1]}" for index in range(len(names) - 1))
        lines.extend([f"    {names[-1]} --> Completed", "    Completed --> [*]"])
        return "\n".join(lines)

    def render_to_svg(self, mermaid_code: str, output_path: str | None = None) -> str:
        return self._render(mermaid_code, output_path, ".svg")

    def render_to_png(self, mermaid_code: str, output_path: str | None = None) -> str:
        return self._render(mermaid_code, output_path, ".png")

    def _render(self, mermaid_code: str, output_path: str | None, suffix: str) -> str:
        if not self._mermaid_cli_path:
            raise RuntimeError("mermaid-cli is unavailable; install @mermaid-js/mermaid-cli")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False, encoding="utf-8") as source:
            source.write(mermaid_code)
            input_path = source.name
        target_path = output_path or input_path.replace(".mmd", suffix)
        command = self._mermaid_cli_path.split() + ["-i", input_path, "-o", target_path]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"Mermaid rendering failed: {result.stderr.strip()}")
            return target_path
        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)

    def generate_all(self, business_system: Dict[str, Any]) -> Dict[str, str]:
        return {
            "flowchart": self.generate_flowchart(business_system),
            "mindmap": self.generate_mindmap(business_system),
            "sequence_diagram": self.generate_sequence_diagram(business_system),
            "state_diagram": self.generate_state_diagram(business_system),
        }

    @staticmethod
    def _mindmap_section(lines: list[str], title: str, values: Iterable[Dict[str, Any]]) -> None:
        values = list(values)
        if not values:
            return
        lines.append(f"        {title}")
        for index, value in enumerate(values[:5], 1):
            lines.append(f"            {_label(value, f'{title} {index}')}")


def _items(value: Any) -> list[Dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _label(item: Dict[str, Any], fallback: str) -> str:
    return _clean(str(item.get("name") or item.get("objective") or item.get("risk") or fallback))


def _clean(value: str) -> str:
    return value.replace("\n", " ").replace("[", "(").replace("]", ")").replace('"', "'")
