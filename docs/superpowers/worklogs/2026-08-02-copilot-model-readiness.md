# Copilot Model Readiness Runtime Record

Date: 2026-08-02
Project: `proj_b8a285642094`

## Scope

Make the active Obsidian authoring path honest when Claudian is unavailable and
Copilot's provider access is not readable from the plugin settings file.

## Implemented

- Added a metadata-only Copilot model readiness probe. It returns only
  `ready`, `unavailable`, or `unverified` plus a reason code; provider values
  and key material are never returned.
- Copilot Plus and known provider-key fields are recognized without exposing
  credentials. System keychain mode is reported as `unverified`.
- A clearly missing provider blocks the governed Copilot command with
  `copilot_model_not_configured` instead of recording a false dispatch.
- The Knowledge Workspace distinguishes a missing model setup from a keychain
  route that still needs live output proof.
- Claudian remains absent from the active Vault plugin list and is not used by
  the command bridge.

## Verification

- Backend focused scope: `65 passed, 1 skipped, 1 warning`.
- Frontend focused scope: `26 passed`.
- TypeScript check and production build passed.
- Docker Compose rebuilt API, Worker, and Beat successfully; all six runtime
  services remained healthy and `/ready` returned `ok`.
- Live workspace readback: Copilot archive route `configured`, Local REST
  `connected`, model readiness `unverified` with
  `copilot_provider_keychain_check_required`.
- A real allowlisted Copilot dispatch was received by the local bridge, but a
  bounded 35-second observation found no new or changed archive file. The
  result is transport proof only, not model-generation proof.
- Release remains `implemented_with_operational_proof_pending`; only
  `o6_feedback_cycle` is missing.

## Required external action

In Obsidian, complete one Copilot response using Copilot Plus or a configured
provider, confirm that it is saved in the project Copilot archive, then use the
BSC PBOS review flow to inspect and explicitly import it. Do not send provider
keys through chat.
