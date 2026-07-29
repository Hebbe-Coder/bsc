# O1 - Obsidian Integration Boundary

## Goal

Back up user-owned Obsidian configuration, verify the enabled integration
baseline, and make Local REST API safe before any BSC connection is considered.

**Depends on:** none.
**Blocks:** O2-O6.

## Owned Surfaces

**Modify:** user-owned plugin settings only after a timestamped private backup,
the ecosystem worklog, and focused boundary tests.
**Do not modify:** plugin JavaScript/CSS, source notes, Vault content, BSC data,
or any credential value.

## Inputs And Contract

- Vault root is `D:/bsc/bsc`; the BSC-managed project root is
  `projects/default`.
- Local REST API is optional. Its token must exist only in its plugin settings
  or ignored runtime secret storage. Filesystem projection remains the BSC
  baseline until the secure read boundary is proven.
- Required core plugins are Properties, Bases, Canvas, Backlinks, Graph,
  Templates and Daily Notes. Community plugin inventory records IDs and
  versions only.

## Outputs, Authorization, And Redaction

- **Outputs:** a redacted inventory, private-backup success record, secure
  listener state, protected-route result, and a clear distinction between
  configured and restart-verified state.
- **Authorization:** the owner performs only settings changes for the declared
  Vault. BSC receives no Local REST token and does not call a write, delete,
  traversal, or LAN endpoint.
- **Redaction:** neither tests nor handoff may include tokens, configuration
  bodies, source notes, account identifiers, certificate material, or paths
  outside the declared Vault boundary.

## Test-First Tasks

1. First write a focused failing redacted configuration probe test: it may report plugin/version,
   port, secure/insecure state and protected-route result, but it must reject
   serializing token, key, certificate private key or source content.

## Implementation Tasks

2. Create a timestamped private backup of `.obsidian` JSON configuration outside
   the Vault and Git worktree. Record only backup success and file count.
3. Inventory the required core plugins and enabled community integrations.
4. Configure Local REST API for secure loopback access only: secure port `27124`
   enabled, insecure port `27123` disabled, token required, no LAN exposure or
   unauthenticated write/delete/traversal operation.
5. Restart or reload Obsidian, then prove an unauthenticated secure `/vault/`
   and `/openapi.json` call returns `401`, and that `27123` is unreachable.
   Do not supply or log an authorization token in this test.
6. Leave BSC disconnected from Local REST API. Any later integration needs a
   separate scoped, authorized and redacted read test.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_obsidian_integration_boundary.py -q
curl.exe --silent --insecure --max-time 3 --output NUL --write-out "%{http_code}" https://127.0.0.1:27124/vault/
```

The test passes only when the report contains no secret, the secure route is
protected, and the old plaintext runtime listener is closed after reload.

## Failure, Rollback, Worklog, And Handoff

If a setting is invalid, restore only the private backup of that plugin JSON;
do not uninstall plugins or delete their data. Hand O2 a redacted plugin matrix,
backup result, Local REST state, exact probe/test output, and any user action
still required for reload. Append every attempt to the shared worklog with the
command, exit state, protected-route response, backup evidence, deviation, and
rollback action; do not record restart verification until it has actually
occurred.
