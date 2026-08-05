# Codex Delivery and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship LangCampaign as a repository-installable Codex plugin that safely runs the existing local campaign engine through a versioned adapter, supports the complete learner workflow, and passes deterministic and live release evaluation.

**Architecture:** A skills-only plugin owns invocation and teaching policy; `scripts/langcampaign_adapter.py` exposes one platform-neutral JSON protocol; focused profile, receipt, and data-management modules resolve identity and safe persistence; and the existing public engine remains authoritative for campaign and mission state. Generated language stays in Codex, while validated compact mission content, checkpoints, evidence, and next actions stay local and resumable.

**Tech Stack:** Python 3.11+, standard library only at runtime, Codex plugin manifest and repository marketplace metadata, JSON Schema documents, frozen dataclasses/`StrEnum`, atomic filesystem persistence, pytest 8+.

## Global Constraints

- Codex is the only delivery target in this milestone; ChatGPT and Claude adapters remain post-MVP.
- The plugin is skills-only: no MCP server, hosted service, authentication, telemetry, or runtime dependency.
- Installation is from `qasim-a/langcampaign` through the supported Codex Git marketplace flow; no manual clone or `pip install`.
- Python 3.11 is the minimum; macOS, Linux, and Windows are supported.
- The adapter loads only the bundled `src/langcampaign` package relative to its own installed path, never the current directory or ambient `PYTHONPATH`.
- Personal storage is outside repositories and has one automatic opaque local learner profile.
- Campaign lifecycle has exactly `active`, `paused`, and `completed`; at most one campaign is active.
- An existing campaign goal is immutable; materially new goals use transition and preserve the old campaign as paused.
- Normal learner messages use at most one model generation and one committed mutation; invalid generated content gets one bounded correction generation.
- Full transcripts and model reasoning are never persisted.
- Every mutation is revision-safe, cross-process locked, atomic, and idempotent across timeout retries.
- Caller timestamps are never authoritative.
- Rubric criterion scores are integers 0–100, weights total 100, and the engine derives the weighted score and outcome.
- No-hints checks cannot receive material linguistic help; accidental help returns to practice without recording evidence.
- Learner presentation uses restrained colored status emoji and the existing ten-segment progress bar.
- Export is consistent and non-overwriting; reset is explicit, backed up, and recoverable rather than destructive.
- Local adapter work should normally complete in milliseconds and must never make network calls.
- All commits use `Qasim Ali <qasimali0630@gmail.com>` as author.
- Use the approved lighter workflow: one implementer per task, one whole-milestone review, and one consolidated fix wave unless a consequential defect remains.

## File map

- Create `.agents/plugins/marketplace.json` — repository marketplace named `langcampaign`, pointing at `./`.
- Create `.codex-plugin/plugin.json` — skills-only plugin identity, version, and compatibility metadata.
- Create `skills/langcampaign/SKILL.md` — invocation boundary and complete learner orchestration.
- Create `skills/langcampaign/agents/openai.yaml` — Codex-facing display metadata and starter prompts.
- Create `workflow/learner-policy.md` — setup, lifecycle, goal-transition, and no-hints rules.
- Create `workflow/generation-contracts.md` — campaign/content/rubric generation and one-correction contract.
- Create `workflow/presentation.md` — compact response templates, emoji, progress, and error presentation.
- Create `workflow/examples.md` — canonical setup, resume, assessment, pause, transition, and recovery transcripts.
- Create `scripts/check_install.py` — executable clean-install and environment probe.
- Create `scripts/langcampaign_adapter.py` — one-request/one-response protocol entry point and bundled import bootstrap.
- Create `src/langcampaign/profile.py` — personal data-root resolution, profile schema, permissions, and profile locking.
- Create `src/langcampaign/protocol.py` — protocol envelopes, operation names, typed errors, dispatch, and exit codes.
- Create `src/langcampaign/receipts.py` — persistent bounded operation receipt ledger.
- Create `src/langcampaign/data_management.py` — upgrade backups, export, and recoverable reset.
- Create `schemas/protocol-envelope-v1.json` and `schemas/operations/*.json` — exact machine-readable adapter contracts.
- Create `evaluation/README.md`, `evaluation/scenario.schema.json`, and `evaluation/scenarios/*.json` — reproducible release scenarios and rubric.
- Create `.github/workflows/test.yml` — supported OS/Python and subprocess concurrency matrix.
- Modify `src/langcampaign/learners.py` — portable cross-process lock, explicit pause, and stable desired-state lifecycle mutations.
- Modify `src/langcampaign/runtime_service.py` — explicit `return_to_practice` mutation.
- Modify `src/langcampaign/cli.py` — public pause and return-to-practice engine commands while preserving existing commands.
- Modify `src/langcampaign/storage.py` — supported-version inspection hooks needed for safe backup/migration orchestration.
- Modify `src/langcampaign/__init__.py` — export only the new public engine/domain interfaces.
- Modify `README.md` — concise learner installation and usage guide.
- Create `tests/test_profile.py`, `tests/test_protocol.py`, `tests/test_receipts.py`, `tests/test_data_management.py`, `tests/test_plugin_package.py`, `tests/test_adapter_subprocess.py`, and `tests/test_evaluation_contract.py`.
- Modify `tests/test_learners.py`, `tests/test_runtime_service.py`, `tests/test_cli.py`, and `tests/test_mission_runtime_flow.py`.

---

### Task 1: Repository plugin package, bundled import, and local profile

**Files:**
- Create: `.agents/plugins/marketplace.json`
- Create: `.codex-plugin/plugin.json`
- Create: `scripts/check_install.py`
- Create: `scripts/langcampaign_adapter.py`
- Create: `src/langcampaign/profile.py`
- Modify: `src/langcampaign/__init__.py`
- Create: `tests/test_plugin_package.py`
- Create: `tests/test_profile.py`
- Create: `tests/test_adapter_subprocess.py`

**Interfaces:**
- Produces `Profile(profile_version: int, learner_id: str, created_at: datetime)`.
- Produces `resolve_data_root(platform, environ, home) -> Path`, `load_or_create_profile(root, *, now=None, token_bytes=None) -> Profile`, and `profile_lock(root)`.
- Produces adapter bootstrap `_bundled_src(script_file: Path) -> Path` and install probe operation used by every later task.

- [ ] **Step 1: Write failing marketplace and manifest tests**

Assert `.agents/plugins/marketplace.json` has top-level name `langcampaign`, one `AVAILABLE`/`ON_INSTALL` language-learning entry named `langcampaign`, and `source.path == "./"`. Assert `.codex-plugin/plugin.json` has an explicit semantic version, descriptive name, and a bundled `skills/langcampaign` entry with no MCP or app dependency.

- [ ] **Step 2: Run package tests and observe RED**

Run: `PYTHONPATH=src python -m pytest tests/test_plugin_package.py -v`

Expected: FAIL because the plugin package files do not exist.

- [ ] **Step 3: Add the minimal valid repository marketplace and plugin manifest**

Use the exact repository layout from the approved design. Validate both JSON files in tests and prohibit absolute or parent-traversing plugin paths.

- [ ] **Step 4: Write failing data-root and profile tests**

Cover macOS `~/Library/Application Support/LangCampaign`, Linux XDG/fallback, Windows `%LOCALAPPDATA%\LangCampaign`, missing Windows environment, fixed-clock UTC creation time, secure-random stable learner ID, atomic reuse, mode `0700`/`0600` where enforceable, corrupt JSON, unknown profile version, symlinked root/profile, concurrent first creation, and no current-working-directory fallback.

```python
@dataclass(frozen=True)
class Profile:
    profile_version: int
    learner_id: str
    created_at: datetime
```

- [ ] **Step 5: Implement `profile.py` and run focused tests**

Use an opaque `secrets.token_hex(16)` learner ID, adapter-owned aware UTC clock, `additionalProperties`-style exact field checks, same-directory temporary write, `flush`, `os.fsync`, `os.replace`, and best-effort parent sync. Do not accept a learner ID or audit timestamp from the caller.

Run: `PYTHONPATH=src python -m pytest tests/test_profile.py -v`

Expected: PASS.

- [ ] **Step 6: Write failing clean-subprocess bundled-import tests**

Launch the copied plugin from an unrelated temporary working directory with `PYTHONPATH` set to a fake conflicting `langcampaign` package. Assert the script derives `<plugin>/src`, validates the manifest/package sentinel, imports the bundled module, reports its version/path in one JSON line, and fails safely for Python below 3.11, missing bundle files, or unsafe installation paths.

- [ ] **Step 7: Implement the bootstrap and non-destructive install probe**

In `scripts/langcampaign_adapter.py`, resolve `Path(__file__)`, set the exact bundled `src` as `sys.path[0]`, remove any previously loaded ambient `langcampaign` modules, import, and verify `Path(langcampaign.__file__).resolve().is_relative_to(bundled_src)`. Keep `check_install.py` a thin caller of the same probe rather than a second implementation.

- [ ] **Step 8: Verify and commit Task 1**

Run: `PYTHONPATH=src python -m pytest tests/test_plugin_package.py tests/test_profile.py tests/test_adapter_subprocess.py -v`

Run: `PYTHONPATH=src python -m pytest -q`

Expected: all pass.

```bash
git add .agents .codex-plugin scripts src/langcampaign/profile.py src/langcampaign/__init__.py tests/test_plugin_package.py tests/test_profile.py tests/test_adapter_subprocess.py
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: package LangCampaign for Codex"
```

---

### Task 2: Portable locking and explicit recovery mutations

**Files:**
- Modify: `src/langcampaign/learners.py`
- Modify: `src/langcampaign/runtime_service.py`
- Modify: `src/langcampaign/cli.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/test_learners.py`
- Modify: `tests/test_runtime_service.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_mission_runtime_flow.py`

**Interfaces:**
- Produces portable `exclusive_file_lock(descriptor: int)` used by learner, profile, receipt, and data-management locks.
- Produces `pause_campaign(root, learner_id, campaign_id, expected_revision) -> CampaignState`.
- Produces `return_to_practice(root, learner_id, campaign_id, expected_revision, mission_id, attempt_number) -> RuntimeSnapshot`.
- Adds engine commands `pause-campaign` and `return-to-practice` without changing the other fifteen commands.

- [ ] **Step 1: Write failing cross-process lock tests**

Spawn two real processes that enter the same lock. The first blocks inside the critical section; assert the second cannot enter until release. Run the same behavioral test on every CI OS. Add unit branches for POSIX `fcntl.flock` and Windows `msvcrt.locking`; remove the non-POSIX in-process-only fallback.

- [ ] **Step 2: Implement one portable lock primitive**

Keep the existing descriptor and regular-file checks. On Windows lock one byte after ensuring the lock file has at least one byte; always unlock in `finally`. Preserve the in-process keyed mutex only as an additional thread guard, not as the cross-process guarantee.

- [ ] **Step 3: Write failing pause tests**

Assert pause requires the active campaign and matching revision, increments the campaign revision exactly once, atomically changes lifecycle to `paused`, clears the index pointer, preserves runtime session/evidence/content, is a no-op success when already in the desired paused state, and conflicts when another campaign is active.

- [ ] **Step 4: Implement `pause_campaign` behind the lifecycle lock**

Reuse the descriptor-confined learner repository. Do not let the adapter edit `index.json`. The lifecycle and state publication must be one recoverable locked operation using the repository's existing rollback pattern.

- [ ] **Step 5: Write failing accidental-help recovery tests**

From `check_ready`, `return_to_practice` must require matching campaign/mission/attempt/revision, set `guided_practice`, set `content_refresh_required=True`, preserve the attempt number, add no assessment evidence or attempt record, and increment revision once. Identical replay at guided practice with refresh required is a no-op success.

- [ ] **Step 6: Implement the service and two CLI commands**

Map validation/domain failures to existing stable engine error objects. Caller timestamps remain forbidden. Update exact command-set tests from fifteen to seventeen.

- [ ] **Step 7: Verify and commit Task 2**

Run: `PYTHONPATH=src python -m pytest tests/test_learners.py tests/test_runtime_service.py tests/test_cli.py tests/test_mission_runtime_flow.py -v`

Run: `PYTHONPATH=src python -m pytest -q`

Expected: all pass.

```bash
git add src/langcampaign tests
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: add portable lifecycle recovery"
```

---

### Task 3: Versioned adapter protocol and exact operation schemas

**Files:**
- Create: `src/langcampaign/protocol.py`
- Modify: `scripts/langcampaign_adapter.py`
- Create: `schemas/protocol-envelope-v1.json`
- Create: `schemas/operations/check-install.json`
- Create: `schemas/operations/setup.json`
- Create: `schemas/operations/status.json`
- Create: `schemas/operations/list-campaigns.json`
- Create: `schemas/operations/show-roadmap.json`
- Create: `schemas/operations/validate-content.json`
- Create: `schemas/operations/transition.json`
- Create: `schemas/operations/resume.json`
- Create: `schemas/operations/pause.json`
- Create: `schemas/operations/complete.json`
- Create: `schemas/operations/start-mission.json`
- Create: `schemas/operations/advance-mission.json`
- Create: `schemas/operations/adjust-difficulty.json`
- Create: `schemas/operations/return-to-practice.json`
- Create: `schemas/operations/submit-assessment.json`
- Create: `schemas/operations/export.json`
- Create: `schemas/operations/reset.json`
- Create: `tests/test_protocol.py`
- Modify: `tests/test_adapter_subprocess.py`

**Interfaces:**
- Produces `Operation(StrEnum)`, `ProtocolErrorCode(StrEnum)`, `ProtocolRequest`, `ProtocolResponse`, `ProtocolFailure`, and `dispatch(request, context) -> ProtocolResponse`.
- Protocol input/output is the exact v1 envelope and closed operation/error sets from the design.

- [ ] **Step 1: Write failing envelope, schema, and stream tests**

Assert protocol version exactly `1`; UUID operation IDs on mutations; exact object keys; `additionalProperties: false`; 1 MiB stdin limit; invalid JSON/null recoverable ID; one UTF-8 JSON line on stdout; empty stderr for expected failures; redacted stderr for unexpected faults; and exit codes `0`, `2`, `3`, `4`, `70`.

- [ ] **Step 2: Implement protocol records, validation, and error mapping**

Read bounded bytes before decoding. Convert engine errors into only the closed v1 error set. Use `json.dumps(..., ensure_ascii=False, separators=(",", ":")) + "\n"`. Redirect or prohibit engine logging to stdout. Do not include raw learner content in exceptions or diagnostics.

- [ ] **Step 3: Write a failing test fixture for every operation schema**

For every design-table operation provide one minimal valid input/result fixture and invalid fixtures for missing required fields, extra fields, bool-as-int, unsafe IDs/paths, caller audit timestamps, invalid enums, overlong strings, and oversized collections. Validate schemas in tests with a small repository-owned standard-library checker; do not add `jsonschema` as a runtime dependency.

- [ ] **Step 4: Implement dispatch through public engine commands**

Adapter operation names remain platform-neutral. `status` is read-only and never starts a mission. Setup validates before its one create. Assessment passes exact rubric coverage and `independent=True`; the engine derives time, score, outcome, next action, and progress. Normalize all success data through schema-specific serializers.

- [ ] **Step 5: Verify and commit Task 3**

Run: `PYTHONPATH=src python -m pytest tests/test_protocol.py tests/test_adapter_subprocess.py tests/test_cli.py -v`

Run: `PYTHONPATH=src python -m pytest -q`

Expected: all pass and no subprocess writes extra stdout.

```bash
git add src/langcampaign/protocol.py scripts/langcampaign_adapter.py schemas tests/test_protocol.py tests/test_adapter_subprocess.py
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: add versioned adapter protocol"
```

---

### Task 4: Durable idempotency and crash-safe operation recovery

**Files:**
- Create: `src/langcampaign/receipts.py`
- Modify: `src/langcampaign/profile.py`
- Modify: `src/langcampaign/protocol.py`
- Modify: `src/langcampaign/learners.py`
- Create: `tests/test_receipts.py`
- Modify: `tests/test_protocol.py`
- Modify: `tests/test_learners.py`
- Modify: `tests/test_adapter_subprocess.py`

**Interfaces:**
- Produces `ReceiptLedger(receipt_version: int, completed: tuple[OperationReceipt, ...])` and `OperationReceipt(operation_id, operation, input_sha256, response)`.
- Produces `canonical_input_digest(operation, input_data) -> str`, `load_receipt`, and locked `record_receipt`/`replay_or_conflict` operations.
- State-changing protocol dispatch requires and preserves one UUID operation ID across retries.

- [ ] **Step 1: Write failing ledger validation and replay tests**

Assert canonical JSON uses sorted keys and compact separators, the SHA-256 excludes no semantic input fields, identical ID/input returns the exact stored response without dispatch, different input conflicts, the ledger retains the newest 256 completed receipts oldest-first, and symlink/corrupt/version-newer ledgers fail safely.

- [ ] **Step 2: Implement atomic locked receipt persistence**

Store only operation name, digest, and bounded protocol response. Use the profile lock before lifecycle/campaign locks. Validate response size before persistence. Never evict an operation being processed; do not write an “in progress” success surrogate.

- [ ] **Step 3: Write failing operation-specific idempotency tests**

Cover stable campaign-ID setup/transition replay, desired-state pause/resume/complete/return-to-practice, and the existing campaign/mission/attempt assessment duplicate rule. Reusing an operation ID after timeout must return the original success and must not increment revision twice.

- [ ] **Step 4: Add crash-injection tests at publication boundaries**

Inject process termination before domain write, after domain write/before receipt, and after receipt. On retry, inspect the desired domain state under lock: return equivalent success when the exact mutation already landed, conflict when it differs, and perform the mutation only when absent. Assessment uses stored attempt identity and canonical submitted evidence for this reconciliation.

- [ ] **Step 5: Implement reconciliation without a distributed-transaction fiction**

Keep stable identifiers and desired-state semantics authoritative. Record the receipt while still holding the relevant lock, but explicitly recover the unavoidable two-file crash window by comparing persisted domain state with the request. Never blindly retry a create or assessment.

- [ ] **Step 6: Verify and commit Task 4**

Run: `PYTHONPATH=src python -m pytest tests/test_receipts.py tests/test_protocol.py tests/test_learners.py tests/test_adapter_subprocess.py -v`

Run: `PYTHONPATH=src python -m pytest -q`

Expected: all pass, including real two-process replay tests.

```bash
git add src/langcampaign/receipts.py src/langcampaign/profile.py src/langcampaign/protocol.py src/langcampaign/learners.py tests
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: make adapter mutations idempotent"
```

---

### Task 5: Upgrade backups, safe export, and recoverable reset

**Files:**
- Create: `src/langcampaign/data_management.py`
- Modify: `src/langcampaign/storage.py`
- Modify: `src/langcampaign/profile.py`
- Modify: `src/langcampaign/protocol.py`
- Modify: `src/langcampaign/__init__.py`
- Create: `tests/test_data_management.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_protocol.py`
- Modify: `tests/test_adapter_subprocess.py`

**Interfaces:**
- Produces `inspect_schema_versions(root, learner_id) -> SchemaInventory` without mutating data.
- Produces `backup_before_upgrade`, `export_profile`, and `reset_profile` with injected clock and operation ID.
- Export returns archive path and manifest summary; reset returns fresh profile plus backup/recovery paths.

- [ ] **Step 1: Write failing schema inventory and upgrade-backup tests**

Assert historical campaign schemas remain byte-identical on read, a first write requiring migration creates an owner-only ZIP backup with format/plugin/schema metadata and SHA-256 hashes, only the newest three successful upgrade backups remain, and code older than stored schema returns `UNSUPPORTED_SCHEMA` without modification.

- [ ] **Step 2: Implement per-document staged migration orchestration**

Under the profile lock, inventory expected regular files, create and verify the backup, load/validate the document in memory, write its migrated replacement through the existing atomic storage API, and record migration completion. On failure keep the original authoritative and move only partial staging artifacts to `recovery/`; never auto-downgrade.

- [ ] **Step 3: Write failing consistent-export tests**

Export under profile/lifecycle locks to a caller-selected existing destination directory. Assert ZIP contents include only profile, receipt ledger, learner index, and campaign states plus a manifest; exclude locks/temp/backups/recovery; reject symlinks/path traversal/non-directory destinations/overwrite; use private temp plus atomic rename; verify every checksum.

- [ ] **Step 4: Implement export from public snapshots**

Do not parse campaign JSON in the adapter. Put enumeration and validated byte snapshots behind `data_management.py`/storage interfaces. Resolve and re-check destination containment and entry types immediately before opening.

- [ ] **Step 5: Write failing reset tests**

Reject every confirmation except exact `RESET LANGCAMPAIGN`. Assert reset first produces a verified export backup, then moves the old profile/learners/receipts into a timestamped recovery directory, creates a new opaque profile, reports both paths, follows no symlinks, is timeout-idempotent, and never calls recursive deletion.

- [ ] **Step 6: Implement recoverable reset and protocol operations**

Use the exclusive profile lock and deterministic operation-specific names. If interrupted, retry reconciles backup, recovery directory, and new profile state using the same operation ID.

- [ ] **Step 7: Verify and commit Task 5**

Run: `PYTHONPATH=src python -m pytest tests/test_data_management.py tests/test_storage.py tests/test_protocol.py tests/test_adapter_subprocess.py -v`

Run: `PYTHONPATH=src python -m pytest -q`

Expected: all pass.

```bash
git add src/langcampaign/data_management.py src/langcampaign/storage.py src/langcampaign/profile.py src/langcampaign/protocol.py src/langcampaign/__init__.py tests
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: add safe learner data management"
```

---

### Task 6: Codex learner workflow and presentation policy

**Files:**
- Create: `skills/langcampaign/SKILL.md`
- Create: `skills/langcampaign/agents/openai.yaml`
- Create: `workflow/learner-policy.md`
- Create: `workflow/generation-contracts.md`
- Create: `workflow/presentation.md`
- Create: `workflow/examples.md`
- Modify: `.codex-plugin/plugin.json`
- Create: `tests/test_skill_contract.py`

**Interfaces:**
- Consumes only `scripts/langcampaign_adapter.py` protocol v1 operations.
- Produces `$langcampaign` explicit invocation, narrow implicit activation, and the complete natural-language learner flow.

- [ ] **Step 1: Write failing static skill-contract tests**

Assert the skill positively covers create/continue/assess/pause/transition/resume/progress and explicitly excludes implicit one-off translation, grammar, pronunciation, editing, and general discussion. Assert it invokes only the adapter, names no internal JSON path, and includes every recovery branch and the one-generation/one-mutation rule.

- [ ] **Step 2: Write learner policy and exact routing rules**

Define automatic profile resolution; minimal setup questions; fixed Flexible/Targeted, Balanced, Supportive defaults; immutable goals; the exact materially-new-goal criteria; ambiguous resume choices; active/paused/completed semantics; `too easy`/`too hard`; and engine-authoritative progress. Casual texting, friends, tweets, and reading remain valid practical goals.

- [ ] **Step 3: Write generation and correction contracts**

Specify complete setup output, two or three roadmap mission outlines, detailed first content only, persisted 0–100 weighted rubric, no caller audit timestamps, one complete validation request, ordered issue correction, and termination after candidate two fails. For subsequent missions generate content only when `content_refresh_required` or no persisted bundle exists.

- [ ] **Step 4: Write the no-hints and one-response rules**

List disqualifying help exactly: answer/translation, correction before score, completion, choices, criterion coaching, or an example that solves the prompt. Allow verbatim repetition and non-linguistic/accessibility clarification. On leakage call `return-to-practice` and record no evidence. Evaluation uses one generation, then one `submit-assessment`; it trusts but truthfully labels Codex's independence declaration.

- [ ] **Step 5: Write restrained presentation templates and examples**

Provide canonical outputs for setup, teaching, guided practice, check announcement, pass/partial/retry, resume, progress, pause, transition, ambiguous choice, persistence failure, and unsupported environment. Use at most one colored status emoji when material, the engine's ten-segment bar after meaningful work, direct credit/correction, and a next action; prohibit banners, emoji patterns, CEFR claims, and long encouragement.

- [ ] **Step 6: Validate skill discovery and commit Task 6**

Run: `PYTHONPATH=src python -m pytest tests/test_skill_contract.py tests/test_plugin_package.py -v`

Run the installed plugin in a fresh Codex conversation and record that `$langcampaign` discovers the skill, a campaign request activates it, and a translation-only prompt does not implicitly activate it.

Run: `PYTHONPATH=src python -m pytest -q`

Expected: all automated tests pass and manual discovery checks match the declared boundary.

```bash
git add skills workflow .codex-plugin/plugin.json tests/test_skill_contract.py
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: add Codex learner workflow"
```

---

### Task 7: Reproducible evaluation and supported-platform CI

**Files:**
- Create: `evaluation/README.md`
- Create: `evaluation/scenario.schema.json`
- Create: `evaluation/scenarios/01-travel-beginner.json` through `evaluation/scenarios/10-fresh-resume.json`
- Create: `evaluation/run_deterministic.py`
- Create: `evaluation/score_live_run.py`
- Create: `tests/test_evaluation_contract.py`
- Create: `tests/test_concurrency_subprocess.py`
- Create: `.github/workflows/test.yml`

**Interfaces:**
- Each scenario declares schema version, fixed input, fresh-profile seed, expected operations, learner-visible assertions, prohibited behavior, and severity rubric.
- Live result records scenario/plugin commit/model/Codex/Python/OS/start time/redacted transcript/adapter trace/latency without learner secrets.

- [ ] **Step 1: Write failing scenario-schema and fixture tests**

Require all ten approved scenarios and exact fields. Reject unknown fields, missing expected operations, non-redacted result fixtures, mutable timestamps/randomness in deterministic traces, and scenarios that reuse data directories.

- [ ] **Step 2: Implement fixed deterministic trace runner**

Inject fixed clocks and randomness, create a fresh temporary profile per scenario, dispatch the declared adapter operations, and compare normalized envelopes/tool counts. Return nonzero for any mismatch. Never call a model or network.

- [ ] **Step 3: Implement live-run scoring and severity gates**

Score goal relevance, setup economy, hint leakage, evidence accuracy, fair credit, brevity, visual restraint, persistence, recovery, and model/tool count. Encode Critical, Important, and Minor definitions verbatim from the design. Release fails on any Critical or unresolved reproducible Important result; run each live scenario twice from fresh profiles.

- [ ] **Step 4: Add real subprocess concurrency/crash scenarios**

Cover same-operation setup replay, duplicate assessment, pause versus assessment, export versus update, reset versus update, lock-holder termination, domain-commit/receipt crash window, and partial migration recovery. Assert no corrupt JSON, duplicate evidence, multiple active campaigns, lost completed mutation, or unsafe file traversal.

- [ ] **Step 5: Add the CI matrix**

Run the full suite on `ubuntu-latest`, `macos-latest`, and `windows-latest` with Python 3.11, plus the newest Python version declared supported. Set `PYTHONPATH=src` explicitly so subprocess tests inherit the bundled-development import path. Run plugin JSON/schema checks and deterministic evaluation in CI; keep live-model runs manual release gates.

- [ ] **Step 6: Verify and commit Task 7**

Run: `PYTHONPATH=src python -m pytest tests/test_evaluation_contract.py tests/test_concurrency_subprocess.py -v`

Run: `PYTHONPATH=src python evaluation/run_deterministic.py`

Run: `PYTHONPATH=src python -m pytest -q`

Expected: zero deterministic mismatches and all tests pass.

```bash
git add evaluation .github/workflows/test.yml tests/test_evaluation_contract.py tests/test_concurrency_subprocess.py
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "test: add Codex release evaluation"
```

---

### Task 8: Learner documentation, clean installation, and MVP release gate

**Files:**
- Modify: `README.md`
- Modify: `evaluation/README.md`
- Modify: `docs/superpowers/specs/2026-08-04-codex-delivery-evaluation-design.md`
- Modify: any Task 1–7 file only for defects discovered by the release gate

**Interfaces:**
- Produces the final user-facing installation/use/data/troubleshooting guide and evidence that the published repository fulfills it.

- [ ] **Step 1: Rewrite the README as a concise learner guide**

Document exactly:

```bash
codex plugin marketplace add qasim-a/langcampaign
codex plugin add langcampaign@langcampaign
```

Then show starting with `$langcampaign`, natural setup examples (including casual texting/reading goals), continuing in a fresh conversation, progress, pause/resume, materially new goal transition, data locations, non-overwriting export, exact reset confirmation, upgrade command, Python 3.11 requirement, privacy boundary, and MVP limitations. Do not expose engine command names in the normal usage path or claim ChatGPT/Claude support.

- [ ] **Step 2: Run a clean-profile repository installation acceptance test**

Use a temporary Codex home/config with no development checkout on its Python path. Add `qasim-a/langcampaign`, install `langcampaign@langcampaign`, start a fresh conversation, run the check-install probe, create a campaign, reach guided practice, close the conversation, and resume from a new conversation. Record versions, commands, elapsed local-operation times, and redacted results in the release evidence format.

- [ ] **Step 3: Run the two-pass live scenario suite**

Execute all ten scenarios twice with fresh profiles. Investigate every Important inconsistency, rerun its exact scenario after correction, and require zero Critical and zero unresolved reproducible Important failures. Do not average away a safety or persistence failure.

- [ ] **Step 4: Run final automated verification**

Run: `git diff --check`

Run: `PYTHONPATH=src python -m pytest -q`

Run: `PYTHONPATH=src python evaluation/run_deterministic.py`

Run: `python scripts/check_install.py`

Expected: clean diff, all tests pass, zero deterministic mismatches, and one successful JSON install-probe response.

- [ ] **Step 5: Mark the design implemented and commit the final MVP**

Change the design status only after Steps 2–4 pass and attach the release evidence location. Confirm commit authorship before committing.

```bash
git add README.md evaluation docs/superpowers/specs/2026-08-04-codex-delivery-evaluation-design.md .agents .codex-plugin skills workflow scripts schemas src tests .github
git diff --cached --check
git -c user.name="Qasim Ali" -c user.email="qasimali0630@gmail.com" commit -m "feat: complete LangCampaign Codex MVP"
git show -s --format='%an <%ae>' HEAD
```

- [ ] **Step 6: Push only after final verification remains green**

Run: `git push origin main`

Expected: GitHub reports the verified final commit on `main`.
