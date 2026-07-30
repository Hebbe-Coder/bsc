# PBOS v1.0 Product Requirements Document

## Product Definition

PBOS (Personal Business Operating System) connects personal knowledge, real execution evidence, outcomes, and reflection to compile the next personal execution strategy. It is not a fixed SOP library. The v1 audience is one person's AI-project delivery workspace.

## Daily Product Loop

1. **Today**: recommend the highest-value next action with its evidence and success check.
2. **Reflect**: collect a three-minute record of completion, blocker, result, and adjustment.
3. **Grow**: turn verified execution and feedback into experiences, capabilities, and Strategy Genome revisions.

Evidence-poor requests must produce a capture plan, never an invented personalised conclusion.

## Authority And Storage

- Raw sources remain immutable. BSC stores lifecycle, authorization, provenance, and PBOS Artifact Graph state.
- Obsidian is the personal memory layer: L1 raw material, L2 methods/decisions/failures, L3 managed PBOS assets.
- Managed PBOS projections live under `pbos/` in the configured project Vault and expose Dataview-compatible frontmatter. Manual L3 edits become review candidates; they do not overwrite audited state.
- Weekly PBOS reports live below `distillations/每周蒸馏/<week>/pbos/` without changing the existing knowledge-distillation contract.

## Core Model

`PersonalProfile -> Capability`; `Mission -> PersonalExecutionPlan -> WorkExecutionRecord -> WorkOutcome -> WorkFeedback -> Experience -> Capability`; `Experience + Capability -> StrategyGenome -> SOPVersion -> next Mission`.

`StrategyGenome` is immutable and includes scope, input conditions, decision rules, execution paths, capabilities/tools, risks, failure boundaries, success metrics, verification, evidence, cases, and confidence.

## Functional Requirements

1. PBOS creates project-scoped profile, capability, plan, execution, outcome, feedback, experience, strategy, and promotion artifacts.
2. Local Git, build, test, BSC, and Vault evidence can be attached to an execution record. Only a server-captured receipt may qualify an outcome for learning; client-supplied receipt claims remain unverified. The user may add a concise reflection; no source is silently promoted to truth.
3. The personal compiler combines Mission/diagnosis with verified profile, capabilities, experiences, strategy genomes, resource constraints, and evidence gaps.
4. A strategy promotion requires three comparable complete records, no severe failure, and either a median quality improvement of at least ten points or removal of a known hard failure. Two comparable regressions or one severe failure roll the promoted version back.
5. The Personal Growth Cockpit shows only traceable information: today action, project health, capability evidence, strategy versions, failure patterns, and lineage.
6. GitHub and Feishu are read-only, explicitly authorised connectors. Without credentials their state is `awaiting_authorization`.
7. Daily, weekly, and monthly jobs are durable and auditable. No job claims external completion without a receipt.

## Safety And Acceptance

- Existing DBOS Mission authorization, MCP transport, and Artifact Graph semantics remain unchanged.
- Before Mission confirmation, PBOS may diagnose and compile but cannot cause external side effects.
- Every plan, outcome, promotion, and rollback links to its governing evidence.
- A user-entered quality score is an acceptance decision, not proof by itself. It is eligible for learning only when its own execution record includes a server-verified receipt and a reflection.
- Two comparable personal contexts must compile materially different execution plans when their history, constraints, or capabilities differ.
- Remote credentials never enter artifacts, Vault files, logs, or API responses.
