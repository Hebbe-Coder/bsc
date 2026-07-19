"""Optimization Agent — identifies bottlenecks and recommends improvements."""
from .protocol import BaseAgent, AgentContext
import logging

logger = logging.getLogger("bsc.studio.optimization")

AUTOMATION_KEYWORDS = ["filter", "classify", "route", "sort", "tag", "notify", "validate", "extract", "format"]
MANUAL_KEYWORDS = ["review", "approve", "inspect", "verify", "check"]
BOTTLENECK_KEYWORDS = ["queue", "wait", "hold", "pending", "delay"]


class OptimizationAgent(BaseAgent):
    name = "optimization"
    description = "Identifies bottlenecks, inefficiencies, and recommends process optimizations"
    capabilities = ["analyze", "optimize", "improve"]

    def on_analyze(self, ctx: AgentContext, **params) -> dict:
        """
        Analyze business system for optimization opportunities.
        
        Args:
            ctx: AgentContext containing business_system data
            params: Additional parameters with business_system as fallback
        
        Returns:
            dict: Optimization analysis with bottlenecks, recommendations, and automation potential
        """
        if ctx is None:
            return {
                "bottlenecks": [],
                "efficiency_recommendations": [],
                "automation_potential": {},
                "estimated_savings": "",
                "process_health": {},
            }

        bs = ctx.business_system or params.get("business_system", {})
        processes = bs.get("processes", [])
        metrics = bs.get("metrics", [])
        risks = bs.get("risks", [])

        bottlenecks = self._identify_bottlenecks(processes, metrics, risks)
        efficiency_recs = self._generate_efficiency_recommendations(processes, metrics, bottlenecks)
        automation_potential = self._calculate_automation_potential(processes)
        process_health = self._calculate_process_health(processes, bottlenecks, automation_potential)

        return {
            "bottlenecks": bottlenecks[:5],
            "efficiency_recommendations": efficiency_recs,
            "automation_potential": automation_potential,
            "estimated_savings": f"{int(automation_potential['automation_rate'] * 100)}% of processes can be fully automated",
            "process_health": process_health,
        }

    def _identify_bottlenecks(self, processes, metrics, risks):
        """Identify bottlenecks based on process characteristics and keyword analysis."""
        bottlenecks = []
        
        for i, proc in enumerate(processes):
            name = proc.get("name", f"Step {i+1}") if isinstance(proc, dict) else str(proc)
            name_lower = str(name).lower()
            
            is_bottleneck = False
            bottleneck_type = ""
            cause = ""
            impact = ""
            suggestion = ""

            if "review" in name_lower or "approve" in name_lower:
                is_bottleneck = True
                bottleneck_type = "approval"
                cause = "Manual approval creates sequential dependency"
                impact = "Delays cascade through entire workflow"
                suggestion = f"Implement automated approval rules or parallel review for step {i+1}"

            elif "quality" in name_lower or "verify" in name_lower:
                is_bottleneck = True
                bottleneck_type = "quality"
                cause = "100% manual quality check"
                impact = "High effort with diminishing returns"
                suggestion = f"Implement sampling-based QA for step {i+1}"

            elif any(kw in name_lower for kw in BOTTLENECK_KEYWORDS):
                is_bottleneck = True
                bottleneck_type = "queue"
                cause = "Queue or waiting state detected"
                impact = "Build-up during peak periods"
                suggestion = f"Implement dynamic queue management for step {i+1}"

            elif i >= len(processes) - 2:
                is_bottleneck = True
                bottleneck_type = "sequential"
                cause = "Later steps accumulate upstream delays"
                impact = "Final steps become throughput constraint"
                suggestion = f"Consider parallelizing step {i+1}"

            if is_bottleneck:
                bottlenecks.append({
                    "step": i + 1,
                    "name": str(name)[:80],
                    "type": bottleneck_type,
                    "cause": cause,
                    "impact": impact,
                    "suggestion": suggestion,
                    "expected_improvement": self._estimate_improvement(bottleneck_type, i, len(processes)),
                })

        if not bottlenecks and processes:
            bottlenecks = [{
                "step": 1,
                "name": "Intake processing",
                "type": "capacity",
                "cause": "Single-threaded entry point",
                "impact": "Limits overall throughput",
                "suggestion": "Implement load-balanced intake queue",
                "expected_improvement": "30% throughput increase",
            }]

        return bottlenecks

    def _estimate_improvement(self, bottleneck_type, step_index, total_steps):
        """Estimate expected improvement based on bottleneck type and position."""
        improvements = {
            "approval": "40-60% reduction in approval time",
            "quality": "70% reduction in QA effort",
            "queue": "50% reduction in waiting time",
            "sequential": f"{20 + step_index * 5}% throughput increase",
            "capacity": "30% throughput increase",
        }
        return improvements.get(bottleneck_type, "20-30% improvement")

    def _generate_efficiency_recommendations(self, processes, metrics, bottlenecks):
        """Generate efficiency recommendations based on actual process data."""
        recommendations = []
        
        manual_steps = sum(1 for p in processes if self._is_manual_step(p))
        automation_rate = self._calculate_automation_potential(processes)["automation_rate"]
        bottleneck_count = len(bottlenecks)

        if automation_rate > 0.2:
            recommendations.append({
                "area": "Automation",
                "recommendation": f"Automate {int(automation_rate * 100)}% of filter/classify/route steps to reduce manual touch points",
                "roi": f"High - reduce headcount by {int(automation_rate * 40)}%",
                "priority": "high",
                "affected_steps": [p.get("name", "") for p in processes if self._is_automatable(p)][:3],
            })

        if manual_steps > len(processes) // 2:
            recommendations.append({
                "area": "Quality",
                "recommendation": f"Add sampling-based QA for {manual_steps} manual steps instead of 100% review",
                "roi": "Medium - reduce effort by 70% with minimal quality tradeoff",
                "priority": "medium",
                "affected_steps": [p.get("name", "") for p in processes if self._is_manual_step(p)][:3],
            })

        if bottleneck_count >= 2:
            recommendations.append({
                "area": "Capacity",
                "recommendation": f"Implement elastic scaling for {bottleneck_count} identified bottlenecks during peak hours",
                "roi": "High - prevent SLA breaches at minimal cost",
                "priority": "high",
                "affected_steps": [b["name"] for b in bottlenecks[:3]],
            })

        if metrics:
            recommendations.append({
                "area": "Monitoring",
                "recommendation": f"Set up automated monitoring for {len(metrics)} key metrics with alerting thresholds",
                "roi": "Medium - early detection prevents escalation",
                "priority": "medium",
                "affected_steps": [],
            })

        if not recommendations:
            recommendations = [{
                "area": "Baseline",
                "recommendation": "Establish performance baseline and implement trend analysis for continuous improvement",
                "roi": "Medium - provides data foundation for future optimizations",
                "priority": "low",
                "affected_steps": [],
            }]

        return recommendations

    def _is_manual_step(self, proc):
        """Check if a step appears to be manual."""
        if not isinstance(proc, dict):
            return False
        name = str(proc.get("name", "")).lower()
        action = str(proc.get("action", "")).lower()
        return any(kw in name or kw in action for kw in MANUAL_KEYWORDS)

    def _is_automatable(self, proc):
        """Check if a step can be automated."""
        if not isinstance(proc, dict):
            return False
        name = str(proc.get("name", "")).lower()
        action = str(proc.get("action", "")).lower()
        return any(kw in name or kw in action for kw in AUTOMATION_KEYWORDS)

    def _calculate_automation_potential(self, processes):
        """Calculate automation potential based on process characteristics."""
        total_processes = len(processes)
        automatable = sum(1 for p in processes if self._is_automatable(p))
        auto_rate = automatable / max(total_processes, 1)

        return {
            "automatable_steps": automatable,
            "total_steps": total_processes,
            "automation_rate": round(auto_rate, 2),
            "automatable_actions": [p.get("name", "") for p in processes if self._is_automatable(p)][:5],
        }

    def _calculate_process_health(self, processes, bottlenecks, automation_potential):
        """Calculate overall process health score."""
        total_steps = len(processes)
        bottleneck_count = len(bottlenecks)
        automation_rate = automation_potential["automation_rate"]

        base_score = 80
        bottleneck_penalty = bottleneck_count * 5
        automation_bonus = int(automation_rate * 20)
        complexity_penalty = max(0, (total_steps - 10) * 2)

        health_score = max(0, min(100, base_score - bottleneck_penalty + automation_bonus - complexity_penalty))

        if health_score >= 80:
            health_level = "healthy"
        elif health_score >= 60:
            health_level = "moderate"
        elif health_score >= 40:
            health_level = "warning"
        else:
            health_level = "critical"

        return {
            "score": health_score,
            "level": health_level,
            "factors": {
                "bottleneck_penalty": bottleneck_penalty,
                "automation_bonus": automation_bonus,
                "complexity_penalty": complexity_penalty,
            },
            "recommendations": self._health_recommendations(health_score, bottleneck_count, automation_rate),
        }

    def _health_recommendations(self, score, bottleneck_count, automation_rate):
        """Generate health-based recommendations."""
        recs = []
        if bottleneck_count > 0:
            recs.append(f"Address {bottleneck_count} bottleneck(s)")
        if automation_rate < 0.3:
            recs.append("Identify more automatable steps")
        if score < 60:
            recs.append("Conduct comprehensive process review")
        return recs
