from __future__ import annotations
import hashlib
import json
import time
from app.constraint.models import AuditEntry

GENESIS = "0" * 64


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _stable(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


class AuditChain:
    def __init__(self):
        self.entries: list[AuditEntry] = []
        self._prev = GENESIS

    def append(self, agent: str, action: str, payload: dict) -> AuditEntry:
        seq = len(self.entries)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        inp = _sha256(_stable(payload.get("input", {})))
        out = _sha256(_stable(payload.get("output", {})))
        raw = f"{seq}|{ts}|{agent}|{action}|{inp}|{out}|{self._prev}"
        h = _sha256(raw)
        entry = AuditEntry(seq=seq, agent=agent, action=action,
                           input_hash=inp, output_hash=out,
                           hash=h, prev_hash=self._prev, timestamp=ts)
        self.entries.append(entry)
        self._prev = h
        return entry

    def verify(self) -> bool:
        prev = GENESIS
        for e in self.entries:
            raw = f"{e.seq}|{e.timestamp}|{e.agent}|{e.action}|{e.input_hash}|{e.output_hash}|{prev}"
            if _sha256(raw) != e.hash:
                return False
            prev = e.hash
        return True
