"""Strategy Agent — strategic analysis and planning."""
from .protocol import BaseAgent, AgentContext
import logging

logger = logging.getLogger("bsc.studio.strategy")

STRENGTH_KEYWORDS = ["automated", "efficient", "scalable", "integrated", "data-driven", "ai-powered"]
WEAKNESS_KEYWORDS = ["manual", "complex", "slow", "legacy", "dependent", "limited"]
OPPORTUNITY_KEYWORDS = ["growth", "digital", "transformation", "market", "expand", "innovation"]
THREAT_KEYWORDS = ["competition", "regulatory", "change", "disruption", "risk", "uncertainty"]


class StrategyAgent(BaseAgent):
    name = "strategy"
    description = "Performs strategic analysis: competitive positioning, market opportunity, SWOT, and recommendations"
    capabilities = ["analyze", "strategy", "planning"]

    def on_analyze(self, ctx: AgentContext, **params) -> dict:
        """
        Perform strategic analysis based on business system data.
        
        Args:
            ctx: AgentContext containing business_system data
            params: Additional parameters with business_system as fallback
        
        Returns:
            dict: Strategic analysis results with SWOT, recommendations, and market analysis
        """
        if ctx is None:
            return {"swot": {}, "recommendations": [], "market_analysis": {}, "strategic_fit": {}}

        bs = ctx.business_system or params.get("business_system", {})
        objectives = bs.get("objectives", [])
        domain = ctx.domain or bs.get("domain", bs.get("business_domain", "general"))
        processes = bs.get("processes", [])
        metrics = bs.get("metrics", [])
        risks = bs.get("risks", [])

        objective_texts = [o.get("name", "") if isinstance(o, dict) else str(o) for o in objectives if o]
        all_text = " ".join([str(p.get("name", "")) for p in processes if isinstance(p, dict)] + 
                           [str(m.get("name", "")) for m in metrics if isinstance(m, dict)] + 
                           objective_texts).lower()

        swot = self._generate_swot(objective_texts, domain, all_text, len(processes), len(risks))
        recommendations = self._generate_recommendations(objective_texts, domain, swot, len(processes), len(risks))
        market_analysis = self._generate_market_analysis(domain, objectives, processes)
        strategic_fit = self._calculate_strategic_fit(objectives, processes, risks)

        return {
            "swot": swot,
            "recommendations": recommendations,
            "market_analysis": market_analysis,
            "strategic_fit": strategic_fit,
        }

    def _generate_swot(self, objectives, domain, all_text, process_count, risk_count):
        """Generate SWOT analysis based on actual business data."""
        strengths = self._generate_strengths(objectives, domain, all_text, process_count)
        weaknesses = self._generate_weaknesses(objectives, domain, all_text, risk_count)
        opportunities = self._generate_opportunities(objectives, domain, all_text)
        threats = self._generate_threats(objectives, domain, all_text, risk_count)

        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "opportunities": opportunities,
            "threats": threats,
        }

    def _generate_strengths(self, objectives, domain, all_text, process_count):
        """Generate strengths based on business characteristics."""
        strengths = []

        if process_count > 0:
            strengths.append(f"Defined process framework with {process_count} steps")
        
        if any(kw in all_text for kw in STRENGTH_KEYWORDS):
            strengths.append("Automated and data-driven operations")
        
        if objectives:
            strengths.append(f"Clear business objectives: {objectives[0][:40]}")
        
        if domain != "general":
            strengths.append(f"Domain expertise in {domain}")
        
        if not strengths:
            strengths = [
                "Structured business process foundation",
                f"Domain focus: {domain}",
                "Capability for process automation",
            ]
        
        return strengths

    def _generate_weaknesses(self, objectives, domain, all_text, risk_count):
        """Generate weaknesses based on business characteristics."""
        weaknesses = []

        if risk_count > 3:
            weaknesses.append(f"Elevated risk exposure: {risk_count} identified risks")
        
        if any(kw in all_text for kw in WEAKNESS_KEYWORDS):
            weaknesses.append("Dependency on manual processes")
        
        if not objectives:
            weaknesses.append("Undefined business objectives")
        
        if not weaknesses:
            weaknesses = [
                "Process maturity assessment needed",
                "Limited market differentiation data",
            ]
        
        return weaknesses

    def _generate_opportunities(self, objectives, domain, all_text):
        """Generate opportunities based on business characteristics."""
        opportunities = []

        if any(kw in all_text for kw in OPPORTUNITY_KEYWORDS):
            opportunities.append("Market expansion and digital transformation")
        
        if domain != "general":
            opportunities.append(f"Deepen {domain} vertical expertise")
        
        if objectives:
            opportunities.append(f"Execute on key objective: {objectives[0][:40]}")
        
        opportunities.append("Process automation and efficiency gains")
        
        return opportunities

    def _generate_threats(self, objectives, domain, all_text, risk_count):
        """Generate threats based on business characteristics."""
        threats = []

        if any(kw in all_text for kw in THREAT_KEYWORDS):
            threats.append("Competitive landscape and market disruption")
        
        if risk_count > 5:
            threats.append("Significant operational risk exposure")
        
        threats.append("Technology and regulatory changes")
        threats.append("AI capability commoditization")
        
        return threats

    def _generate_recommendations(self, objectives, domain, swot, process_count, risk_count):
        """Generate strategic recommendations based on SWOT analysis."""
        recommendations = []

        if objectives:
            recommendations.append({
                "title": f"Strategic Priority: {objectives[0][:60]}",
                "action": "Develop phased rollout plan with measurable milestones",
                "impact": "high",
                "timeframe": "Q1-Q2",
                "related_swot": ["strengths", "opportunities"],
            })

        if risk_count > 3:
            recommendations.append({
                "title": "Risk Mitigation Strategy",
                "action": f"Address top {min(risk_count, 3)} risks before scaling operations",
                "impact": "high",
                "timeframe": "Q1",
                "related_swot": ["weaknesses", "threats"],
            })

        if domain != "general":
            recommendations.append({
                "title": f"Build {domain} Industry Knowledge Base",
                "action": f"Curate {domain} best practices, templates, and benchmarks",
                "impact": "medium",
                "timeframe": "Q2-Q3",
                "related_swot": ["strengths", "opportunities"],
            })

        recommendations.append({
            "title": "Establish Quality and Performance Metrics",
            "action": "Define KPIs for process efficiency, accuracy, and customer satisfaction",
            "impact": "high",
            "timeframe": "Q1",
            "related_swot": ["strengths"],
        })

        if process_count > 10:
            recommendations.append({
                "title": "Process Simplification Initiative",
                "action": "Identify and eliminate redundant steps in complex workflows",
                "impact": "medium",
                "timeframe": "Q2",
                "related_swot": ["weaknesses"],
            })

        return recommendations

    def _generate_market_analysis(self, domain, objectives, processes):
        """Generate market analysis based on business data."""
        domain_size = {
            "finance": "Large enterprise market",
            "healthcare": "Regulated growth market",
            "retail": "High volume market",
            "manufacturing": "Industrial market",
            "general": "Broad enterprise market",
        }

        competitive_position = {
            "finance": "Compliance-focused differentiator",
            "healthcare": "Security and privacy differentiator",
            "retail": "Speed and efficiency differentiator",
            "manufacturing": "Process optimization differentiator",
            "general": "Flexible business system compiler",
        }

        return {
            "domain": domain,
            "total_addressable": domain_size.get(domain, "Enterprise consulting market"),
            "competitive_position": competitive_position.get(domain, "Early mover in AI business system compilation"),
            "differentiators": [
                "Speed (automated compilation)",
                "Consistency (standardized output)",
                "Consulting-grade output quality",
                f"Domain expertise: {domain}",
            ],
            "market_timing": "Favorable - digital transformation acceleration",
        }

    def _calculate_strategic_fit(self, objectives, processes, risks):
        """Calculate strategic fit score."""
        objective_score = min(len(objectives) * 20, 40)
        process_score = min(len(processes) * 5, 30)
        risk_score = max(0, 30 - len(risks) * 3)

        total_score = objective_score + process_score + risk_score

        if total_score >= 80:
            fit_level = "excellent"
        elif total_score >= 60:
            fit_level = "good"
        elif total_score >= 40:
            fit_level = "moderate"
        else:
            fit_level = "needs improvement"

        return {
            "score": total_score,
            "level": fit_level,
            "factors": {
                "objective_clarity": objective_score,
                "process_maturity": process_score,
                "risk_posture": risk_score,
            },
            "recommendations": self._fit_recommendations(total_score, len(objectives), len(processes), len(risks)),
        }

    def _fit_recommendations(self, score, objective_count, process_count, risk_count):
        """Generate recommendations based on strategic fit score."""
        recs = []
        if objective_count == 0:
            recs.append("Define clear business objectives")
        if process_count < 3:
            recs.append("Expand process definition")
        if risk_count > 5:
            recs.append("Prioritize risk mitigation")
        if score < 60:
            recs.append("Conduct strategic review")
        return recs
