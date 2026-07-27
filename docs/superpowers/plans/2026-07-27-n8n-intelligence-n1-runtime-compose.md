# N1 - n8n Runtime And Compose

## Goal

Introduce a disabled-by-default n8n Compose profile that can be started,
observed, stopped, and rolled back without changing existing BSC, Celery,
Horizon, Obsidian, or A/B/C/D runtime behavior.

**Depends on:** none.
**Blocks:** N2 and N3.

## Owned Surfaces

**Modify:** docker-compose.yml, Docker runtime configuration, ignored runtime
secret templates, and focused Compose/configuration tests.

**Create:** n8n profile documentation, service-health probe, runtime feature
flag, and a redacted operator bootstrap/runbook.

**Do not modify:** BSC source/triage logic, Horizon behavior, Celery schedules,
provider credentials, user Vault content, third-party workflow data, or any
existing service port/health semantics.

## Inputs, Outputs, Authorization, And Redaction

- **Inputs:** existing Compose topology and the product PRD runtime contract.
- **Outputs:** an optional n8n service, named persistent volume, local-only
  management binding, restart policy, encryption-key variable contract, health
  state, feature-flag state, and disable procedure.
- **Authorization:** only the local service owner can initialize n8n and create
  its first account. BSC does not receive n8n administrative credentials.
- **Redaction:** configuration examples use placeholders only. No runtime
  encryption key, n8n account, provider credential, local path, or cookie is
  committed, printed, or added to the worklog.

## Test-First Tasks

1. Add focused failing Compose contract tests for: n8n is absent from the
   default service set; the n8n profile requires an encryption key; its named
   volume is persisted; and the UI port is bound only to loopback.
2. Add the optional n8n service using a pinned compatible image, a named data
   volume, local-only port binding, non-root defaults supported by the image,
   restart policy, and a health check that distinguishes startup from ready.
3. Add a feature flag that prevents any BSC schedule or ingress path from
   claiming n8n availability merely because a container is defined.
4. Document local bootstrap: create runtime secret outside Git, start the n8n
   profile, create an n8n owner account, and keep provider credentials solely
   in n8n after startup. Do not import the supplied workflow in N1.
5. Verify default Compose remains unchanged when the profile is omitted, then
   verify explicit profile startup/shutdown, health state, persisted volume, and
   feature-flag disable behavior.

## Acceptance

~~~powershell
docker compose config
docker compose --profile n8n config
./.venv/Scripts/python.exe -m pytest tests/test_docker_compose_contract.py tests/test_config_n8n.py -q
docker compose --profile n8n up -d n8n
docker compose --profile n8n ps
docker compose --profile n8n down
git diff --check
~~~

The acceptance result is incomplete if image pull, Docker Desktop, encryption
secret, or owner-account initialization is unavailable. It must record that
state rather than report n8n as operational.

## Rollback, Worklog, And Handoff

Disable the n8n profile and feature flag, then stop only the n8n service. Keep
the named volume unless the service owner explicitly requests destructive
removal. The handoff includes Compose diff, image/version, profile state,
redacted environment-variable names, test/health output, volume behavior,
external blockers, and rollback result. Record every attempt in the shared
n8n information-intelligence worklog.
