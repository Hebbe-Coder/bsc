"""Studio API v3 — Star-topology orchestrator endpoint."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studio", tags=["studio"])

def _ok(d): return {"success": True, "data": d}
def _err(m, c=400): raise HTTPException(c, detail={"success": False, "error": m})

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    input_text: Optional[str] = ""
    project_name: Optional[str] = "Quick Analysis"
    output_types: Optional[list[str]] = ["ppt", "html"]
    domain: Optional[str] = ""

@router.post("/ask")
async def studio_ask(req: AskRequest):
    """Natural language -> star-topology agent dispatch -> workspace."""
    if not req.question.strip():
        _err("Please provide a question or business goal.", 400)

    from app.agents.studio_orchestrator import get_studio_orchestrator
    orch = get_studio_orchestrator()

    result = orch.execute(
        question=req.question,
        input_text=req.input_text or req.question,
        project_name=req.project_name,
        output_types=req.output_types,
        domain=req.domain,
    )

    # Build template detection
    from app.engines.template_router import classify_template
    tmpl = classify_template(req.question)

    return _ok({
        "intent": "full_analysis",
        "display_name": f"Business Analysis: {result.domain}",
        "confidence": 1.0,
        "domain": result.domain,
        "summary": result.summary,
        "agents_dispatched": ["business_understanding", "sop", "risk", "strategy", "optimization", "composer", "asset"],
        "stages": result.stages,
        "report": result.workspace,
        "assets": result.workspace.get("assets", []),
        "template": {
            "type": tmpl.template_type,
            "display": tmpl.display_name,
            "confidence": tmpl.confidence,
            "slides": tmpl.slide_structure,
            "matched_keywords": tmpl.matched_keywords,
        },
        "run_id": result.run_id,
        "total_duration_ms": result.total_ms,
    })
