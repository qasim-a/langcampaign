# LangCampaign Lean Mission Runtime Design

**Date:** 2026-08-04
**Status:** Approved in conversation; awaiting written-spec review

## Objective

Turn the persisted campaign engine into a usable mission-learning runtime for
Codex. A learner should move through focused teaching, guided practice, one
short independent check, evidence-backed assessment, compact progress, and a
clear next action in one continuous conversation.

The runtime must remain goal-scoped, resumable, and responsive. It must not
introduce multiple agents or serial model calls for an ordinary learner turn.

## Learner experience

A mission attempt follows one visible sequence:

```text
🎯 State the practical capability and scenario
→ Teach only the material needed now
→ Run short guided practice with decreasing help
→ Clearly announce a no-hints check
→ Evaluate one independent learner response
→ Record pass, partial, or retry
→ Show compact progress and the next action
```

Each attempt ends with one short no-hints check and one result. A mission does
not require several independent checks in the same attempt. Later attempts or
review missions can gather additional evidence when necessary.

Normal results use one colored status emoji, a short factual explanation, a
ten-segment text progress bar, and the next action. The runtime avoids banners,
emoji patterns, long encouragement, CEFR estimates, and dashboard-style output.

## Runtime ownership boundary

Codex owns the conversational work:

- Generate focused teaching and practice.
- Conduct the learner interaction.
- Clearly announce the no-hints boundary.
- Interpret the independent learner response.
- Submit a structured result to LangCampaign.

The local Python engine owns deterministic state and policy:

- Validate generated mission content before activation.
- Enforce legal checkpoint transitions.
- Prevent assessment evidence before the no-hints checkpoint.
- Persist one assessment result per mission attempt.
- Preserve earned partial credit and prior evidence.
- Choose advancement, focused retry, prerequisite support, or review.
- Calculate and render compact progress.
- Provide enough structured context to resume in a fresh Codex session.

Generated teaching text and full transcripts are not campaign state. Codex
conversation history may contain them, but LangCampaign persists only concise
structured checkpoints, outcomes, and assessment evidence.

## Campaign-embedded runtime state

Runtime state is stored additively inside the existing atomic `CampaignState`.
There is at most one active mission session per campaign.

The session records:

- Current mission identifier.
- Checkpoint: teaching, guided practice, check ready, or assessed.
- Positive integer attempt number.
- Difficulty adjustment: standard, harder, or prerequisite support.
- Whether review is due.
- Latest outcome when assessed: pass, partial, or retry.

No separate mutable session file is introduced. Assessment evidence and the
corresponding checkpoint advancement are published in one atomic campaign
state write. This prevents evidence and runtime state from disagreeing after a
failure.

Older campaign schemas remain loadable with no active mission session. The
runtime state becomes campaign-state schema version 5. Versions 1 through 4
continue to load with `active_session` absent.

## Checkpoint state machine

The normal transitions are:

```text
no session → teaching
teaching → guided practice
guided practice → check ready
check ready → assessed
assessed → next mission teaching | retry teaching | review teaching | no session
```

The engine rejects skipped or reversed checkpoints. In particular:

- Evidence cannot be submitted from teaching or guided practice.
- Entering `check ready` is the durable indication that the learner was told
  support had ended.
- One attempt can publish only one assessment result.
- Starting another attempt increments the attempt number.
- Completing or pausing a campaign preserves its current mission session.
- Resuming a campaign restores that exact checkpoint.

An assessed session remains readable until the next action is started. This
allows a fresh session to render the completed result and proposed next action
without relying on the previous transcript.

## Assessment outcomes

Codex submits a structured assessment containing the current campaign and
mission identifiers, attempt number, score, independence declaration,
modality, timestamp, and a concise evidence-based result statement. A valid
submission from `check ready` must declare `independent: true`. If Codex gives
help after announcing the check, it must return the session to guided practice
and may not submit that response as an assessment.

The engine verifies that the identifiers and attempt match the active session
and that the session is at `check ready`. The existing validated
`AssessmentEvidence` remains the durable evidence record.

Outcome policy is intentionally small and fixed:

- **Pass (80–100):** record independent evidence and advance to the next
  eligible mission, unless a review is due first.
- **Partial (40–79):** record the earned independent evidence and schedule
  focused practice or another attempt on the same capability.
- **Retry (0–39):** record the independent attempt without awarding mission
  completion, retain all earlier evidence, and schedule support followed by
  another attempt.

Codex may explain its evaluation, but it may not override the engine's outcome
band for the submitted score.

Language introduced, corrected, or prompted during the no-hints response is
not credited as independently demonstrated in that same attempt. A failed
evidence write leaves the previous state unchanged, and Codex must not tell the
learner the result was recorded.

## Difficulty feedback and local adaptation

The learner may say `too easy` or `too hard` at any point before assessment is
recorded. These are preference signals, not evidence.

- `too easy` marks the current or next attempt as harder. Codex shortens guided
  practice and makes the next independent check more demanding while testing
  the same practical capability.
- `too hard` marks the current or next attempt for prerequisite support. The
  learner does not advance; Codex inserts one focused prerequisite practice
  step before retrying the same capability.

These adjustments do not erase evidence, mutate the campaign goal, regenerate
the full roadmap, or automatically change unrelated missions. Repeated signals
replace the current pending adjustment rather than creating an unbounded queue.

## Mission selection and review

Only the current mission has detailed teaching, practice, and assessment
content. Two or three later missions may remain as concise outlines. A later
mission is detailed only when it approaches activation.

After assessment, the engine deterministically selects one next-action type:

1. Prerequisite support for `too hard` or a retry result.
2. Focused practice or retry for a partial result.
3. A due review of previously demonstrated capability.
4. The next eligible roadmap mission after a pass.
5. Campaign completion when every critical mission is passed and no review is
   due. Supporting prerequisite missions remain required when referenced by a
   critical mission; extension missions are optional.

The first version uses a simple mission-level `review due` flag. It does not
implement vocabulary cards, spaced-repetition intervals, full-roadmap
replanning, or multi-mission simulations.

## Generated content validation

Mission content is generated only when needed and must continue to satisfy the
existing mission-plan validation contract. The runtime adds validation for the
current teaching/practice/check payload needed by Codex.

A validation failure permits one bounded correction attempt by Codex. If the
second candidate is invalid, no content or checkpoint is activated. The
learner receives a concise retry message rather than an open-ended generation
loop.

The Python engine does not call a model itself. It validates structured input
provided by the future Codex workflow, preserving a platform-neutral runtime
boundary.

## Command boundary

The runtime adds these exact command names; the implementation plan defines
their JSON field schemas:

- `mission-status`: start or resume the active mission and return its
  structured checkpoint.
- `advance-mission`: move teaching to guided practice, guided practice to
  check ready, or an assessed result to its selected next action.
- `adjust-difficulty`: record `too easy` or `too hard` before assessment.
- `submit-assessment`: atomically record evidence, outcome, progress, and the
  selected next action.

Existing setup, roadmap, validation, and campaign-lifecycle commands remain
compatible. Each command emits exactly one JSON envelope. Expected learner and
content errors use concise typed error envelopes; arbitrary programmer faults
continue to propagate.

## Progress rendering

Progress is rendered locally without another model call. The normal output is:

```text
✅ Mission passed

You responded appropriately and asked a relevant follow-up without hints.

Progress  ████░░░░░░  40%

Next: respond naturally to unexpected news.
```

Progress is mission-level and evidence-aware. For each mission, the engine uses
the highest independent score ever recorded, so a later weak attempt can mark
the mission for review without erasing previously earned credit. Campaign
progress is the existing mission-weighted percentage calculated from those
best scores and rounded to the nearest integer. The learner-facing bar has ten
segments, clamps to 0–100%, and is explicitly campaign-goal progress rather
than general language proficiency.

A passed mission whose latest independent attempt later scores below 80 is
marked `review due`, while its best-score progress credit remains. Completing
the review can raise the best score or clear review due, but can never reduce
stored credit.

## Responsiveness contract

The product requirement is a user-friendly experience, not a brittle absolute
deadline.

- Local lookup, validation, state transition, evidence recording, and progress
  rendering should normally complete in milliseconds and target less than
  100 ms in representative local benchmarks.
- An ordinary learner interaction requires at most one substantive model
  response and one local persistence command.
- Initial roadmap or new-mission generation uses one model response plus local
  validation, with at most one bounded correction attempt after invalid
  content.
- No operation may perform separate planner, teacher, and assessor model calls,
  generate a full detailed curriculum, or rebuild the roadmap without an
  explicit later requirement.
- If a genuinely longer operation is underway, Codex should provide concise
  progress rather than leave the learner without feedback.

External model or service latency cannot be guaranteed. Acceptance testing
will measure local command latency and end-to-end representative flows, and
will investigate any avoidable delay rather than enforcing an arbitrary
one-minute cutoff.

## Failure and recovery behavior

- Invalid generated content is never activated or persisted.
- Illegal checkpoint transitions leave campaign state unchanged.
- Failed evidence persistence leaves both evidence and checkpoint unchanged.
- A result is not described as recorded until persistence succeeds.
- A fresh Codex session can reconstruct the active mission, checkpoint,
  adjustment, latest result, progress, and next action without the old
  transcript.
- Pausing, completing, transitioning, or resuming campaigns retains their
  embedded runtime state consistently with existing lifecycle semantics.

## Testing strategy

The implementation must use test-driven development and cover:

- Every allowed checkpoint transition.
- Skipped, reversed, duplicated, stale-attempt, and mismatched-mission calls.
- Pass, partial, and retry outcome bands.
- The prohibition on evidence before `check ready`.
- One-result-per-attempt enforcement.
- Partial-credit and prior-evidence preservation.
- `too easy` and `too hard` before each assessable checkpoint.
- Review-due selection and next-mission advancement.
- Atomic publication failure and fresh-process recovery.
- Schema migration from all supported historical versions.
- Deterministic progress rendering at 0%, partial boundaries, and 100%.
- JSON command success and typed-error envelopes.
- End-to-end learner flows through setup, mission attempts, fresh-session
  resume, campaign pause/resume, and completion.
- Representative local-operation latency measurements with generous,
  non-flaky thresholds.

## Explicitly deferred

- ChatGPT integration and hosted learner persistence.
- Voice and pronunciation scoring.
- Multiple checks inside one mission attempt.
- Detailed transcript storage.
- Full placement examinations.
- Rich dashboards and CEFR estimates.
- Vocabulary-card or sophisticated spaced-repetition scheduling.
- Automatic full-roadmap replanning.
- Separate planner, teacher, and assessor agents.
- Coaching-style or presentation-style controls.

## Acceptance criteria

The runtime milestone is complete when:

1. A learner can start the first mission immediately after setup.
2. One continuous flow reaches teaching, guided practice, an announced
   no-hints check, persisted assessment, progress, and a next action.
3. Each attempt produces exactly one pass, partial, or retry result.
4. Partial work receives persisted credit without being described as a pass.
5. `too easy` and `too hard` adjust only the relevant next attempt.
6. A fresh process resumes the exact active checkpoint without the transcript.
7. Assessment and checkpoint advancement remain atomic under injected failure.
8. Normal progress uses a colored emoji, ten-segment bar, factual result, and
   next action.
9. Representative local commands stay effectively instantaneous, and the
   design adds no avoidable serial model calls.
10. Existing campaign setup, persistence, transition, and resume behavior
    remains compatible.
