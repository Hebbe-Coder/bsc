from app.constraint.audit import AuditChain


def test_chain_hashes_and_verifies():
    c = AuditChain()
    c.append("risk", "coverage", {"input": {"x": 1}, "output": {"pct": 100}})
    c.append("risk", "gate", {"input": {"pct": 100}, "output": {"decision": "pass"}})
    assert len(c.entries) == 2
    assert c.verify() is True


def test_tamper_detection():
    c = AuditChain()
    c.append("risk", "coverage", {"input": {"x": 1}, "output": {"pct": 100}})
    # 篡改某条记录的 output，不改 hash
    c.entries[0].output_hash = "deadbeef"
    assert c.verify() is False
