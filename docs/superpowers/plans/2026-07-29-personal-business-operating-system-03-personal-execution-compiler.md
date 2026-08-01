# PBOS Plan 03: Personal Execution Compiler

## Goal And Dependencies

Depends on Plans 01-02. Compile the confirmed Mission into a Personal Execution
Plan from declared profile, verified assets, failure patterns, governed Vault
context, resources, and evidence gaps. It must not return a fixed SOP template.

## Ownership And Prohibitions

- May change `app/pbos/compiler.py`, `app/pbos/context.py`, `app/pbos/service.py`,
  `app/api/pbos_api.py`, and contextual compiler/API tests.
- May use the configured planning provider within bounded context/token budgets;
  never expose provider keys, source bodies, or unreviewed output as evidence.
- Must not change Mission authorization or trigger any external side effect.

## Test-First Tasks

1. Assert contrasting roles/constraints produce different phases, capabilities,
   risks, checks, and evidence gaps.
2. Build bounded context from governed Vault/Wiki references, schedule state,
   and verified PBOS assets; exclude raw sources and unreadable legacy text.
3. Compile actions, inputs, outputs, decision points, checks, risks, success
   criteria, and reflection entry. Insufficient evidence emits a capture plan.
4. Localize visible actions to the Mission language without translating
   technical identifiers or manufacturing personal evidence.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_contextual_compiler.py tests/pbos/test_pbos_service.py tests/api/test_pbos_api.py -q
```

Every plan must link to Mission, profile, governed references, and named gaps;
read-only Cockpit access has no side effect. Rollback restores the compiler but
retains plans. Handoff records context order, fallback/locale behavior, and
contrasting-context assertions for Plans 04-05.
