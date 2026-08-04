# Lean Mission Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resumable, revision-safe mission runtime that validates compact content, conducts checkpointed attempts, records rubric-derived evidence, adapts locally, and renders compact learner progress.

**Architecture:** Pure runtime records and policy live in a new `runtime.py`; schema-v5 conversion remains in `storage.py`; descriptor-confined locked mutation remains a learner-repository responsibility; and `runtime_service.py` coordinates policy with persistence. The CLI exposes six runtime commands while Codex remains responsible for conversational generation and evaluation.

**Tech Stack:** Python 3.11+, frozen dataclasses, `StrEnum`, standard-library JSON/`fcntl`/descriptor APIs, existing atomic learner repository, pytest 8+.

## Global Constraints

- Codex is the only delivery target in this milestone; ChatGPT integration remains deferred.
- One learner message normally causes at most one model generation and one local state mutation.
- The Python engine never calls a model.
- Full transcripts, learner messages, model reasoning, and conversational filler are never persisted.
- Current compact mission content, rubric, attempt history, checkpoint, and selected next action are persisted.
- Each attempt has one no-hints check and exactly one pass, partial, or retry result.
- Pass is 80–100, partial is 40–79, and retry is 0–39.
- Rubric weights are positive integers totaling 100; the engine derives scores with round-half-up arithmetic.
- The engine assigns assessment timestamps; callers cannot supply them.
- Best independent evidence determines progress; later failure schedules review without erasing credit.
- Runtime mutations require `expected_revision`, lock the campaign, and increment revision exactly once.
- Identical duplicate assessments are no-op successes; conflicting duplicates fail.
- `mission-status` and `validate-mission-content` are read-only.
- Invalid generated content is never activated; Codex gets at most one correction candidate.
- Local operations target effectively instantaneous behavior with representative non-flaky latency coverage.
- Existing schema versions 1–4, nine commands, public APIs, lifecycle behavior, descriptor confinement, and 226 tests remain compatible.
- No runtime dependency may be added; Python 3.11 remains the minimum.
- Use the approved lighter workflow: one implementer, one whole-milestone review, and at most one consolidated fix wave.

## File map

- Create `src/langcampaign/runtime.py` — immutable runtime/content/rubric records and pure score, outcome, selection, and rendering policy.
- Create `src/langcampaign/runtime_service.py` — status/start/advance/adjust/assessment application over the learner repository.
- Modify `src/langcampaign/storage.py` — schema-v5 state and runtime conversion.
- Modify `src/langcampaign/learners.py` — exclusive descriptor-confined campaign lock and revision-checked mutation primitive.
- Modify `src/langcampaign/cli.py` — six runtime JSON commands and stable coded errors.
- Modify `src/langcampaign/__init__.py` — public runtime types and services.
- Create `tests/test_runtime.py` — pure policy/content/rubric/selection/rendering tests.
- Modify `tests/test_storage.py` — schema-v5 and v1–v4 migration tests.
- Modify `tests/test_learners.py` — locked compare-and-swap and descriptor-safety tests.
- Create `tests/test_runtime_service.py` — state-machine, idempotency, review, and recovery tests.
- Modify `tests/test_cli.py` — exact fifteen-command boundary and runtime envelopes.
- Create `tests/test_mission_runtime_flow.py` — complete learner and fresh-process flows.
- Modify `tests/fixtures.py` — reusable content/rubric payloads.
- Modify `README.md` — implemented runtime status without claiming the Codex plugin exists.

---

### Task 1: Pure runtime content, assessment, selection, and progress policy

**Files:**
- Create: `src/langcampaign/runtime.py`
- Modify: `src/langcampaign/__init__.py`
- Create: `tests/test_runtime.py`

**Interfaces:**
- Produces enums `MissionCheckpoint`, `DifficultyAdjustment`, `AttemptKind`, `MissionOutcome`, and `NextActionType`.
- Produces records `RubricCriterion`, `MissionContent`, `CriterionScore`, `NextAction`, `MissionAttemptRecord`, `ActiveMissionSession`, and `RuntimeProgress`.
- Produces `derive_score()`, `outcome_for_score()`, `best_independent_scores()`, `runtime_progress()`, `render_runtime_progress()`, and `select_next_action()`.

- [ ] **Step 1: Write failing immutable-record and validation tests**

Test exact enum values:

```python
MissionCheckpoint: teaching, guided_practice, check_ready, assessed
DifficultyAdjustment: standard, harder, prerequisite_support
AttemptKind: initial, retry, prerequisite_supported, review
MissionOutcome: pass, partial, retry
NextActionType: prerequisite_support, focused_retry, review, next_mission, goal_ready_to_complete
```

Define exact records:

```python
@dataclass(frozen=True)
class RubricCriterion:
    id: str
    description: str
    weight: int

@dataclass(frozen=True)
class MissionContent:
    generation_id: str
    candidate_number: int
    capability: str
    scenario: str
    teaching_objectives: tuple[str, ...]
    essential_language: tuple[str, ...]
    guided_prompts: tuple[str, ...]
    assessment_prompt: str
    rubric: tuple[RubricCriterion, ...]

@dataclass(frozen=True)
class CriterionScore:
    criterion_id: str
    score: int

@dataclass(frozen=True)
class NextAction:
    kind: NextActionType
    mission_id: str | None = None

@dataclass(frozen=True)
class MissionAttemptRecord:
    mission_id: str
    attempt_number: int
    kind: AttemptKind
    rubric: tuple[RubricCriterion, ...]
    criterion_scores: tuple[CriterionScore, ...]
    score: int
    outcome: MissionOutcome
    modality: str
    result_statement: str
    assessed_at: datetime

@dataclass(frozen=True)
class ActiveMissionSession:
    mission_id: str
    attempt_number: int
    kind: AttemptKind
    checkpoint: MissionCheckpoint
    adjustment: DifficultyAdjustment
    content: MissionContent
    latest_outcome: MissionOutcome | None = None
    next_action: NextAction | None = None
    content_refresh_required: bool = False
```

Require non-empty stripped strings, exact tuples, unique criterion IDs, weights totaling 100, candidate number 1 or 2, nonempty teaching/objective/prompt/rubric tuples, attempt number at least 1, complete unique criterion scores, aware datetimes, and next-action mission IDs exactly when the kind is not `goal_ready_to_complete`.

- [ ] **Step 2: Run records tests and observe RED**

Run: `python -m pytest tests/test_runtime.py -v`

Expected: import failure because `langcampaign.runtime` does not exist.

- [ ] **Step 3: Implement records and score/outcome policy**

`derive_score(rubric, scores)` validates exact criterion coverage and returns:

```python
(sum(criterion.weight * score.score for ...) + 50) // 100
```

`outcome_for_score()` returns pass at 80, partial at 40, retry below 40, and rejects bool/non-integer/out-of-range input.

- [ ] **Step 4: Write and implement best-evidence progress tests**

`best_independent_scores(campaign, evidence)` ignores non-independent evidence and returns the maximum independent score per mission. `runtime_progress()` calculates weighted campaign-goal progress from those maxima with half-up integer rounding. `render_runtime_progress(outcome, statement, progress, next_label)` returns exactly one status emoji/header, statement, ten-segment floor bar, and `Next:` line. Assert 0%, 9%, 10%, 40%, 99%, and 100% bar boundaries.

- [ ] **Step 5: Write and implement deterministic next-action tests**

`select_next_action(campaign, plans, roadmap, completed_review_phase_ids,
current_session, outcome)` obeys this priority. This explicit input boundary
keeps `runtime.py` independent of `storage.py` and prevents an import cycle:

1. Retry outcome or prerequisite-support adjustment -> same mission prerequisite support.
2. Partial -> same mission focused retry.
3. `REVIEW_DUE` missions in roadmap order.
4. Required unmet prerequisites then critical missions in roadmap order.
5. Goal ready when all critical missions and their prerequisites are demonstrated and no review is due.

Enrichment missions do not block goal readiness. Planned phase reviews use
`completed_review_phase_ids`; schedule demonstrated critical missions once
before advancing past a phase marked `planned_review_after`. The pure result
also identifies the target roadmap phase so the service can atomically advance
`active_phase_id` when the selected mission belongs to the next phase.

- [ ] **Step 6: Run focused and full tests**

Run: `python -m pytest tests/test_runtime.py tests/test_assessment.py tests/test_roadmaps.py -v`

Run: `python -m pytest -q`

Expected: all pass.

- [ ] **Step 7: Commit pure runtime policy**

```bash
git add src/langcampaign/runtime.py src/langcampaign/__init__.py tests/test_runtime.py
git commit -m "feat: add mission runtime policy"
```

---

### Task 2: Schema-v5 runtime persistence

**Files:**
- Modify: `src/langcampaign/storage.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Changes `CampaignState` additively with `revision: int = 0`, `active_session: ActiveMissionSession | None = None`, `mission_attempts: tuple[MissionAttemptRecord, ...] = ()`, and `completed_review_phase_ids: tuple[str, ...] = ()`.
- Produces conversion helpers for every Task 1 runtime record.
- New saves use schema version 5; versions 1–4 load with the exact defaults above.

- [ ] **Step 1: Write failing version-5 round-trip tests**

Build a state containing an active `check_ready` session, two attempt records, completed phase review, and revision 7. Save/reload equality must hold and the JSON envelope must contain:

```json
{
  "schema_version": 5,
  "revision": 7,
  "active_session": {"mission_id": "reply", "attempt_number": 3},
  "mission_attempts": [],
  "completed_review_phase_ids": ["phase-1"]
}
```

The abbreviated values above identify required top-level shape; assert every nested field in the actual test.

- [ ] **Step 2: Write migration and corruption tests**

For representative version 1, 2, 3, and 4 fixtures assert revision 0, no session, empty attempt records, and empty completed-review IDs. Assert that loading does not alter file bytes and first save produces version 5. Reject bool/negative revision, mutable runtime tuples, duplicate attempt identities, attempt records for unknown missions, active sessions for unknown missions, mismatched latest outcome/checkpoint, unknown completed phase IDs, malformed enums, naive timestamps, and incomplete nested content.

- [ ] **Step 3: Run storage tests and observe RED**

Run: `python -m pytest tests/test_storage.py -v`

Expected: failures because schema 5 and runtime fields are absent.

- [ ] **Step 4: Implement additive schema-v5 conversion**

Add `CAMPAIGN_RUNTIME_SCHEMA_VERSION = 5`, include it in `SUPPORTED_SCHEMA_VERSIONS`, serialize the exact runtime records, and wrap all malformed persisted runtime data as `CampaignStorageError`. Preserve legacy public conversion behavior.

`CampaignState.__post_init__` validates exact tuple boundaries, unique attempt identities, known mission/phase references, and that session attempt number is greater than every completed record for that mission unless the session itself is assessed and has the matching stored record.

- [ ] **Step 5: Run focused and full tests**

Run: `python -m pytest tests/test_storage.py tests/test_content_state_flow.py tests/test_campaign_lifecycle_flow.py -v`

Run: `python -m pytest -q`

Expected: all pass, including every historical schema.

- [ ] **Step 6: Commit schema v5**

```bash
git add src/langcampaign/storage.py src/langcampaign/__init__.py tests/test_storage.py
git commit -m "feat: persist mission runtime state"
```

---

### Task 3: Locked repository mutation and runtime services

**Files:**
- Modify: `src/langcampaign/learners.py`
- Create: `src/langcampaign/runtime_service.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/test_learners.py`
- Create: `tests/test_runtime_service.py`

**Interfaces:**
- Produces `RuntimeErrorCode`, `MissionRuntimeError(code, message, issues=())`, `ContentIssue`, `ContentValidationResult`, and `RuntimeSnapshot`.
- Produces repository function `mutate_learner_campaign(root, learner_id, campaign_id, expected_revision, transform, *, idempotent_if=None) -> CampaignState`.
- Produces services `validate_mission_content()`, `mission_status()`, `start_mission()`, `advance_mission()`, `adjust_difficulty()`, and `submit_assessment()`.

- [ ] **Step 1: Write failing locked-mutation tests**

Test that `mutate_learner_campaign`:

- opens `.state.lock` beneath the already-open campaign directory with `O_NOFOLLOW | O_CREAT | O_RDWR` and mode `0o600`;
- verifies the lock entry is a regular file;
- takes `fcntl.flock(fd, LOCK_EX)` on POSIX;
- reloads state only after locking;
- calls `idempotent_if(current)` before revision comparison and returns current unchanged when true;
- otherwise raises a typed revision conflict on mismatch;
- calls the transform once, replaces revision with current+1, saves through `save_campaign_state_at`, and releases the lock;
- rejects symlink/FIFO lock entries and leaves state unchanged on transform/save failure.

Use deterministic two-writer tests: both read revision 0, the first mutation succeeds at 1, and the second receives current revision 1 without overwriting.

- [ ] **Step 2: Run learner tests and observe RED**

Run: `python -m pytest tests/test_learners.py -v`

Expected: missing mutation API failures.

- [ ] **Step 3: Implement descriptor-confined compare-and-swap**

Keep path normalization and campaign selection in `learners.py`. Do not use a path-based lock after validation. On non-POSIX systems where `fcntl` is unavailable, protect in-process mutations with a keyed `threading.Lock`; document that cross-process locking is POSIX-only while atomic replace remains portable.

- [ ] **Step 4: Write failing content/status/start tests**

Content validation accepts only candidate numbers 1/2 and returns ordered `ContentIssue(field, code, message)` records. Candidate 1 invalid returns correction allowed; candidate 2 invalid does not. `mission_status` must not create a session or change file bytes/revision. `start_mission` requires the active campaign, selected next mission, valid content matching the mission, and expected revision; it creates attempt 1 or max+1.

- [ ] **Step 5: Write failing checkpoint/adjustment tests**

`advance_mission` permits teaching -> guided practice -> check ready. It rejects skips, stale revision/attempt, and mismatched missions. When `content_refresh_required` is true, guided -> check ready requires a newly validated replacement `MissionContent`; otherwise replacement content is rejected. `adjust_difficulty` replaces the pending adjustment; at check ready it returns to guided practice and sets content refresh required; adjustment is consumed at the next check-ready transition and resets after assessment.

- [ ] **Step 6: Write failing assessment/idempotency/review tests**

Freeze/inject `now()` in tests. `submit_assessment` requires check ready, exact
criterion coverage, independent true, and no timestamp. Assert derived boundary
outcomes at 39/40/79/80, atomic evidence plus attempt plus assessed session plus
persisted next action, best-credit preservation, review-due behavior, one-time
phase reviews, atomic `active_phase_id` advancement when a selected mission
crosses a roadmap boundary, and goal-ready without lifecycle completion.

Retry the identical request with stale revision and assert the original snapshot, unchanged bytes/revision, and one evidence record. Change one criterion and assert `duplicate_conflict`. Inject save failure and assert no result is claimed or persisted.

- [ ] **Step 7: Implement runtime services minimally**

All services return a frozen `RuntimeSnapshot` containing `revision`, `session`, `progress`, `rendered_progress`, and `next_action`. `mission_status` uses `select_campaign` and additionally verifies the campaign is active through the learner index. Mutations call only `mutate_learner_campaign` and pure Task 1 policy.

- [ ] **Step 8: Run focused, concurrency, and full tests**

Run: `python -m pytest tests/test_learners.py tests/test_runtime_service.py -v`

Run: `python -m pytest -q`

Expected: all pass.

- [ ] **Step 9: Commit services**

```bash
git add src/langcampaign/learners.py src/langcampaign/runtime_service.py src/langcampaign/__init__.py tests/test_learners.py tests/test_runtime_service.py
git commit -m "feat: add resumable mission runtime services"
```

---

### Task 4: Runtime JSON boundary, end-to-end flow, latency, and learner docs

**Files:**
- Modify: `src/langcampaign/cli.py`
- Modify: `tests/fixtures.py`
- Modify: `tests/test_cli.py`
- Create: `tests/test_mission_runtime_flow.py`
- Modify: `README.md`

**Interfaces:**
- Adds `validate-mission-content`, `mission-status`, `start-mission`, `advance-mission`, `adjust-difficulty`, and `submit-assessment` for an exact total of fifteen commands.
- Preserves `CommandResult.to_dict()` success shape; runtime failures add structured `error.code` while legacy error strings remain backward compatible.

- [ ] **Step 1: Write exact request/response fixture builders**

Add `mission_content_payload(candidate_number=1)` with all compact content and rubric fields. Add builders for common repository identity fields and criterion scores. Requests use:

```json
{"learner_id":"qasim","campaign_id":"campaign-a","expected_revision":0,"mission_id":"reply","attempt_number":1}
```

`start-mission` additionally contains `content`; `advance-mission` may contain `replacement_content`; `adjust-difficulty` contains `adjustment`; `submit-assessment` contains `criterion_scores`, `independent`, `modality`, and `result_statement`. No runtime request accepts `assessed_at`.

- [ ] **Step 2: Write failing command-contract tests**

Assert exact fifteen-command registration. Assert these envelopes:

```json
{"success":true,"data":{"valid":true,"content":{},"correction_allowed":false}}
{"success":true,"data":{"revision":1,"session":{},"progress":{"percent":0,"bar":"░░░░░░░░░░"},"next_action":null}}
{"success":false,"error":{"code":"revision_conflict","message":"...","current_revision":2}}
{"success":false,"error":{"code":"invalid_content","message":"...","issues":[{"field":"rubric","code":"invalid_weight_total","message":"..."}]}}
```

Legacy failures keep `{"success": false, "error": "message"}`. Runtime domain failures use the error object. Assert every stable error code is reachable or directly mapped, malformed input never becomes an internal exception, and injected programmer faults propagate.

- [ ] **Step 3: Implement narrow CLI parsing and serialization**

Add exact parsers for content, criteria, expected revision, attempt number, and adjustment. Reject booleans as integers, unknown fields where ambiguity would be unsafe, caller timestamps, missing identity, and inconsistent replacement content. Serialize enums as values and datetimes as ISO 8601 only in responses.

- [ ] **Step 4: Write and implement full learner-flow tests**

Exercise through `run_command` and a fresh subprocess:

```text
setup -> validate content -> status is null -> start -> teaching
-> guided -> check ready -> submit partial -> persisted focused retry
-> fresh process status -> start retry -> too easy -> adjusted check
-> submit pass -> persisted next mission -> pause/resume unchanged
-> finish critical missions/review -> goal ready -> explicit complete
```

Also prove invalid candidate 1 permits one correction, invalid candidate 2 is terminal, identical assessment retry is idempotent, a stale writer fails, and guided-practice content survives a fresh process.

- [ ] **Step 5: Add representative local latency coverage**

Measure 100 read-only status calls and 25 mutation cycles in a temporary local repository after warm-up. Use generous thresholds of 100 ms median per operation and 1 second total for each batch to detect accidental model/network/process sleeps without asserting microbenchmarks. Mark no test as network-dependent.

- [ ] **Step 6: Update README truthfully**

Describe the mission runtime and show one concise example. State that the deterministic engine now supports checkpoints, rubric-derived assessment, evidence, adaptation, progress, and resume, while the installable Codex teaching skill remains the next milestone. Do not claim ChatGPT, voice, hosted persistence, or a finished consumer UI.

- [ ] **Step 7: Run milestone verification**

Run:

```bash
python -m pytest tests/test_runtime.py tests/test_storage.py tests/test_learners.py tests/test_runtime_service.py tests/test_cli.py tests/test_mission_runtime_flow.py -v
python -m pytest -q
python -m pip install -e '.[test]'
python -m compileall -q src
python -m pytest tests/test_cli.py::test_missing_campaign_runtime_smoke -v
git diff --check
```

The smoke test runs the subprocess, asserts exit 2, parses its one JSON
envelope, and asserts code `campaign_not_found`. All verification commands exit
0 and the full suite passes.

- [ ] **Step 8: Commit command/runtime milestone**

```bash
git add src/langcampaign/cli.py tests/fixtures.py tests/test_cli.py tests/test_mission_runtime_flow.py README.md
git commit -m "feat: add lean mission learning flow"
```

## Milestone review contract

After all four tasks are committed, perform one independent whole-branch review. It must verify every revised-spec critique: exact command shapes, read-only status, persisted content/next action, rubric scoring, honest independence boundary, revision locking, assessment idempotency, adjustment lifecycle, review/attempt/completion semantics, authoritative timestamps, v1–v4 migration, rounding, error codes, correction protocol, fresh-session recovery, compatibility, and latency design.

If the review finds issues, send the complete list through one consolidated fix wave, run one scoped re-review, and stop rather than starting a second fix wave if a load-bearing issue remains.
