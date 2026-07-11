from __future__ import annotations
import json, time, uuid
from typing import Any, Dict, Optional
from app.db import get_db


class ProjectDraft:
    def __init__(self, session_id: str = None, idea: str = "", requirements: str = "",
                 domain: Optional[dict] = None, business_system: Optional[dict] = None,
                 sop: Optional[dict] = None, status: str = "idea",
                 messages: Optional[list] = None, updated_at: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.idea = idea
        self.requirements = requirements
        self.domain = domain or {}
        self.business_system = business_system or {}
        self.sop = sop or {}
        self.status = status
        self.messages = messages or []
        self.updated_at = updated_at or time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id, "idea": self.idea, "requirements": self.requirements,
            "domain": self.domain, "business_system": self.business_system, "sop": self.sop,
            "status": self.status, "messages": self.messages, "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row):
        d = dict(row)
        d["domain"] = json.loads(d["domain"]) if isinstance(d.get("domain"), str) else (d.get("domain") or {})
        d["business_system"] = json.loads(d["business_system"]) if isinstance(d.get("business_system"), str) else (d.get("business_system") or {})
        d["sop"] = json.loads(d["sop"]) if isinstance(d.get("sop"), str) else (d.get("sop") or {})
        d["messages"] = json.loads(d["messages"]) if isinstance(d.get("messages"), str) else (d.get("messages") or [])
        return cls(**d)


class ProjectDraftRepository:
    def __init__(self):
        self._db = get_db()
        self._ensure_table()

    def _ensure_table(self):
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS agent_project_drafts (
                session_id TEXT PRIMARY KEY,
                idea TEXT, requirements TEXT, domain TEXT,
                business_system TEXT, sop TEXT, status TEXT,
                messages TEXT, updated_at TEXT
            )"""
        )
        self._db.commit()

    def save(self, draft: ProjectDraft):
        draft.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._db.execute(
            """INSERT INTO agent_project_drafts
               (session_id, idea, requirements, domain, business_system, sop, status, messages, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
               idea=excluded.idea, requirements=excluded.requirements, domain=excluded.domain,
               business_system=excluded.business_system, sop=excluded.sop, status=excluded.status,
               messages=excluded.messages, updated_at=excluded.updated_at""",
            (draft.session_id, draft.idea, draft.requirements, json.dumps(draft.domain, ensure_ascii=False),
             json.dumps(draft.business_system, ensure_ascii=False), json.dumps(draft.sop, ensure_ascii=False),
             draft.status, json.dumps(draft.messages, ensure_ascii=False), draft.updated_at))
        self._db.commit()

    def get(self, session_id: str) -> Optional[ProjectDraft]:
        row = self._db.execute("SELECT * FROM agent_project_drafts WHERE session_id=?", (session_id,)).fetchone()
        return ProjectDraft.from_row(row) if row else None

    def patch(self, session_id: str, path: str, value: Any):
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        # 仅支持 business_system.<key> 一级打补丁（MVP 范围）
        if not path.startswith("business_system."):
            raise ValueError(f"只允许补丁 business_system.* ，收到: {path}")
        key = path.split(".", 1)[1]
        draft.business_system[key] = value
        draft.status = "edited"
        self.save(draft)
        return draft
