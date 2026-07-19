---
name: bsc-safe-merge
description: Use this skill before merging any feature branch into master in the bsc-backend repo. The working tree contains ~256 unrelated dirty files the user is actively editing, master must never be touched without explicit authorization, and a single wrong `git checkout`/`git add -A` can nuke the user's in-progress work. This skill enforces the verified safety protocol (merge-base + dirty-tree overlap check + --no-ff) and the repo-specific traps (venv pytest, explicit router registration in dirty main.py, autocrlf, subagent silent-failure).
agent_created: true
---

# bsc-backend: Safe Merge Around a Dirty Working Tree

## When to use
- About to `git merge` / `git checkout master` / `git branch -d` in this repo.
- Any operation that could touch the user's ~256 unrelated dirty files.
- Never act on master without the user's explicit "合并" / "merge" authorization.

## Hard rules (non-negotiable)
1. **Never `git add -A` / `git commit -a`** — only stage your own files by explicit path.
2. **Never edit `app/main.py`** — router is an explicit list at `app/main.py:216`; new API routes attach to a CLEAN already-registered module (`app/api/orchestrate.py`), not main.py.
3. **pytest MUST use the venv interpreter**: `./venv/Scripts/python.exe -m pytest ...` (global `python` lacks numpy → collection fails).
4. **Don't touch these dirty files**: `app/main.py`, `src/api/orchestrateApi.ts`, `src/components/Workspace.tsx`. Safe to edit: `src/App.tsx`, `src/store/workspaceStore.ts` (clean).
5. **Long subagent tasks may silently return empty** — always `ls`/verify the expected files + commit exist before marking the task done.

## Safety protocol (run BEFORE checkout/merge)
On your feature branch, run all of these; only proceed if every check is green:

```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend"
echo "BRANCH: $(git branch --show-current)"
echo "MASTER..FEAT: $(git rev-list --count master..HEAD)"   # expect >0
echo "FEAT..MASTER: $(git rev-list --count HEAD..master)"   # expect 0
# merge-base must equal master (fast-forward-able base, master fully behind)
test "$(git merge-base master HEAD)" = "$(git rev-parse master)" && echo "BASE_OK" || echo "BASE_MISMATCH"
# CRITICAL: feature files must NOT overlap the dirty tree
comm -12 <(git diff --name-only master...HEAD | sort) \
        <(git status --short | awk '{print $2}' | sort)
# -> must print NOTHING (OVERLAP_COUNT=0). If non-empty, see "Overlap rescue" below.
echo "DIRTY_TOTAL: $(git status --short | wc -l)"
```

## Merge
```bash
git checkout master            # safe only because overlap=0; touches only your feature files
git merge --no-ff <branch> -m "merge: <what and why> (方案 X)"
```
After merge verify: `MASTER..FEAT=0`, `FEAT..MASTER=1` (just the merge commit), `DIRTY_TOTAL` unchanged.

## Post-merge verification
```bash
./venv/Scripts/python.exe -m pytest tests/constraint tests/orchestrator tests/agent tests/audit tests/api -q
npm run check                  # tsc -b --noEmit, expect 0 errors
```

## Delete merged branch (only after merge, user-approved)
```bash
git branch --merged master | grep <branch>   # must list it (fully contained)
git branch -d <branch>                        # safe delete
```

## Overlap rescue (feature file also shows dirty)
Common cause: you committed, then edited a file (e.g. appended a doc log) but forgot to commit → it appears in both `git diff --name-only master...HEAD` and `git status`. Fix:
```bash
git add <that-file>
git commit --amend --no-edit    # fold the late edit into the feature commit
# re-run the overlap check -> now empty
```
autocrlf note: "LF will be replaced by CRLF" warnings are cosmetic; if a committed file shows as dirty only due to line endings, `git checkout -- <file>` normalizes it (content preserved).

## Anti-patterns that bit us before
- Assuming a file/module exists without grepping (B-style "assumed wrong"): verify before planning.
- Putting metadata on the `run()` return top-level (e.g. `_citation_coverage`) → engine `state[seg]=out.get(seg)` drops it; inline into the sub-segment.
- `AuditEntry` persists `input_hash`/`output_hash` only, NOT raw `output` → verify-by-replaying-raw-output fails; bind via hash recomputation.
