"""HTTP JSON-RPC and SSE transport for the BSC MCP tool surface."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.mcp import server
from app.mcp.compatibility import build_compatibility_profile, normalize_mcp_result

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
_sse_sessions: dict[str, asyncio.Queue[dict[str, Any]]] = {}

_TOOL_HANDLERS = {
    "bsc_mcp_compatibility_profile": server.bsc_mcp_compatibility_profile,
    "bsc_compile": server.bsc_compile,
    "bsc_generate_sop": server.bsc_generate_sop,
    "knowledge_ask": server.knowledge_ask,
    "wiki_guide": server.wiki_guide,
    "wiki_search": server.wiki_search,
    "wiki_graph": server.wiki_graph,
    "wiki_evidence": server.wiki_evidence,
    "wiki_evidence_record": server.wiki_evidence_record,
    "wiki_read": server.wiki_read,
    "wiki_propose_update": server.wiki_propose_update,
    "wiki_lint": server.wiki_lint,
    "wiki_apply_update": server.wiki_apply_update,
    "wiki_distill": server.wiki_distill,
    "wiki_schedule": server.wiki_schedule,
    "knowledge_growth_profile": server.knowledge_growth_profile,
    "knowledge_growth_assets": server.knowledge_growth_assets,
    "knowledge_growth_source_triage": server.knowledge_growth_source_triage,
    "knowledge_growth_method": server.knowledge_growth_method,
    "knowledge_growth_output": server.knowledge_growth_output,
    "knowledge_growth_feedback": server.knowledge_growth_feedback,
    "knowledge_growth_failure": server.knowledge_growth_failure,
    "knowledge_growth_summary": server.knowledge_growth_summary,
    "knowledge_growth_lineage": server.knowledge_growth_lineage,
    "knowledge_growth_review": server.knowledge_growth_review,
    "knowledge_growth_schedule": server.knowledge_growth_schedule,
    "knowledge_growth_run": server.knowledge_growth_run,
    "knowledge_growth_distillation": server.knowledge_growth_distillation,
    "knowledge_growth_triage": server.knowledge_growth_triage,
    "knowledge_growth_weekly_distill": server.knowledge_growth_weekly_distill,
    "knowledge_operations_portfolio": server.knowledge_operations_portfolio,
    "knowledge_operations_project": server.knowledge_operations_project,
    "knowledge_operations_graph": server.knowledge_operations_graph,
    "knowledge_information_overview": server.knowledge_information_overview,
    "knowledge_information_receipts": server.knowledge_information_receipts,
    "dbos_create_mission": server.dbos_create_mission,
    "dbos_diagnose_mission": server.dbos_diagnose_mission,
    "dbos_confirm_mission": server.dbos_confirm_mission,
    "dbos_execute_mission": server.dbos_execute_mission,
    "dbos_run_external_worker": server.dbos_run_external_worker,
    "dbos_cancel_external_worker": server.dbos_cancel_external_worker,
    "dbos_review_mission": server.dbos_review_mission,
    "dbos_control_center": server.dbos_control_center,
    "dbos_record_feedback": server.dbos_record_feedback,
    "dbos_record_decision": server.dbos_record_decision,
    "dbos_stop_mission": server.dbos_stop_mission,
    "dbos_rollback_execution": server.dbos_rollback_execution,
    "dbos_mission": server.dbos_mission,
    "dbos_confirm": server.dbos_confirm,
    "dbos_execute": server.dbos_execute,
    "dbos_feedback": server.dbos_feedback,
    "dbos_intake": server.dbos_intake,
    "pbos_cockpit": server.pbos_cockpit,
    "pbos_weekly_report": server.pbos_weekly_report,
    "analyze_domain": server.analyze_domain,
}

_WIKI_READ_TOOLS = {"wiki_guide", "wiki_search", "wiki_graph", "wiki_evidence", "wiki_evidence_record", "wiki_read"}
_WIKI_WRITE_TOOLS = {"wiki_propose_update", "wiki_lint", "wiki_apply_update", "wiki_distill", "wiki_schedule"}
_GROWTH_TOOLS = {
    "knowledge_growth_profile",
    "knowledge_growth_assets",
    "knowledge_growth_source_triage",
    "knowledge_growth_method",
    "knowledge_growth_output",
    "knowledge_growth_feedback",
    "knowledge_growth_failure",
    "knowledge_growth_summary",
    "knowledge_growth_lineage",
    "knowledge_growth_review",
    "knowledge_growth_schedule",
    "knowledge_growth_run",
    "knowledge_growth_distillation",
    "knowledge_growth_triage",
    "knowledge_growth_weekly_distill",
}
_OPERATIONS_TOOLS = {
    "knowledge_operations_portfolio",
    "knowledge_operations_project",
    "knowledge_operations_graph",
}
_INFORMATION_INTELLIGENCE_TOOLS = {
    "knowledge_information_overview",
    "knowledge_information_receipts",
}
_GROWTH_WRITE_ONLY_TOOLS = {
    "knowledge_growth_review",
    "knowledge_growth_triage",
    "knowledge_growth_weekly_distill",
}
_DBOS_TOOLS = {
    "dbos_create_mission",
    "dbos_diagnose_mission",
    "dbos_confirm_mission",
    "dbos_execute_mission",
    "dbos_run_external_worker",
    "dbos_cancel_external_worker",
    "dbos_review_mission",
    "dbos_control_center",
    "dbos_record_feedback",
    "dbos_record_decision",
    "dbos_stop_mission",
    "dbos_rollback_execution",
    "dbos_mission",
    "dbos_confirm",
    "dbos_execute",
    "dbos_feedback",
    "dbos_intake",
    "pbos_cockpit",
    "pbos_weekly_report",
}
_DBOS_WRITE_TOOLS = {
    "dbos_create_mission",
    "dbos_diagnose_mission",
    "dbos_confirm_mission",
    "dbos_execute_mission",
    "dbos_run_external_worker",
    "dbos_cancel_external_worker",
    "dbos_review_mission",
    "dbos_record_feedback",
    "dbos_record_decision",
    "dbos_stop_mission",
    "dbos_rollback_execution",
    "dbos_mission",
    "dbos_confirm",
    "dbos_execute",
    "dbos_feedback",
    "dbos_intake",
    "pbos_weekly_report",
}

_TOOL_SPECS = {
    "bsc_mcp_compatibility_profile": {
        "description": "Return supported BSC MCP transports, auth and isolation capabilities.",
        "properties": {},
    },
    "bsc_compile": {
        "description": "Compile a business description through the BSC runtime.",
        "properties": {
            "description": {"type": "string"},
            "template_id": {"type": "string"},
        },
        "required": ["description"],
    },
    "bsc_generate_sop": {
        "description": "Generate a complete SOP report from a business description.",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
    },
    "knowledge_ask": {
        "description": "Ask the scoped BSC knowledge base.",
        "properties": {
            "question": {"type": "string"},
            "project_id": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["question"],
    },
    "wiki_guide": {
        "description": "Explain the governed project Wiki workflow.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_search": {
        "description": "Search project-scoped Wiki evidence metadata.",
        "properties": {"project_id": {"type": "string"}, "query": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_graph": {
        "description": "Read the project-scoped derived Knowledge Graph.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_read": {
        "description": "Read a published project Wiki page and its citation metadata.",
        "properties": {"project_id": {"type": "string"}, "page_id": {"type": "string"}},
        "required": ["project_id", "page_id"],
    },
    "wiki_propose_update": {
        "description": "Create a reviewable Wiki proposal without writing to the Vault.",
        "properties": {
            "project_id": {"type": "string"},
            "operations": {"type": "array"},
            "source_ids": {"type": "array"},
            "rationale": {"type": "string"},
        },
        "required": ["project_id", "operations"],
    },
    "wiki_lint": {
        "description": "Lint a project Wiki proposal before publication.",
        "properties": {"project_id": {"type": "string"}, "proposal_id": {"type": "string"}},
        "required": ["project_id", "proposal_id"],
    },
    "wiki_apply_update": {
        "description": "Publish a proposal through the Wiki gates.",
        "properties": {"project_id": {"type": "string"}, "proposal_id": {"type": "string"}},
        "required": ["project_id", "proposal_id"],
    },
    "wiki_distill": {
        "description": "Queue a governed weekly evidence distillation.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_schedule": {
        "description": "Configure a bounded persistent Wiki schedule.",
        "properties": {
            "project_id": {"type": "string"},
            "job_type": {"type": "string"},
            "cron": {"type": "string"},
            "timezone": {"type": "string"},
        },
        "required": ["project_id", "job_type", "cron"],
    },
    "knowledge_growth_profile": {
        "description": "Read or update the project knowledge-growth profile with revisioned persistence.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["get", "update"]},
            "profile": {"type": "object"},
            "expected_revision": {"type": "integer", "minimum": 0},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_assets": {
        "description": "List project-scoped A/B/C/D growth assets.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "stage": {"type": "string", "enum": ["", "A", "B", "C", "D", "review"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_source_triage": {
        "description": "Read or run deterministic profile-bound source triage.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["get", "run"]},
            "source_id": {"type": "string", "maxLength": 128},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_method": {
        "description": "List revisions and govern proposal, publication, audited deprecation, and single-variable method-evolution experiments.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "propose", "distill", "review", "publish", "resolve", "revisions", "deprecate", "experiments", "experiment", "evolve"]},
            "method_id": {"type": "string", "maxLength": 128},
            "proposal_id": {"type": "string", "maxLength": 128},
            "status": {"type": "string", "maxLength": 32},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {
                "type": "object",
                "description": "Action payload; distill requires source_id and creates review-only proposals; evolve requires candidate_body, candidate_manifest, supporting_output_ids, mutation_dimension, rationale and idempotency_key, and never publishes automatically; experiment requires experiment_id; deprecate requires a non-blank reason of at most 500 characters.",
            },
        },
        "required": ["project_id"],
    },
    "knowledge_growth_output": {
        "description": "List, read, register, evaluate or file immutable project outputs.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "register", "evaluate", "file"]},
            "output_id": {"type": "string", "maxLength": 128},
            "status": {"type": "string", "maxLength": 32},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {
                "type": "object",
                "description": "Action payload; file requires a non-blank reason of at most 500 characters.",
            },
        },
        "required": ["project_id"],
    },
    "knowledge_growth_feedback": {
        "description": "List, create or process project output feedback through governed routing.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "create", "process"]},
            "feedback_id": {"type": "string", "maxLength": 128},
            "output_id": {"type": "string", "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {"type": "object"},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_failure": {
        "description": "List, record, or resolve project-scoped knowledge failure diagnostics linked to durable run evidence.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "create", "resolve"]},
            "failure_id": {"type": "string", "maxLength": 128},
            "status": {"type": "string", "enum": ["", "open", "retry_scheduled", "resolved"]},
            "run_id": {"type": "string", "maxLength": 128},
            "diagnostic_pattern": {"type": "string", "enum": ["", "P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08", "P09", "P10", "P11", "P12"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {
                "type": "object",
                "description": "Create requires code and summary; it may declare a P01-P12 primary diagnosis, up to two secondary diagnoses, and a minimal structural fix. Resolve requires a non-blank resolution_note; source bodies must not be included.",
            },
        },
        "required": ["project_id"],
    },
    "knowledge_growth_summary": {
        "description": "Read persisted knowledge-growth counts and quality flow summary.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "knowledge_growth_lineage": {
        "description": "Read bounded project-scoped source/page/method/output lineage.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "relation": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_review": {
        "description": "Route feedback or detect method proposals without direct publication.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["feedback", "method_detection"]},
            "target_id": {"type": "string", "maxLength": 128},
            "minimum_uses": {"type": "integer", "minimum": 3, "maximum": 100},
        },
        "required": ["project_id", "action"],
    },
    "knowledge_growth_schedule": {
        "description": "List or configure bounded persistent growth schedules.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "create"]},
            "job_type": {"type": "string", "enum": ["", "growth_daily", "growth_weekly_distillation"]},
            "cron": {"type": "string", "maxLength": 100},
            "timezone": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_run": {
        "description": "List, start, read or replay durable growth runs.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "start", "get", "events"]},
            "run_id": {"type": "string", "maxLength": 128},
            "job_type": {"type": "string", "enum": ["", "growth_daily", "growth_weekly_distillation"]},
            "idempotency_key": {"type": "string", "maxLength": 200},
            "after_sequence": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {"type": "object"},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_distillation": {
        "description": "List, read or start a durable weekly growth distillation.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "start"]},
            "distillation_id": {"type": "string", "maxLength": 128},
            "kind": {"type": "string", "enum": ["", "daily", "weekly"]},
            "week": {"type": "string", "maxLength": 32},
            "source_cutoff": {"type": "string", "maxLength": 64},
            "idempotency_key": {"type": "string", "maxLength": 200},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_triage": {
        "description": "Run profile-bound triage for one validated source.",
        "properties": {"project_id": {"type": "string"}, "source_id": {"type": "string"}},
        "required": ["project_id", "source_id"],
    },
    "knowledge_growth_weekly_distill": {
        "description": "Run an idempotent project weekly distillation.",
        "properties": {"project_id": {"type": "string"}, "week": {"type": "string"}, "source_cutoff": {"type": "string"}},
        "required": ["project_id", "week", "source_cutoff"],
    },
    "knowledge_operations_portfolio": {
        "description": "Read tenant-admin knowledge operations metrics and action queue.",
        "properties": {},
    },
    "knowledge_operations_project": {
        "description": "Read one authorized project's knowledge operations cockpit.",
        "properties": {"project_id": {"type": "string", "minLength": 1, "maxLength": 128}},
        "required": ["project_id"],
    },
    "knowledge_information_overview": {
        "description": "Read an authorized project's source registry, BSC receipts, and honest information-intake counts.",
        "properties": {"project_id": {"type": "string", "minLength": 1, "maxLength": 128}},
        "required": ["project_id"],
    },
    "knowledge_information_receipts": {
        "description": "Read bounded, authorized BSC signal receipts without source or derivative bodies.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
    "wiki_evidence": {
        "description": "Read bounded, project-scoped evidence lineage with redacted metadata only.",
        "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
        "required": ["project_id"],
    },
    "wiki_evidence_record": {
        "description": "Read one project-scoped evidence record without its source or derivative body.",
        "properties": {"project_id": {"type": "string"}, "record_type": {"type": "string", "enum": ["source", "asset", "extraction", "table", "reference"]}, "record_id": {"type": "string"}},
        "required": ["project_id", "record_type", "record_id"],
    },
    "knowledge_operations_graph": {
        "description": "Read a bounded lifecycle graph projection for one authorized project.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 512},
        },
        "required": ["project_id"],
    },
    "dbos_create_mission": {
        "description": "Create a project-scoped DBOS mission that requires review before execution.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "title": {"type": "string", "minLength": 1, "maxLength": 300},
            "intent": {"type": "string", "minLength": 1, "maxLength": 20000},
            "intake_mode": {"type": "string", "enum": ["business", "career"]},
            "context": {"type": "object"},
        },
        "required": ["project_id", "title", "intent"],
    },
    "dbos_diagnose_mission": {
        "description": "Create the reviewable diagnosis, capability selection, and Dynamic SOP for a mission.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "required": ["project_id", "mission_id"],
    },
    "dbos_confirm_mission": {
        "description": "Confirm a selected subset of a reviewed mission's capabilities.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "actor_id": {"type": "string", "minLength": 1, "maxLength": 256},
            "authorized_capabilities": {"type": "array"},
        },
        "required": ["project_id", "mission_id", "actor_id", "authorized_capabilities"],
    },
    "dbos_execute_mission": {
        "description": "Execute one confirmed DBOS capability with an idempotency key.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "capability_name": {"type": "string", "minLength": 1, "maxLength": 128},
            "idempotency_key": {"type": "string", "maxLength": 256},
        },
        "required": ["project_id", "mission_id", "capability_name"],
    },
    "dbos_run_external_worker": {
        "description": "Queue one non-production allowlisted HTTPS worker through the mission policy gate. Credentials are server-side references only.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "dynamic_sop_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "capability_name": {"type": "string", "minLength": 1, "maxLength": 128},
            "worker_id": {"type": "string", "minLength": 1, "maxLength": 100},
            "model_id": {"type": "string", "minLength": 1, "maxLength": 100},
            "endpoint": {"type": "string", "minLength": 1, "maxLength": 2000},
            "payload": {"type": "object"},
            "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
            "estimated_cost_microusd": {"type": "integer", "minimum": 0},
        },
        "required": ["project_id", "mission_id", "dynamic_sop_id", "capability_name", "worker_id", "model_id", "endpoint", "payload", "idempotency_key"],
    },
    "dbos_cancel_external_worker": {
        "description": "Request cancellation of a queued or executing external worker. Cancellation is completed only after transport acknowledgement.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "worker_run_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["project_id", "worker_run_id", "reason"],
    },
    "dbos_review_mission": {
        "description": "Run a metered PromptOps Advisor review for a compiled mission. The review can only recommend; it cannot authorize or execute work.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
        },
        "required": ["project_id", "mission_id", "idempotency_key"],
    },
    "dbos_control_center": {
        "description": "Read the project-scoped DBOS mission ledger, lineage, and execution health.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "required": ["project_id", "mission_id"],
    },
    "pbos_cockpit": {
        "description": "Read the evidence-backed Personal Growth Cockpit for one project.",
        "properties": {"project_id": {"type": "string", "minLength": 1, "maxLength": 128}},
        "required": ["project_id"],
    },
    "pbos_weekly_report": {
        "description": "Write an evidence-only PBOS weekly review into the configured Obsidian Vault.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "week": {"type": "string", "pattern": "^$|^\\d{4}-W\\d{2}$"},
        },
        "required": ["project_id"],
    },
    "dbos_record_feedback": {
        "description": "Record an execution-linked DBOS feedback memory candidate.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "statement": {"type": "string", "minLength": 1, "maxLength": 20000},
            "source_refs": {"type": "array"},
        },
        "required": ["project_id", "mission_id", "statement"],
    },
    "dbos_record_decision": {
        "description": "Record a reviewer decision against a Dynamic SOP task without executing it.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "statement": {"type": "string", "minLength": 1, "maxLength": 4000},
            "rationale": {"type": "string", "maxLength": 20000},
            "alternatives": {"type": "array"},
            "actor_id": {"type": "string", "maxLength": 200},
        },
        "required": ["project_id", "mission_id", "task_id", "statement"],
    },
    "dbos_stop_mission": {
        "description": "Stop a non-terminal DBOS mission and persist the reviewer reason.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["project_id", "mission_id", "reason"],
    },
    "dbos_rollback_execution": {
        "description": "Record a reviewer rollback for an eligible DBOS execution.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "execution_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["project_id", "execution_id", "reason"],
    },
    "dbos_mission": {
        "description": "Create, diagnose, or read a project-scoped Dynamic Business OS mission.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["create", "diagnose", "read", "control_center"]},
            "mission_id": {"type": "string", "maxLength": 128},
            "payload": {"type": "object"},
        },
        "required": ["project_id"],
    },
    "dbos_confirm": {
        "description": "Confirm selected capabilities before a DBOS mission may execute.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "authorized_capabilities": {"type": "array"},
            "actor_id": {"type": "string", "maxLength": 256},
        },
        "required": ["project_id", "mission_id", "authorized_capabilities"],
    },
    "dbos_execute": {
        "description": "Execute one confirmed DBOS capability with a durable idempotency key.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "capability_name": {"type": "string", "minLength": 1, "maxLength": 128},
            "idempotency_key": {"type": "string", "maxLength": 256},
        },
        "required": ["project_id", "mission_id", "capability_name"],
    },
    "dbos_feedback": {
        "description": "Record outcome-linked feedback as an advisory DBOS memory candidate.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "mission_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "statement": {"type": "string", "minLength": 1, "maxLength": 20000},
            "source_refs": {"type": "array"},
        },
        "required": ["project_id", "mission_id", "statement"],
    },
    "dbos_intake": {
        "description": "Create or govern a bounded Blindspot Intake. Conversion creates a review-gated Mission; it never executes work.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["create", "get", "resolve_uncertain", "next_question", "answer", "revert", "list_revisions", "direct_to_review", "select_tier", "convert", "recommend", "export_handoff"]},
            "session_id": {"type": "string", "maxLength": 128},
            "payload": {"type": "object"},
        },
        "required": ["project_id", "action"],
    },
    "analyze_domain": {
        "description": "Classify a business text into a domain.",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


@router.post("")
async def mcp_json_rpc(request: Request):
    api_key = _request_api_key(request)
    payload = await request.json()
    response = await _dispatch(payload, api_key=api_key)
    if response is None:
        return JSONResponse(status_code=202, content={})
    return JSONResponse(response)


@router.get("/compatibility")
async def mcp_compatibility(request: Request):
    api_key = _request_api_key(request)
    _require_http_auth(api_key)
    configured = bool(server._MCP_API_KEY or server._get_settings_api_key())
    return build_compatibility_profile(api_key_configured=configured).model_dump()


@router.get("/sse")
async def mcp_sse(request: Request):
    api_key = _request_api_key(request)
    _require_http_auth(api_key)
    session_id = uuid.uuid4().hex
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _sse_sessions[session_id] = queue

    async def events():
        endpoint = f"/api/mcp/messages/{session_id}"
        yield f"event: endpoint\ndata: {endpoint}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
        finally:
            _sse_sessions.pop(session_id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{session_id}")
async def mcp_sse_message(session_id: str, request: Request):
    api_key = _request_api_key(request)
    _require_http_auth(api_key)
    queue = _sse_sessions.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="MCP SSE session not found")
    response = await _dispatch(await request.json(), api_key=api_key)
    if response is not None:
        await queue.put(response)
    return JSONResponse(status_code=202, content={})


async def _dispatch(payload: Any, *, api_key: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return _error(None, -32600, "JSON-RPC request must be an object")
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    if not isinstance(method, str):
        return _error(request_id, -32600, "JSON-RPC method is required")
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "initialize":
        return _success(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "bsc-engine", "version": "5.0.0"},
            },
        )
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(request_id, {"tools": _tool_list()})
    if method == "tools/call":
        return await _call_tool(request_id, params, api_key=api_key)
    return _error(request_id, -32601, f"Method not found: {method}")


async def _call_tool(request_id: Any, params: Any, *, api_key: str) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _error(request_id, -32602, "tools/call params must be an object")
    name = params.get("name")
    if name not in _TOOL_HANDLERS:
        return _error(request_id, -32602, f"Unknown MCP tool: {name}")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "tools/call arguments must be an object")
    arguments = dict(arguments)
    argument_error = _validate_tool_arguments(name, arguments)
    if argument_error:
        return _error(request_id, -32602, argument_error)
    arguments["api_key"] = api_key
    try:
        handler = _TOOL_HANDLERS[name]
        if inspect.iscoroutinefunction(handler):
            result = await handler(**arguments)
        else:
            result = await asyncio.to_thread(handler, **arguments)
        return _success(request_id, _wire_result(normalize_mcp_result(result)))
    except server.growth_tools.GrowthUnavailableError as exc:
        return _error(
            request_id,
            -32003,
            str(exc),
            data={"code": "dependency_unavailable", "availability": exc.availability},
        )
    except PermissionError as exc:
        return _error(request_id, -32001, str(exc), data={"code": "permission_denied"})
    except KeyError as exc:
        return _error(request_id, -32004, str(exc), data={"code": "resource_not_found"})
    except server.growth_tools.GrowthStateConflictError as exc:
        return _error(
            request_id,
            -32009,
            str(exc),
            data={"code": "knowledge_conflict"},
        )
    except server.dbos_tools.ExternalWorkerPolicyError as exc:
        return _error(request_id, -32009, str(exc), data={"code": "policy_denied"})
    except ValueError as exc:
        message = str(exc)
        normalized = message.lower()
        if "conflict" in normalized or "revision" in normalized:
            return _error(request_id, -32009, message, data={"code": "knowledge_conflict"})
        if "not found" in normalized:
            return _error(request_id, -32004, message, data={"code": "resource_not_found"})
        if "unavailable" in normalized or "not configured" in normalized:
            return _error(request_id, -32003, message, data={"code": "dependency_unavailable"})
        return _error(request_id, -32602, message, data={"code": "invalid_arguments"})
    except Exception as exc:
        return _error(request_id, -32000, "MCP tool execution failed", data={"code": "internal_tool_error"})


def _tool_list() -> list[dict[str, Any]]:
    from app.core.config import settings

    enabled_names = set(_TOOL_SPECS)
    if not settings.KNOWLEDGE_WIKI_ENABLED:
        enabled_names -= _WIKI_READ_TOOLS | _WIKI_WRITE_TOOLS
    elif not settings.KNOWLEDGE_MCP_WRITE_ENABLED:
        enabled_names -= _WIKI_WRITE_TOOLS
    if not settings.KNOWLEDGE_GROWTH_ENABLED:
        enabled_names -= _GROWTH_TOOLS
    elif not settings.KNOWLEDGE_MCP_WRITE_ENABLED:
        enabled_names -= _GROWTH_WRITE_ONLY_TOOLS
    if not settings.KNOWLEDGE_INTELLIGENCE_ENABLED:
        enabled_names -= _INFORMATION_INTELLIGENCE_TOOLS
    if not settings.DYNAMIC_BUSINESS_OS_ENABLED:
        enabled_names -= _DBOS_TOOLS
    elif not settings.DBOS_BLINDSPOT_INTAKE_ENABLED:
        enabled_names.discard("dbos_intake")
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": {
                "type": "object",
                "properties": spec.get("properties", {}),
                "required": spec.get("required", []),
                "additionalProperties": False,
            },
        }
        for name, spec in _TOOL_SPECS.items()
        if name in enabled_names
    ]


def _validate_tool_arguments(name: str, arguments: dict[str, Any]) -> str | None:
    """Apply the advertised MCP tool contract before entering a handler."""
    spec = _TOOL_SPECS[name]
    properties = spec.get("properties", {})
    unexpected = sorted(set(arguments) - set(properties))
    if unexpected:
        return f"Unexpected arguments for {name}: {', '.join(unexpected)}"

    missing = [key for key in spec.get("required", []) if key not in arguments]
    if missing:
        return f"Missing required arguments for {name}: {', '.join(missing)}"

    for key, value in arguments.items():
        schema = properties[key]
        expected_type = schema.get("type")
        if expected_type == "string" and not isinstance(value, str):
            return f"Argument {key} for {name} must be a string"
        if expected_type == "string" and isinstance(value, str):
            if schema.get("minLength") is not None and len(value) < schema["minLength"]:
                return f"Argument {key} for {name} is shorter than {schema['minLength']} characters"
            if schema.get("maxLength") is not None and len(value) > schema["maxLength"]:
                return f"Argument {key} for {name} is longer than {schema['maxLength']} characters"
            if schema.get("enum") is not None and value not in schema["enum"]:
                return f"Argument {key} for {name} must be one of: {', '.join(schema['enum'])}"
        if expected_type == "array" and not isinstance(value, list):
            return f"Argument {key} for {name} must be an array"
        if expected_type == "object" and not isinstance(value, dict):
            return f"Argument {key} for {name} must be an object"
        if expected_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"Argument {key} for {name} must be an integer"
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                return f"Argument {key} for {name} must be at least {minimum}"
            if maximum is not None and value > maximum:
                return f"Argument {key} for {name} must be at most {maximum}"
    return None


def _wire_result(result) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for block in result.content:
        if block.type == "text":
            content.append({"type": "text", "text": block.text})
        elif block.type == "image":
            content.append({
                "type": "image",
                "data": block.data,
                "mimeType": block.mime_type,
            })
        elif block.type == "resource":
            content.append({
                "type": "resource",
                "resource": {
                    "uri": block.uri,
                    "name": block.name,
                    "mimeType": block.mime_type,
                    "text": block.text,
                    "blob": block.data,
                },
            })
        else:
            content.append({
                "type": "text",
                "text": block.message,
                "annotations": {"error_code": block.error_code},
            })
    payload: dict[str, Any] = {"content": content, "isError": result.is_error}
    if result.structured_content is not None:
        payload["structuredContent"] = result.structured_content
    return payload


def _request_api_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("x-api-key", "") or str(
        getattr(request.state, "signed_api_key", "")
    )


def _require_http_auth(api_key: str) -> None:
    try:
        server._require_mcp_auth(api_key)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _success(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload
