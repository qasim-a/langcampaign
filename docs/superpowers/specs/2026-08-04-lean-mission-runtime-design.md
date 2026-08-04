# LangCampaign Lean Mission Runtime Design

**Date:** 2026-08-04
**Status:** Revised after written-spec review; awaiting approval

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

Full transcripts are not campaign state. Codex conversation history may
contain them, but LangCampaign persists only the validated compact content
needed to resume, structured checkpoints, outcomes, and assessment evidence.

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
- Validated compact content for the current attempt.
- The selected next action after assessment.
- Attempt kind: initial, retry, prerequisite-supported, or review.

Campaign state also records roadmap phase identifiers whose one-time planned
review boundary has been completed. This makes review scheduling stable across
restarts and prevents a cleared review from being recreated by the same phase.

No separate mutable session file is introduced. Assessment evidence and the
corresponding checkpoint advancement are published in one atomic campaign
state write. This prevents evidence and runtime state from disagreeing after a
failure.

Older campaign schemas remain loadable with no active mission session. The
runtime state becomes campaign-state schema version 5. Versions 1 through 4
continue to load with revision `0`, `active_session` absent, and no attempt
records. Loading does not rewrite an old file. Its first successful mutation
writes the complete version-5 representation at revision `1`.

### Persisted compact mission content

The active session persists the validated material needed to resume without a
transcript:

- Practical capability and scenario.
- Short teaching objectives and essential language points.
- Ordered guided-practice prompts.
- No-hints assessment prompt.
- A mission-specific scoring rubric.
- Content-generation identifier and candidate number.

It does not persist conversational filler, learner messages, model reasoning,
corrections, or the full transcript. Codex may phrase and adapt the stored
material conversationally, but it cannot replace the persisted assessment
prompt or rubric after the no-hints checkpoint becomes ready.

Each rubric contains stable criterion identifiers, observable descriptions,
and positive integer weights totaling 100. At assessment, Codex submits a
0–100 score for every criterion. The engine derives the weighted total using
round-half-up arithmetic; Codex does not submit an authoritative total score.

### Attempt history and identity

Campaign state persists immutable mission-attempt records. Each record is
uniquely identified within a campaign by `(mission_id, attempt_number)` and
contains the rubric snapshot, criterion scores, derived score, outcome,
engine-generated assessment time, and concise result statement. Schema
validation requires one corresponding `AssessmentEvidence` with the same
mission, derived score, modality, and timestamp.

The first attempt for each mission is number `1`. Starting another attempt for
the same mission uses one plus the highest persisted attempt number, including
retries and later reviews. Attempt numbers are never reused or decremented.

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

The selected next action is persisted in the same write as the assessment. It
contains an action type—prerequisite support, focused retry, review, next
mission, or goal ready to complete—and a target mission identifier when
required. A restart reads this value instead of recomputing it.

## Assessment outcomes

Codex submits a structured assessment containing the current campaign and
mission identifiers, attempt number, criterion scores, independence
declaration, modality, and a concise evidence-based result statement. A valid
submission from `check ready` must declare `independent: true`. If Codex gives
help after announcing the check, it must return the session to guided practice
and may not submit that response as an assessment. The engine assigns the
authoritative timezone-aware timestamp when committing the result;
caller-provided timestamps are neither accepted nor used for ordering.

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

Codex may explain its evaluation, but it may not override the engine-derived
weighted score or its outcome band.

Language introduced, corrected, or prompted during the no-hints response is
not credited as independently demonstrated in that same attempt. A failed
evidence write leaves the previous state unchanged, and Codex must not tell the
learner the result was recorded.

The engine cannot inspect the conversation and prove that Codex withheld
hints. It enforces the durable no-hints checkpoint, requires the independence
declaration, derives the rubric score, and rejects illegal transitions.
Workflow instructions and adversarial end-to-end evaluations are responsible
for detecting conversational hint leakage. The product must not claim stronger
verification than this boundary provides.

Submitting an assessment twice is idempotent. If campaign, mission, attempt,
criterion scores, independence declaration, modality, and result statement
exactly match the stored attempt, the engine returns the original result
without appending evidence or changing revision. A second submission for the
same attempt identity with different values fails with `duplicate_conflict`.

## Difficulty feedback and local adaptation

The learner may say `too easy` or `too hard` at any point before assessment is
recorded. These are preference signals, not evidence. The session stores at
most one pending adjustment; the most recent signal replaces the earlier one.

- `too easy` marks the current or next attempt as harder. Codex shortens guided
  practice and makes the next independent check more demanding while testing
  the same practical capability.
- `too hard` marks the current or next attempt for prerequisite support. The
  learner does not advance; Codex inserts one focused prerequisite practice
  step before retrying the same capability.

The adjustment applies immediately while the session is in teaching or guided
practice. At `check ready`, changing difficulty returns the session to guided
practice so Codex can prepare an adjusted check; the old check cannot be
assessed. The adjustment is consumed when the adjusted no-hints check becomes
ready and resets to standard after assessment.

These adjustments do not erase evidence, mutate the campaign goal, regenerate
the full roadmap, or automatically change unrelated missions.

## Mission selection and review

Only the current mission has detailed teaching, practice, and assessment
content. Two or three later missions may remain as concise outlines. A later
mission is detailed only when it approaches activation.

After assessment, the engine deterministically selects one next-action type:

1. Prerequisite support for `too hard` or a retry result.
2. Focused practice or retry for a partial result.
3. A due review of previously demonstrated capability.
4. The next eligible roadmap mission after a pass.
5. Goal readiness when every critical mission is passed and no review is due.
   Supporting prerequisite missions remain required when referenced by a
   critical mission; enrichment missions are optional.

Outcome and review rules are:

- Pass sets an unpassed mission to `DEMONSTRATED`. A successful review also
  clears `REVIEW_DUE`.
- Partial or retry sets an unpassed mission to `DEVELOPING` and selects the
  same mission for another attempt.
- When a previously demonstrated mission is assessed below 80, it becomes
  `REVIEW_DUE`; best-score progress credit remains intact.
- At a roadmap phase whose `planned_review_after` flag is true, each
  demonstrated critical mission in that phase receives one review before the
  next phase begins. A successful review is not scheduled again by that same
  phase boundary.
- Required prerequisite support and same-mission retry take priority over a
  due review. Due reviews follow roadmap order and take priority over a new
  mission. New missions follow active-phase roadmap order.
- A review clears only with a score of at least 80. A lower review score keeps
  the mission `REVIEW_DUE` and selects focused retry or prerequisite support
  according to the normal outcome.

Meeting every educational requirement persists the next action
`goal_ready_to_complete`; it does not change learner lifecycle state. The
existing explicit `complete-campaign` operation performs administrative
completion and may intentionally end an unfinished campaign. Pausing,
resuming, and administrative completion preserve mission session and attempt
history. Completed campaigns remain non-resumable under the existing rule.

The first version uses a simple mission-level `review due` flag. It does not
implement vocabulary cards, spaced-repetition intervals, full-roadmap
replanning, or multi-mission simulations.

## Generated content validation

Mission content is generated only when needed and must continue to satisfy the
existing mission-plan validation contract. The runtime adds validation for the
current teaching/practice/check payload needed by Codex.

A candidate carries a stable `generation_id` and `candidate_number` of `1` or
`2`. Validation returns either the normalized content bundle or ordered
structured issues containing `field`, `code`, and `message`. Candidate 1
failure returns `correction_allowed: true`; candidate 2 failure returns
`correction_allowed: false`. No invalid candidate changes campaign state.

The Codex workflow may generate candidate 2 only in response to candidate 1's
issues and must preserve the same `generation_id`. It then either activates the
normalized bundle through `start-mission` or shows a concise terminal retry
message. The engine is a stateless content validator and does not call a model;
the Codex workflow owns enforcement of the one-correction policy.

The Python engine does not call a model itself. It validates structured input
provided by the future Codex workflow, preserving a platform-neutral runtime
boundary.

## Command boundary

The runtime adds these exact command names:

- `validate-mission-content`: read-only validation of a generated candidate;
  returns normalized content or structured issues and `correction_allowed`.
- `mission-status`: read-only retrieval of revision, current session, compact
  content, latest result, progress, and persisted next action. With no session,
  it returns `session: null` and does not start one.
- `start-mission`: activates validated content for the selected mission and
  creates its next attempt.
- `advance-mission`: move teaching to guided practice, guided practice to
  check ready, or an assessed result to its selected next action.
- `adjust-difficulty`: record `too easy` or `too hard` before assessment.
- `submit-assessment`: atomically record evidence, outcome, progress, and the
  selected next action.

Every request contains `learners_root`, `learner_id`, and `campaign_id` except
content validation, which is repository-independent. Every mutation also
contains `expected_revision`; mission mutations contain `mission_id` and the
current `attempt_number`. Assessment contains rubric criterion scores,
`independent`, `modality`, and `result_statement`. Successful read and mutation
responses return the authoritative revision and normalized session snapshot.
The implementation plan must provide literal JSON examples and exact parser
rules for every request and response.

Existing setup, roadmap, validation, and campaign-lifecycle commands remain
compatible. Each command emits exactly one JSON envelope. Expected learner and
content errors use concise typed error envelopes; arbitrary programmer faults
continue to propagate.

Stable runtime error codes are:

- `invalid_request`
- `invalid_content`
- `campaign_not_found`
- `campaign_not_active`
- `campaign_completed`
- `mission_not_found`
- `session_not_started`
- `invalid_transition`
- `assessment_not_ready`
- `independence_required`
- `attempt_conflict`
- `duplicate_conflict`
- `revision_conflict`
- `persistence_failed`

Error envelopes contain `success: false` and an `error` object with `code` and
`message`; validation errors may additionally contain ordered `issues`.
Successful envelopes retain the existing `success: true, data: {...}` shape.
Only declared domain, validation, concurrency, and persistence failures are
converted to envelopes. Unexpected programmer faults propagate.

## Concurrency and revision control

Campaign-state schema version 5 has a nonnegative integer `revision`. Every
successful state mutation increments it exactly once. Read commands return it,
and all runtime mutations require `expected_revision`.

Within an exclusive per-campaign repository lock, a mutation reloads the
current state, compares its revision, validates the requested transition, and
publishes the replacement atomically. A mismatch returns `revision_conflict`
with the current revision and makes no change. Atomic replacement alone is not
treated as concurrency control because two writers could otherwise both commit
from the same stale state.

An idempotent duplicate assessment is checked after the locked reload and
before revision comparison. It returns the original stored response even when
the caller's expected revision is stale. A conflicting duplicate still fails
with `duplicate_conflict`.

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
best scores. Percentage rounding is round-half-up: for nonnegative rational
value `x`, use `floor(x + 0.5)`. The ten-segment bar fills
`floor(clamped_percent / 10)` segments; therefore 0–9% shows zero filled
segments, 10–19% shows one, and 100% shows ten. It is explicitly campaign-goal
progress rather than general language proficiency.

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
- One learner message normally causes at most one model generation and one
  local state mutation. Teaching, evaluation, feedback, and learner-facing
  wording for that message must not be split into serial model calls.
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
  compact content, adjustment, latest result, progress, and persisted next
  action without the old transcript.
- Pausing, completing, transitioning, or resuming campaigns retains their
  embedded runtime state consistently with existing lifecycle semantics.
- A stale concurrent mutation fails without overwriting newer state.
- An identical retried assessment returns its original result without adding
  evidence or advancing revision.

## Compatibility contract

This milestone preserves these current public boundaries and invariants:

- `src/langcampaign/storage.py`: `CampaignState`, versions 1–4 loading,
  descriptor-confined regular-file reads, atomic publication, and validation
  before persistence.
- `src/langcampaign/models.py`: `Campaign`, `Mission`, `MissionStatus`, fixed
  learner defaults, immutable records, and mission identifiers.
- `src/langcampaign/assessment.py`: `AssessmentEvidence` validation and
  existing public readiness APIs. Runtime progress may add a best-evidence
  calculation but must not silently change the legacy function's semantics.
- `src/langcampaign/missions.py` and `src/langcampaign/roadmaps.py`: mission-map
  identity, prerequisite, acyclicity, critical-mission, active-phase, and
  roadmap-order validation.
- `src/langcampaign/learners.py`: normalized repository-local learner paths,
  one active campaign, resumable paused campaigns, non-resumable completed
  campaigns, explicit evidence transfer, and failed-transition safety.
- `src/langcampaign/cli.py`: the existing nine commands, exactly-one-JSON
  envelope behavior, narrow typed-error conversion, and programmer-fault
  propagation.

Version-5 conversion must be additive. Existing public exports remain
available, existing successful command payloads do not lose fields, and all
226 pre-runtime tests must continue to pass unchanged unless a test explicitly
asserts the command-name set and is extended for the new commands.

## Testing strategy

The implementation must use test-driven development and cover:

- Every allowed checkpoint transition.
- Skipped, reversed, duplicated, stale-attempt, and mismatched-mission calls.
- Read-only `mission-status` behavior when no session exists.
- Pass, partial, and retry outcome bands.
- Rubric weight validation, criterion completeness, and half-up score derivation.
- The prohibition on evidence before `check ready`.
- One-result-per-attempt enforcement.
- Identical and conflicting duplicate assessment submissions.
- Partial-credit and prior-evidence preservation.
- `too easy` and `too hard` timing, replacement, consumption, and reset.
- Review scheduling, prioritization, attempt numbering, clearing, and
  goal-ready selection.
- Atomic publication failure and fresh-process recovery.
- Locked compare-and-swap behavior under deterministic concurrent writers.
- Schema migration from all supported historical versions.
- Deterministic progress rendering at 0%, partial boundaries, and 100%.
- Every JSON request, response, stable error code, and programmer-fault path.
- Candidate-1 correction and candidate-2 terminal content-validation flows.
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

1. A learner can validate content and start the first mission immediately after
   setup, while a status read alone never mutates campaign state.
2. One continuous flow reaches teaching, guided practice, an announced
   no-hints check, persisted assessment, progress, and a next action.
3. Each attempt produces exactly one pass, partial, or retry result.
4. Partial work receives persisted credit without being described as a pass.
5. `too easy` and `too hard` adjust only the relevant next attempt.
6. A fresh process resumes the exact active checkpoint, compact mission
   content, and persisted next action without the transcript.
7. Assessment and checkpoint advancement remain atomic under injected failure.
8. Normal progress uses a colored emoji, ten-segment bar, factual result, and
   next action.
9. Representative local commands stay effectively instantaneous, and the
   design adds no avoidable serial model calls.
10. Existing campaign setup, persistence, transition, and resume behavior
    remains compatible.
11. Concurrent stale mutations cannot overwrite newer state, and a retried
    identical assessment cannot create duplicate evidence.
12. Mission-specific rubric criteria produce the authoritative score, while
    the product accurately describes independence as workflow-enforced rather
    than engine-proven.
