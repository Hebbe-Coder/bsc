"""SOP Agent — generates standard operating procedures from business model."""
from .protocol import BaseAgent, AgentContext, AgentResult, AgentStatus
import logging

logger = logging.getLogger("bsc.studio.sop")

SLA_BASELINE = {
    "intake": {"base": 5, "variance": 2},
    "process": {"base": 15, "variance": 10},
    "review": {"base": 30, "variance": 15},
    "approve": {"base": 60, "variance": 30},
    "verify": {"base": 20, "variance": 10},
    "output": {"base": 5, "variance": 2},
    "notify": {"base": 5, "variance": 2},
}

ROLE_ASSIGNMENT = {
    "intake": ["receptionist", "operator", "front desk"],
    "process": ["analyst", "specialist", "technician", "processor"],
    "review": ["reviewer", "supervisor", "manager"],
    "approve": ["manager", "director", "approver"],
    "verify": ["qa", "quality", "auditor"],
    "output": ["operator", "dispatcher"],
    "notify": ["notifier", "communicator"],
}


class SOPAgent(BaseAgent):
    name = "sop"
    description = "Generates SOP procedures, workflows, and SLA definitions from business model"
    capabilities = ["generate", "sop", "workflow", "procedure"]

    def on_generate(self, ctx: AgentContext, **params) -> dict:
        """
        Generate SOP procedures from the business system context.
        
        Args:
            ctx: AgentContext containing business_system data
            params: Additional parameters with business_system as fallback
        
        Returns:
            dict: SOP generation results with procedures, workflow steps, and role assignments
        """
        if ctx is None:
            return {"sop": [], "total_steps": 0, "roles_used": [], "has_escalation": False}

        bs = ctx.business_system or params.get("business_system", {})
        processes = bs.get("processes", [])
        objectives = bs.get("objectives", [])
        roles = bs.get("roles", [])

        role_names = self._extract_role_names(roles)
        sop_entries = []

        for i, proc in enumerate(processes):
            name = proc.get("name", f"Step {i+1}") if isinstance(proc, dict) else str(proc)
            action = proc.get("action", "process") if isinstance(proc, dict) else "process"
            
            owner = self._assign_role(name, action, i, role_names)
            sla = self._calculate_sla(name, action, i, len(processes))
            escalation = self._determine_escalation(i, len(processes))

            sop_entries.append({
                "step": i + 1,
                "name": name[:80],
                "action": action,
                "owner": str(owner),
                "input": "Previous step output" if i > 0 else "Incoming request",
                "output": f"Processed {name[:30]}",
                "sla": sla,
                "escalation": escalation,
                "risk_points": self._identify_risk_points(proc, i),
                "dependencies": [i] if i > 0 else [],
            })

        if not sop_entries:
            sop_entries = self._generate_default_sop(role_names)

        return {
            "sop": sop_entries,
            "total_steps": len(sop_entries),
            "roles_used": list(set(e["owner"] for e in sop_entries)),
            "has_escalation": any(e.get("escalation") for e in sop_entries),
            "workflow": self._build_workflow(sop_entries),
        }

    def _extract_role_names(self, roles):
        """Extract role names from roles list."""
        role_names = []
        for r in roles:
            if isinstance(r, dict):
                role_names.append(r.get("name", ""))
            else:
                role_names.append(str(r))
        return [r for r in role_names if r]

    def _assign_role(self, name, action, step_index, available_roles):
        """Assign appropriate role based on action type and available roles."""
        action_lower = str(action).lower()
        
        for action_key, possible_roles in ROLE_ASSIGNMENT.items():
            if action_key in action_lower or action_key in str(name).lower():
                matched = [r for r in available_roles if any(pr in r.lower() for pr in possible_roles)]
                if matched:
                    return matched[step_index % len(matched)]
                return possible_roles[0]

        if available_roles:
            return available_roles[step_index % len(available_roles)]
        
        return self._default_role_for_step(step_index)

    def _default_role_for_step(self, step_index):
        """Determine default role based on step position."""
        if step_index == 0:
            return "operator"
        elif step_index == len(self._generate_default_sop([])) - 1:
            return "manager"
        elif step_index > len(self._generate_default_sop([])) // 2:
            return "reviewer"
        return "operator"

    def _calculate_sla(self, name, action, step_index, total_steps):
        """Calculate dynamic SLA based on action type and process complexity."""
        action_lower = str(action).lower()
        name_lower = str(name).lower()
        
        for action_key, config in SLA_BASELINE.items():
            if action_key in action_lower or action_key in name_lower:
                complexity_factor = min(total_steps / 5, 2)
                base = config["base"] * complexity_factor
                variance = config["variance"] * (1 + step_index / total_steps)
                return f"{int(base + variance)} min"

        base_sla = 15
        if step_index == 0:
            base_sla = 5
        elif step_index >= total_steps - 2:
            base_sla = 30
        
        return f"{base_sla} min"

    def _determine_escalation(self, step_index, total_steps):
        """Determine escalation path based on step position and criticality."""
        if step_index == 0:
            return ""
        if step_index >= total_steps - 2:
            return "Manager review required"
        if step_index == total_steps // 2:
            return "Supervisor review"
        return ""

    def _identify_risk_points(self, proc, step_index):
        """Identify potential risk points for this step."""
        risk_points = []
        
        if isinstance(proc, dict):
            name = proc.get("name", "")
            if "review" in str(name).lower():
                risk_points.append("Manual review bottleneck")
            if "approve" in str(name).lower():
                risk_points.append("Approval delay")
        
        if step_index == 0:
            risk_points.append("High volume entry point")
        
        return risk_points[:3]

    def _generate_default_sop(self, role_names):
        """Generate default SOP when no processes are available."""
        steps = [
            {"name": "Intake", "action": "receive", "owner": self._assign_role("Intake", "receive", 0, role_names), "sla": "5 min"},
            {"name": "Classification", "action": "classify", "owner": self._assign_role("Classification", "classify", 1, role_names), "sla": "10 min"},
            {"name": "Processing", "action": "process", "owner": self._assign_role("Processing", "process", 2, role_names), "sla": "15 min"},
            {"name": "Quality Check", "action": "verify", "owner": self._assign_role("Quality Check", "verify", 3, role_names), "sla": "20 min"},
            {"name": "Review", "action": "review", "owner": self._assign_role("Review", "review", 4, role_names), "sla": "30 min"},
            {"name": "Output", "action": "output", "owner": self._assign_role("Output", "output", 5, role_names), "sla": "5 min"},
        ]
        
        for i, step in enumerate(steps):
            step["step"] = i + 1
            step["input"] = "Previous step output" if i > 0 else "Incoming request"
            step["output"] = f"Processed {step['name'][:30]}"
            step["escalation"] = self._determine_escalation(i, len(steps))
            step["risk_points"] = self._identify_risk_points(step, i)
            step["dependencies"] = [i] if i > 0 else []
        
        return steps

    def _build_workflow(self, sop_entries):
        """Build workflow structure from SOP entries."""
        return [
            {
                "step": entry["step"],
                "name": entry["name"],
                "action": entry["action"],
                "owner": entry["owner"],
                "sla": entry["sla"],
                "dependencies": entry["dependencies"],
            }
            for entry in sop_entries
        ]
