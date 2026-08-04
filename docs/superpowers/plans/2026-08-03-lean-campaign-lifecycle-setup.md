# Lean Campaign Lifecycle and Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fast defaulted setup, persisted prior-knowledge context, and crash-resilient active/paused/completed campaign lifecycle operations without allowing in-place goal changes.

**Architecture:** Campaign content remains in each versioned `CampaignState`. A separate, atomic learner index stores one active campaign identifier and completed identifiers; every other stored campaign is paused. Goal transitions create a new campaign, transfer only explicitly mapped evidence, then atomically switch the active pointer, so the old campaign remains active if activation fails.

**Tech Stack:** Python 3.11+, frozen dataclasses, standard-library JSON and descriptor-based atomic persistence, existing CLI/repository boundaries, pytest 8+.

## Global Constraints

- The learner-facing MVP uses one fixed concise style; underlying legacy coaching fields remain schema-compatible but are not exposed as choices.
- Setup silently defaults to Flexible, Balanced, and Supportive unless a target date requires a Targeted campaign.
- Prior-knowledge self-report influences future generation but never becomes assessment evidence.
- A materially new goal creates a new campaign; existing campaign goals are never mutated.
- Exactly one campaign may be active for a learner. Other non-completed campaigns are paused.
- Resuming a paused campaign atomically changes the active pointer and preserves both campaigns' state.
- Only evidence explicitly mapped from an old mission identifier to a new mission identifier transfers.
- A failed transition must leave the previous campaign active. A newly created but unactivated campaign may remain paused and resumable.
- Learner JSON remains repository-local, versioned, validated, descriptor-confined, and atomically written.
- Schema versions 1–3 remain loadable.
- No runtime dependency may be added.
- Python 3.11 remains the minimum supported version.
- Use the lighter milestone workflow: one implementer for all tasks, one milestone review, at most one consolidated fix wave.

## File map

- `src/langcampaign/storage.py` — schema-version 4 prior-knowledge field and learner-index serialization.
- `src/langcampaign/learners.py` — lifecycle summaries, learner-index persistence, activation, completion, resume, and transition services.
- `src/langcampaign/cli.py` — defaulted setup plus lifecycle command envelopes.
- `src/langcampaign/__init__.py` — public lifecycle exports.
- `tests/test_storage.py` — schema-v4 round-trip and v1–v3 migration.
- `tests/test_learners.py` — index fallback, lifecycle, transition, evidence transfer, and failure behavior.
- `tests/test_cli.py` — fast setup defaults and lifecycle command contracts.
- `tests/test_campaign_lifecycle_flow.py` — end-to-end setup, transition, resume, and fresh-load acceptance.
- `README.md` — current lifecycle/setup status only after behavior exists.

---

### Task 1: Schema-version 4 learner context and index records

**Files:**
- Modify: `src/langcampaign/storage.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Changes `CampaignState` additively with `prior_knowledge: str = ""`.
- Produces `CampaignLifecycle`, `LearnerCampaignIndex`, `learner_index_to_dict()`, and `learner_index_from_dict()`.
- New state saves use schema version 4; versions 1–3 load with empty prior knowledge.

- [ ] **Step 1: Write failing schema and immutable-index tests**

Add tests equivalent to:

```python
def test_version_four_round_trips_prior_knowledge(tmp_path):
    state = CampaignState(
        new_campaign("Text friends", "Spanish"),
        learner_id="qasim",
        prior_knowledge="Can read casual messages but rarely speaks.",
    )
    path = tmp_path / "state.json"
    save_campaign_state(path, state)
    assert load_campaign_state(path) == state
    assert json.loads(path.read_text())["schema_version"] == 4


def test_version_three_migrates_with_empty_prior_knowledge(tmp_path):
    payload = existing_version_three_payload()
    path = tmp_path / "state.json"
    path.write_text(json.dumps(payload))
    assert load_campaign_state(path).prior_knowledge == ""


def test_learner_index_is_immutable_and_has_one_active_campaign():
    index = LearnerCampaignIndex("campaign-a", ("campaign-b",))
    assert index.lifecycle_for("campaign-a") is CampaignLifecycle.ACTIVE
    assert index.lifecycle_for("campaign-b") is CampaignLifecycle.COMPLETED
    assert index.lifecycle_for("campaign-c") is CampaignLifecycle.PAUSED
```

Also reject non-string prior knowledge, mutable/non-string completed IDs,
duplicate completed IDs, and an active ID also marked completed.

- [ ] **Step 2: Run focused tests and observe RED**

Run: `python -m pytest tests/test_storage.py -v`

Expected: failures because schema version 4, `prior_knowledge`, and index records do not exist.

- [ ] **Step 3: Implement schema version 4 and lifecycle records**

Add the exact public records:

```python
class CampaignLifecycle(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass(frozen=True)
class LearnerCampaignIndex:
    active_campaign_id: str | None = None
    completed_campaign_ids: tuple[str, ...] = ()

    def lifecycle_for(self, campaign_id: str) -> CampaignLifecycle:
        if campaign_id == self.active_campaign_id:
            return CampaignLifecycle.ACTIVE
        if campaign_id in self.completed_campaign_ids:
            return CampaignLifecycle.COMPLETED
        return CampaignLifecycle.PAUSED
```

Validate exact tuple/string boundaries and uniqueness. Add
`CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION = 4`, write `prior_knowledge`, and
default it to `""` for versions 1–3. Index conversion uses:

```json
{
  "schema_version": 1,
  "active_campaign_id": "campaign-a",
  "completed_campaign_ids": ["campaign-b"]
}
```

Index parsing must reject unknown/malformed versions with
`CampaignStorageError`.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m pytest tests/test_storage.py tests/test_campaign_flow.py -v`

Expected: all focused tests pass, including v1–v3 compatibility.

Run: `python -m pytest -q`

Expected: complete suite passes.

- [ ] **Step 5: Commit the state records**

```bash
git add src/langcampaign/storage.py src/langcampaign/__init__.py tests/test_storage.py
git commit -m "feat: add learner campaign lifecycle state"
```

---

### Task 2: Atomic lifecycle and campaign-transition repository

**Files:**
- Modify: `src/langcampaign/storage.py`
- Modify: `src/langcampaign/learners.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/test_learners.py`

**Interfaces:**
- Produces `CampaignSummary(id: str, goal: str, lifecycle: CampaignLifecycle)`.
- Produces `EvidenceTransfer(source_mission_id: str, target_mission_id: str)`.
- Produces `create_and_activate_campaign()`, `list_campaign_summaries()`,
  `select_active_campaign()`, `activate_campaign()`, `complete_campaign()`, and
  `transition_campaign()`.
- Preserves existing `list_learner_campaigns()` and `select_campaign()` behavior.

- [ ] **Step 1: Write failing lifecycle and transition tests**

Cover these exact behaviors:

```python
def test_first_campaign_becomes_active_and_second_is_paused(tmp_path):
    first = state("Text friends")
    second = state("Read posts")
    create_and_activate_campaign(tmp_path, first)
    save_learner_campaign(tmp_path, second, create_only=True)
    assert list_campaign_summaries(tmp_path, first.learner_id) == (
        CampaignSummary(first.campaign.id, "Text friends", CampaignLifecycle.ACTIVE),
        CampaignSummary(second.campaign.id, "Read posts", CampaignLifecycle.PAUSED),
    )


def test_resume_switches_active_pointer_without_rewriting_campaign_state(tmp_path):
    # Save two campaigns, activate first, capture both state.json byte strings,
    # activate second, and assert bytes are unchanged and statuses swap.


def test_transition_maps_only_explicit_evidence_and_pauses_previous(tmp_path):
    # Source has evidence for source-a and source-b. Map source-a -> target-a.
    # Assert new state contains only evidence for target-a, old state is intact,
    # new campaign is active, and old campaign is paused.


def test_failed_transition_keeps_previous_campaign_active(tmp_path, monkeypatch):
    # Inject index-publication failure after the new campaign is created.
    # Assert old campaign remains active and the new campaign is merely paused.
```

Also cover completed campaigns refusing activation, missing active campaign,
malformed index storage, index IDs that reference missing campaigns, and legacy
repositories with no index: zero campaigns yields no active campaign; exactly
one campaign is treated as active and materializes an index on the next write;
multiple campaigns without an index require explicit activation.

- [ ] **Step 2: Run learner tests and observe RED**

Run: `python -m pytest tests/test_learners.py -v`

Expected: import/attribute failures for the new lifecycle services.

- [ ] **Step 3: Implement descriptor-confined learner-index persistence**

Store `index.json` directly under the normalized learner directory. Add storage
helpers that read a regular file with `O_NOFOLLOW` and atomically replace a
temporary file through the already-held learner directory descriptor. Reuse the
existing flush/fsync/replace/cleanup policy.

Do not infer lifecycle by rewriting every `state.json`. The index is the single
source of lifecycle truth:

- `active_campaign_id` identifies the active campaign.
- `completed_campaign_ids` identifies completed campaigns.
- Every other valid campaign directory is paused.

The index writer validates that every referenced ID exists as a regular stored
campaign before publication.

`create_and_activate_campaign(root, state)` first stores the campaign with
create-only semantics and then publishes the active pointer. It is the setup
path for a learner's first campaign and the non-transition path for adding a
new campaign. If index publication fails, the stored campaign remains paused
and any previously active campaign remains active.

- [ ] **Step 4: Implement transition and evidence mapping**

Add exact records:

```python
@dataclass(frozen=True)
class CampaignSummary:
    id: str
    goal: str
    lifecycle: CampaignLifecycle


@dataclass(frozen=True)
class EvidenceTransfer:
    source_mission_id: str
    target_mission_id: str
```

`transition_campaign(root, learner_id, new_state, transfers)` must:

1. Load the current active state.
2. Validate that `new_state.learner_id` normalizes to the same learner.
3. Require `new_state.assessment_evidence` to be empty so transferred evidence
   cannot be confused with caller-supplied evidence.
4. Validate every source mission exists in the old campaign and every target
   mission exists in the new campaign.
5. Reject duplicate source or target mappings.
6. Copy all assessment evidence for explicitly mapped sources using
   `dataclasses.replace(evidence, mission_id=target_id)`; copy nothing else.
   Preserve every other evidence field and leave the source state unchanged.
7. Create the new campaign with create-only semantics while leaving the old
   index unchanged.
8. Atomically update only `index.json` to activate the new campaign.

If step 8 fails, propagate the error. The old index remains authoritative, so
the prior campaign stays active and the new stored campaign is paused.

- [ ] **Step 5: Run focused, concurrency, and full tests**

Run: `python -m pytest tests/test_learners.py tests/test_storage.py -v`

Expected: lifecycle, transition, legacy fallback, descriptor safety, and all
existing repository/storage tests pass.

Run: `python -m pytest -q`

Expected: complete suite passes.

- [ ] **Step 6: Commit lifecycle services**

```bash
git add src/langcampaign/storage.py src/langcampaign/learners.py src/langcampaign/__init__.py tests/test_learners.py
git commit -m "feat: add resumable campaign lifecycle"
```

---

### Task 3: Fast setup and lifecycle command boundary

**Files:**
- Modify: `src/langcampaign/cli.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/fixtures.py`
- Modify: `tests/test_cli.py`
- Create: `tests/test_campaign_lifecycle_flow.py`
- Modify: `README.md`

**Interfaces:**
- Existing `setup` accepts optional `prior_knowledge` and silently applies fixed defaults.
- Adds commands `list-campaign-status`, `transition-campaign`, `resume-campaign`, and `complete-campaign`.
- Existing five commands and their successful envelope shapes remain backward compatible.
- Extracts a pure `_state_from_setup_payload(payload) -> CampaignState` parser
  used by both setup and transition; only the command handlers persist state.

- [ ] **Step 1: Write failing fast-setup command tests**

Remove `campaign_type` from `setup_payload()` and add:

```python
"prior_knowledge": "Can read casual messages but rarely speaks."
```

Assert setup succeeds with no curriculum/coaching/campaign-type fields and the
stored state has:

```python
CampaignType.FLEXIBLE
CurriculumScope.BALANCED
CoachingStyle.SUPPORTIVE
"Can read casual messages but rarely speaks."
```

Add a targeted case where `target_date` alone selects `CampaignType.TARGETED`.
An explicitly supplied legacy `campaign_type` remains accepted when consistent
with `target_date`, but curriculum/coaching fields are internal compatibility
inputs and are not returned or requested by learner-facing docs.
Parse `prior_knowledge` as a string, strip surrounding whitespace, permit an
empty result, and reject every non-string value.

- [ ] **Step 2: Write failing lifecycle-command and acceptance tests**

Command envelopes are:

```json
{"success": true, "data": {"campaigns": [{"id": "...", "goal": "...", "status": "active"}]}}
{"success": true, "data": {"active_campaign_id": "..."}}
{"success": true, "data": {"completed_campaign_id": "..."}}
```

`transition-campaign` consumes the normal setup payload plus:

```json
{
  "source_campaign_id": "old-id",
  "evidence_transfers": [
    {"source_mission_id": "old-mission", "target_mission_id": "new-mission"}
  ]
}
```

It constructs and validates the new state before calling
`transition_campaign()`. Add subprocess/error-envelope coverage for missing,
completed, duplicate, mismatched learner, invalid mapping, and injected
programmer-fault paths.

The end-to-end test must prove:

```text
defaulted setup → active first campaign → evidence-bearing transition
→ old paused/new active → fresh command reload → resume old
→ old active/new paused with both state files unchanged
```

- [ ] **Step 3: Run CLI/lifecycle tests and observe RED**

Run: `python -m pytest tests/test_cli.py tests/test_campaign_lifecycle_flow.py -v`

Expected: failures for missing defaults, lifecycle commands, and transition flow.

- [ ] **Step 4: Implement fixed defaults and narrow command handlers**

Infer campaign type as:

```python
raw_date = raw_campaign.get("target_date")
inferred_type = "targeted" if raw_date is not None else "flexible"
campaign_type = CampaignType(raw_campaign.get("campaign_type", inferred_type))
```

Reject a Flexible campaign with a date or a Targeted campaign without one
through existing `CampaignSettings` validation. Parse `prior_knowledge` as an
optional string defaulting to `""` and store it only in `CampaignState`.

Add the four handlers using only the public learner services. Catch typed
repository/input errors narrowly; arbitrary dependency programmer faults must
propagate. Preserve exactly-one-JSON-envelope argparse behavior.

Update the existing command-registration assertion from the original exact
five-command set to the new exact nine-command set, while keeping every
original command and success envelope unchanged.

- [ ] **Step 5: Update learner documentation**

Update only Current status and setup/lifecycle examples to say these behaviors
are now implemented:

- short setup applies silent defaults;
- prior knowledge calibrates future missions but is not credited as evidence;
- one campaign is active, old goals transition to paused campaigns, and paused
  campaigns can be resumed;
- installable Codex teaching workflows and generated mission conversations are
  still future work.

- [ ] **Step 6: Run milestone verification**

Run:

```bash
python -m pytest tests/test_cli.py tests/test_learners.py tests/test_storage.py tests/test_campaign_lifecycle_flow.py -v
python -m pytest -q
python -m pip install -e '.[test]'
python -m compileall -q src
python -m langcampaign list-campaign-status --learners-root learners --learner-id smoke-test
git diff --check
```

Expected: all tests pass, installation/compilation succeed, smoke output is one
successful JSON envelope with an empty campaign list, and diff check is clean.

- [ ] **Step 7: Commit the command milestone**

```bash
git add src/langcampaign/cli.py src/langcampaign/__init__.py tests/fixtures.py tests/test_cli.py tests/test_campaign_lifecycle_flow.py README.md
git commit -m "feat: add lean campaign setup and transitions"
```

## Milestone review contract

After all three tasks are committed, perform one independent milestone review
over the complete branch diff. The reviewer must check schema migration,
descriptor confinement, learner-index authority, transition failure behavior,
explicit evidence mapping, defaulted setup, programmer-fault propagation,
CLI envelopes, documentation truthfulness, and end-to-end resume behavior.

If the review finds issues, dispatch at most one consolidated fix wave, run one
scoped re-review, then either merge or report any residual load-bearing issue.
