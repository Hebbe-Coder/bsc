from app.engines.sop_report_engine import SOPReportEngine


_PAYLOAD = "<script>alert(1)</script>"


def _build_report(payload: str) -> dict:
    return {
        "title": payload,
        "generated_at": "2026-07-11 00:00:00",
        "overview": {
            "description": payload,
            "business_domain": "测试域",
            "total_steps": 1,
            "total_roles": 1,
            "total_sla_items": 0,
            "has_escalation": False,
            "estimated_duration": "1h",
            "core_objectives": [payload],
        },
        "workflow_detail": {
            "total_steps": 1,
            "steps": [{
                "step": 1, "name": payload, "action": "a", "role": "r",
                "input": "i", "output": "o", "sla": "1d",
                "risks": [payload], "mitigations": ["m"],
            }],
        },
        "role_responsibilities": {
            "total_roles": 1,
            "roles": [{
                "name": payload, "department": "d", "level": "L1",
                "headcount": 1, "responsible_steps": [{"step": 1, "name": payload}],
                "responsibilities": [payload],
            }],
        },
        "sla_summary": {
            "total_sla_items": 0, "sla_items": [],
            "step_slas": [{"step": 1, "name": payload, "sla": "1d"}],
            "estimated_total_duration": "1h",
        },
        "risk_assessment": {
            "total_risks": 1, "severity_distribution": {},
            "risks": [{
                "risk": payload, "severity": "high", "probability": "中",
                "mitigation": payload, "category": "c",
            }],
        },
        "flowchart": {
            "total_nodes": 1, "total_edges": 0,
            "nodes": [{"step": 1, "name": payload}],
        },
        "csf": {
            "total_factors": 1,
            "factors": [{
                "name": payload, "impact": "高", "status": "已满足",
                "description": payload, "actions": [payload],
            }],
        },
    }


def test_export_to_html_escapes_xss_payload():
    engine = SOPReportEngine()
    html = engine.export_to_html(_build_report(_PAYLOAD))
    assert "<script>" not in html, "原始 <script> 未被转义，存在 XSS"
    assert "&lt;script&gt;" in html, "转义后的实体未出现在输出中"
