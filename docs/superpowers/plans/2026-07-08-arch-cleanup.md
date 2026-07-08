# Architecture Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining low-risk architecture debt from bsc-backend so the repo is clean, while keeping the test suite green (62 passed / 2 skipped) and the real-LLM path untouched.

**Architecture:** Risk-sequenced, one commit per item. Every change is a pure deletion / move / doc-fix with **no behavior change**. Each task is verified by running the full `pytest` suite (expect `62 passed, 2 skipped`) plus a reference `grep` to confirm zero residual references. The design/spec this plan implements: `docs/superpowers/specs/2026-07-08-arch-cleanup-design.md`.

**Tech Stack:** Git, Python 3.13, pytest (run via `.venv/Scripts/python.exe -m pytest`), existing FastAPI bsc-backend project. All commands assume the working directory is the project root `C:/Users/34216/Documents/New project 3/bsc-backend`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `validators/`, `compilers/`, `prompt_library/` | Move → `archive/` | Orphan directories with zero references anywhere in `app/`. Archiving (not deleting) preserves history and is reversible. |
| `test_comprehensive.py` | Delete (root) | Stray debug script from an earlier session; not part of the `tests/` suite. Untracked, so removal needs no commit. |
| `pytest.ini` | Modify | Remove the `asyncio_mode = auto` line (pytest-asyncio not installed; no async tests) to silence the `PytestConfigWarning`. |
| `app/schemas/production_schema.py` | Modify (comment only) | Fix the module docstring that references the already-deleted `business_schema.py` / `BusinessSystemSchema`. |
| `k8s/deployment.yaml`, `k8s/service.yaml` | Inspect (optional) | Verify container/target port matches the app (`8000`). Edit only if stale. |

All other files (`app/`, exporters, `.env`, routing logic) are intentionally **not** touched — the real-LLM path and the 6-format exporters must keep working unchanged.

---

## Task 1: Archive the three orphan directories

**Files:**
- Move: `validators/` → `archive/validators/`
- Move: `compilers/` → `archive/compilers/`
- Move: `prompt_library/` → `archive/prompt_library/`

- [ ] **Step 1: Move the directories into `archive/` with git**

```bash
git mv validators compilers prompt_library archive/
```

Expected: the three directories now live under `archive/` (`archive/validators`, `archive/compilers`, `archive/prompt_library`); `git status` shows them as renamed.

- [ ] **Step 2: Confirm zero residual references in `app/`**

```bash
grep -rln "validators\.\|compilers\.\|prompt_library\." app --include=*.py
```

Expected: **no output** (empty). If anything prints, stop and investigate before committing.

- [ ] **Step 3: Run the full test suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: `62 passed, 2 skipped`. (The 2 skipped are the opt-in real-LLM `test_real_e2e.py` tests, which require `BSC_REAL_E2E=1` + real keys.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: archive orphan dirs validators/compilers/prompt_library

Zero references from app/ (confirmed via grep). Pure move, no behavior change."
```

---

## Task 2: Delete the stray root debug script

**Files:**
- Delete: `test_comprehensive.py` (project root, untracked)

- [ ] **Step 1: Remove the file**

```bash
rm test_comprehensive.py
```

Expected: the file is gone. Confirm with `ls test_comprehensive.py` → `No such file or directory`.

- [ ] **Step 2: Confirm it was never tracked and pytest is unaffected**

```bash
git status --short test_comprehensive.py
.venv/Scripts/python.exe -m pytest -q
```

Expected: `git status` shows **nothing** for that path (it was untracked, so there is nothing to commit); pytest still reports `62 passed, 2 skipped`.

- [ ] **Step 3: (No commit required)** — because the file was untracked, deletion removes it from disk only. Skip committing. Note this in the PR/changelog if one is kept.

---

## Task 3: Drop the unused `asyncio_mode` from pytest.ini

**Files:**
- Modify: `pytest.ini` (remove line 4, `asyncio_mode = auto`)

Current `pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
asyncio_mode = auto
addopts = -v --tb=short
```

- [ ] **Step 1: Edit `pytest.ini` — delete the `asyncio_mode = auto` line**

Resulting file:
```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -v --tb=short
```

- [ ] **Step 2: Run pytest and confirm the config warning is gone**

```bash
.venv/Scripts/python.exe -m pytest -q 2>&1 | grep -i "asyncio_mode\|PytestConfigWarning"
```

Expected: **no output** (the warning line is gone). Also confirm the suite still ends with `62 passed, 2 skipped`.

- [ ] **Step 3: Commit**

```bash
git add pytest.ini
git commit -m "chore: remove unused asyncio_mode from pytest.ini

No async tests exist and pytest-asyncio is not installed; the option
only produced a PytestConfigWarning."
```

---

## Task 4: Fix the stale comment in production_schema.py

**Files:**
- Modify: `app/schemas/production_schema.py` (module docstring, lines 1–9)

Current docstring (stale — references the deleted `business_schema.py`):
```python
"""
生产路径数据模型 — 匹配 bsc_pipeline / async_pipeline 真实产出。

与 business_schema.py 中的 BusinessSystemSchema 不同，这个模型
完全基于 LLM Agent 的实际 JSON 输出结构定义，所有字段可选，
校验失败时降级而非报错，保证生产可用性。
"""
```

- [ ] **Step 1: Replace the docstring with an accurate one**

```python
"""
生产路径数据模型 — 匹配 bsc_pipeline / async_pipeline 真实产出。

ProductionBusinessSystem 是当前唯一 canonical 业务系统模型，完全基于
LLM Agent 的实际 JSON 输出结构定义，所有字段可选；校验由
validate_business_system() 在 compile_to_business_system() 中执行，
失败时降级而非报错，保证生产可用性。
"""
```

- [ ] **Step 2: Run the test suite to confirm no behavior change**

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: `62 passed, 2 skipped`. (This is a comment-only change; any failure means an accidental edit — revert and re-check.)

- [ ] **Step 3: Commit**

```bash
git add app/schemas/production_schema.py
git commit -m "docs: correct stale comment in production_schema.py

business_schema.py / BusinessSystemSchema no longer exist;
ProductionBusinessSystem is now the sole canonical model."
```

---

## Task 5 (optional): Verify k8s port alignment

**Files:**
- Inspect: `k8s/deployment.yaml`, `k8s/service.yaml`

- [ ] **Step 1: Inspect the exposed ports and image**

```bash
grep -nE "image:|containerPort:|targetPort:|port:" k8s/deployment.yaml k8s/service.yaml
```

Expected: find the container image and the port the service forwards. The app listens on `8000` (`APP_PORT=8000`, uvicorn), so `containerPort` / `targetPort` / `port` should be `8000`.

- [ ] **Step 2: Decide**

- If the ports already read `8000` and the image matches the project's `Dockerfile` → **nothing to change**, note "k8s verified current" in the changelog.
- If a port differs (e.g., `80`/`8080`) or the image tag is stale → edit the YAML so `containerPort`/`targetPort` = `8000` and the image points at the current build, then:

```bash
git add k8s/deployment.yaml k8s/service.yaml
git commit -m "chore: align k8s port/image with app (listen on 8000)"
```

Expected after any edit: `pytest` still `62 passed, 2 skipped` (k8s changes don't affect tests).

---

## Verification summary (every task)

After each task the full suite must read `62 passed, 2 skipped`:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Optional real-LLM happy-path smoke (only if `BSC_REAL_E2E=1` and both keys are real — they are not locally, so it stays skipped):

```bash
BSC_REAL_E2E=1 .venv/Scripts/python.exe -m pytest tests/test_real_e2e.py -v
```

## Self-review notes
- **Spec coverage:** Task 1 = spec §3.1; Task 2 = §3.2; Task 3 = §3.3; Task 4 = §3.4; Task 5 = §3.5. All five spec items have a task. The "already done" items (archive/dead_code, archive/orphan_fork, single k8s, ProductionBusinessSystem unification) are intentionally absent — confirmed completed before planning.
- **No placeholders:** every edit shows the exact before/after file content or the exact command + expected output.
- **Type/name consistency:** no cross-task function/class names; tasks are independent file operations, so no signature drift is possible.
