# app/agent/state.py
from __future__ import annotations
import json, time, uuid
from typing import Any, Dict, Optional
from app.db import get_db

SEGMENTS = ("project", "requirements", "business_model", "sop", "review", "presentation")


class ProjectDraft:
    def __init__(self, session_id: str = None, idea: str = "",
                 project: Optional[dict] = None, requirements: Optional[list] = None,
                 business_model: Optional[dict] = None, sop: Optional[dict] = None,
                 review: Optional[dict] = None, presentation: Optional[dict] = None,
                 status: str = "planned", messages: Optional[list] = None,
                 updated_at: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.idea = idea
        self.project = project or {}
        self.requirements = requirements or []
        self.business_model = business_model or {}
        self.sop = sop or {}
        self.review = review or {}
        self.presentation = presentation or {}
        self.status = status
        self.messages = messages or []
        self.updated_at = updated_at or time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id, "idea": self.idea,
            "project": self.project, "requirements": self.requirements,
            "business_model": self.business_model, "sop": self.sop,
            "review": self.review, "presentation": self.presentation,
            "status": self.status, "messages": self.messages, "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row):
        d = dict(row)
        for seg in SEGMENTS:
            v = d.get(seg)
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    v = [] if seg == "requirements" else {}
            d[seg] = v or ([] if seg == "requirements" else {})
        d["messages"] = json.loads(d["messages"]) if isinstance(d.get("messages"), str) else (d.get("messages") or [])
        return cls(**d)


class ProjectDraftRepository:
    def __init__(self):
        self._db = get_db()
        self._ensure_table()

    def _ensure_table(self):
        expected_cols = {"session_id", "idea", "project", "requirements", "business_model",
                         "sop", "review", "presentation", "status", "messages", "updated_at"}
        cur = self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_project_drafts'"
        ).fetchone()
        needs_recreate = False
        if cur is None:
            needs_recreate = True
        else:
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(agent_project_drafts)").fetchall()}
            if cols != expected_cols:
                needs_recreate = True
        if needs_recreate:
            self._db.execute("DROP TABLE IF EXISTS agent_project_drafts")
            self._db.execute(
                """CREATE TABLE agent_project_drafts (
                    session_id TEXT PRIMARY KEY, idea TEXT, project TEXT, requirements TEXT,
                    business_model TEXT, sop TEXT, review TEXT, presentation TEXT,
                    status TEXT, messages TEXT, updated_at TEXT
                )"""
            )
            self._db.commit()

    def save(self, draft: ProjectDraft):
        draft.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._db.execute(
            """INSERT INTO agent_project_drafts
               (session_id, idea, project, requirements, business_model, sop, review, presentation, status, messages, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
               idea=excluded.idea, project=excluded.project, requirements=excluded.requirements,
               business_model=excluded.business_model, sop=excluded.sop, review=excluded.review,
               presentation=excluded.presentation, status=excluded.status, messages=excluded.messages,
               updated_at=excluded.updated_at""",
            (draft.session_id, draft.idea,
             json.dumps(draft.project, ensure_ascii=False),
             json.dumps(draft.requirements, ensure_ascii=False),
             json.dumps(draft.business_model, ensure_ascii=False),
             json.dumps(draft.sop, ensure_ascii=False),
             json.dumps(draft.review, ensure_ascii=False),
             json.dumps(draft.presentation, ensure_ascii=False),
             draft.status, json.dumps(draft.messages, ensure_ascii=False), draft.updated_at))
        self._db.commit()

    def get(self, session_id: str):
        row = self._db.execute("SELECT * FROM agent_project_drafts WHERE session_id=?", (session_id,)).fetchone()
        return ProjectDraft.from_row(row) if row else None

    def patch(self, session_id: str, segment: str, value: Any):
        if segment not in SEGMENTS:
            raise ValueError(f"未知状态段: {segment}")
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        setattr(draft, segment, value)
        draft.status = f"edited:{segment}"
        self.save(draft)
        return draft
