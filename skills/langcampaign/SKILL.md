---
name: langcampaign
description: Use when a learner explicitly invokes $langcampaign or clearly asks to create, continue, assess, pause, resume, transition, or inspect a goal-driven language-learning campaign. Do not implicitly use for one-off translation, grammar, pronunciation, editing, or general language discussion.
---

# LangCampaign

Turn a practical language goal into one compact, resumable campaign. Converse naturally; use only `../../scripts/langcampaign_adapter.py` for durable operations. Never read or edit learner JSON directly.

## Begin every interaction

1. Run `check-install` when environment readiness is unknown.
2. Run `status` before asking the learner to repeat campaign context.
3. Route the request using [learner-policy.md](../../workflow/learner-policy.md).
4. Load [generation-contracts.md](../../workflow/generation-contracts.md) only when generating setup or refreshed mission content.
5. Format the learner reply with [presentation.md](../../workflow/presentation.md). Consult [examples.md](../../workflow/examples.md) only when a recovery or lifecycle flow is unclear.

Send exactly one protocol-v1 JSON request to the adapter per operation. A read uses `{"protocol_version":1,"operation":"check-install","operation_id":null,"input":{}}`; mutations use a UUID operation ID. Reuse the same request and UUID after a timeout. Never invent commands, paths, scores, timestamps, or saved state.

If `check-install` returns retryable `PERSISTENCE_FAILURE` because the Codex sandbox cannot access the personal data directory, explain that LangCampaign needs one-time permission to keep campaigns available across repositories, request that approval for the adapter invocation, and retry the identical request with approved access. Never fall back to repository or current-directory storage.

## Interaction contract

- Ask only for missing target language, practical goal, optional deadline, realistic weekly time, and compact prior knowledge. If the opening request is sufficient, ask nothing.
- Use the fixed Flexible/Targeted, Balanced, Supportive defaults. Do not offer presentation or coaching settings.
- Generate a hidden coarse roadmap with two or three upcoming missions and detailed content only for the current mission.
- Normally use one model response and one committed mutation. Deterministic reads are allowed. Invalid generated content gets one correction generation and no other retry.
- Resume the exact persisted checkpoint and content. Do not rebuild from the transcript.
- Treat the engine's revision, score, outcome, progress, and next action as authoritative.

## Independent check

Announce the no-hints boundary before the response. Do not supply or translate the answer, correct before scoring, complete a stem, offer choices, coach a rubric criterion, or give an example that solves the prompt. Repeating the prompt or clarifying non-linguistic mechanics is allowed.

Evaluate once against every persisted rubric criterion, then call `submit-assessment` with `independent: true`. If material help leaked, call `return-to-practice`; record no assessment.

## Safety

Never claim progress was saved after an adapter error. Never expose JSON, stack traces, rubric internals, full roadmap, or learner identifiers in ordinary replies. Export only to an explicit destination. Reset only after the learner explicitly supplies `RESET LANGCAMPAIGN`.
