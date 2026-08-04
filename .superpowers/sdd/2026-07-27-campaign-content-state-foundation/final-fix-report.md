# Campaign-content foundation final fix report

**Date:** 2026-08-03
**Branch:** `codex/campaign-content-foundation`
**Review fixed:** `final-review.md` at reviewed head `27faf00442c75840e65f409760072f41cebb6a07`
**Implementation commit:** `a183161` (`fix: close campaign foundation review findings`)
**Commit identity:** `Qasim Ali <qasimali0630@gmail.com>`

## Outcome

The single permitted final-fix wave addresses all five Important findings and
both Minor findings. It also implements the review recommendations that are
natural to those fixes: an adversarial cross-layer roadmap/setup matrix, an
installed-package smoke, and complete public-export assertions for
`CommandResult`, `run_command`, and `CampaignStorageError`.

No assessment-aware mission selection or other follow-on runtime behavior was
added. The completed foundation contract and schema history remain intact.

## Finding-by-finding mapping

### Important 1: roadmap coverage, placement, and actionable ordering

- `validate_roadmap()` now requires every `MissionPlan` identifier to occur
  exactly once across all phases.
- A prerequisite must be in the same phase as or an earlier phase than its
  dependent.
- `next_priority_ids()` now produces a stable topological ordering for the
  active phase. At each step it considers only nodes whose prerequisites are
  already available, then breaks ties by priority and declared roadmap order.
- Earlier phases are treated as satisfied foundation ordering; no assessment
  evidence is consulted.
- Direct roadmap and setup regressions cover an omitted plan, a prerequisite
  in a later phase, and a critical dependent declared ahead of its supporting
  prerequisite.

Files: `src/langcampaign/roadmaps.py`, `tests/test_roadmaps.py`,
`tests/test_cli.py`.

### Important 2: expected repository errors and narrow command catches

- Added explicit `LearnerRepositoryError`, `CampaignSelectionError`, and
  `CampaignAlreadyExistsError` types.
- Setup converts domain construction/validation failures only at their narrow
  statements and catches only typed repository failures around persistence.
- List/select convert only typed repository or storage failures.
- Arbitrary injected `ValueError` from `save_learner_campaign()`,
  `list_learner_campaigns()`, or `select_campaign()` now propagates.
- Genuine missing, ambiguous, unsafe, corrupt, and duplicate repository inputs
  retain `CommandResult` failure envelopes.

Files: `src/langcampaign/learners.py`, `src/langcampaign/cli.py`,
`tests/test_cli.py`, `tests/test_learners.py`.

### Important 3: argparse failure envelopes

- A command-specific `ArgumentParser.error()` emits one JSON failure envelope
  to stdout and exits 2 without usage or error output on stderr.
- Subprocess regressions cover an unknown command, missing
  `--learners-root`, a missing option value, and an unrecognized option.
- The command table remains exactly:
  `setup`, `list-campaigns`, `validate-state`, `validate-mission-map`, and
  `show-roadmap`.

Files: `src/langcampaign/cli.py`, `tests/test_cli.py`,
`tests/test_content_state_flow.py`.

### Important 4: race-safe create-only setup

- `save_learner_campaign(..., create_only=True)` preserves the existing
  overwrite behavior as the default while providing setup's create-only
  repository operation.
- The storage layer writes and fsyncs a unique temporary file within the held
  campaign-directory descriptor, atomically creates `state.json` with a
  no-replace hard link, removes the temporary name, and fsyncs the directory.
- Concurrent creators for the same learner/campaign produce exactly one
  success and one typed duplicate failure.
- Retried setup with an explicit duplicate ID returns
  `campaign already exists`; the original serialized bytes, state, and
  assessment evidence remain unchanged.

Files: `src/langcampaign/storage.py`, `src/langcampaign/learners.py`,
`src/langcampaign/cli.py`, `tests/test_learners.py`, `tests/test_cli.py`.

### Important 5: lean MVP documentation

- Rewrote the README's primary learner journey around silent defaults, one
  concise fixed style, colored status emojis, a compact progress bar,
  small-batch missions, embedded calibration, clearly announced no-hints
  checks, simple local adaptation, and paused/resumable new-goal transitions.
- Removed learner-facing configuration instructions and promises for coaching
  or curriculum choice, in-place goal editing, simulations, CEFR estimates,
  rich dashboards, and full forecast controls.
- Retained engine features are isolated in an explicitly internal/reference
  section and are not presented as lean learner choices or promises.
- Updated only the foundation plan's delivery-decomposition and follow-on
  sections to the approved lifecycle/setup, lean runtime, and Codex
  delivery/evaluation sequence.

Files: `README.md`,
`docs/superpowers/plans/2026-07-27-campaign-content-state-foundation.md`.

### Minor 1: acceptance privacy

- The acceptance flow now asserts exact setup, validate, and list envelopes.
- Each normal envelope is checked for absence of `roadmap` and `assumptions`.
- The test asserts the exact five command names and then checks the exact
  sanitized `show-roadmap` response separately.

File: `tests/test_content_state_flow.py`.

### Minor 2: mission-map public boundary

- `validate_mission_map()` now deliberately rejects non-tuple plans,
  non-`MissionPlan` elements, non-tuple readiness IDs, and readiness IDs that
  are not non-empty strings.
- Direct public-API parameterized tests cover every boundary.

Files: `src/langcampaign/missions.py`, `tests/test_missions.py`.

## RED evidence

Tests were added before production changes and run against the reviewed
implementation.

1. `python -m pytest tests/test_missions.py tests/test_roadmaps.py -q`
   - Exit 1.
   - `8 failed, 25 passed`.
   - Failures showed missing aggregate validation, omitted-plan acceptance,
     later-phase prerequisite acceptance, and priority-before-prerequisite
     selection.
2. `python -m pytest tests/test_cli.py tests/test_content_state_flow.py tests/test_campaign_flow.py -q`
   - Exit 1.
   - `11 failed, 22 passed`.
   - Failures showed setup's wrong first mission, accepted invalid roadmaps,
     swallowed dependency `ValueError`s, duplicate overwrite, and argparse's
     empty stdout/non-JSON path.
3. `python -m pytest tests/test_learners.py -q`
   - Exit 2 during collection.
   - `ImportError: cannot import name 'CampaignAlreadyExistsError'` proved the
     create-only typed repository boundary was absent.

## Focused GREEN evidence

1. `python -m pytest tests/test_missions.py tests/test_roadmaps.py -q`
   - `33 passed in 0.05s`.
2. `python -m pytest tests/test_learners.py -q`
   - `19 passed in 0.07s`.
3. `python -m pytest tests/test_cli.py tests/test_content_state_flow.py tests/test_campaign_flow.py -q`
   - Initial rerun exposed one pre-existing error-precedence regression:
     empty active phase reported roadmap coverage instead of its established
     specific envelope.
   - After restoring that narrow precedence, `33 passed in 0.45s`.

## Final verification evidence

- `python -m pytest -q`
  - `185 passed in 0.56s` immediately before the implementation commit.
  - A prior complete run after all functional/doc changes also reported
    `185 passed in 0.54s`.
- `python -m compileall -q src`
  - Exit 0, no output.
- `python -m pip install -e '.[test]'`
  - The sandboxed attempt could not resolve the isolated setuptools build
    dependency because network access was blocked.
  - The approved escalated rerun built the editable wheel and ended with
    `Successfully installed langcampaign-0.1.0`.
- Installed-package smoke from `/private/tmp` with `PYTHONPATH` removed:
  - `env -u PYTHONPATH python -m langcampaign list-campaigns --learners-root /private/tmp/langcampaign-installed-smoke --learner-id smoke-test`
  - Exit 0: `{"success": true, "data": {"campaigns": []}}`.
- Explicit source-layout smoke from `/private/tmp`:
  - `PYTHONPATH=<worktree>/src python -m langcampaign list-campaigns --learners-root /private/tmp/langcampaign-pythonpath-smoke --learner-id smoke-test`
  - Exit 0 with the same success envelope.
- Installed malformed invocation:
  - `env -u PYTHONPATH python -m langcampaign unknown --learners-root /private/tmp/langcampaign-installed-smoke`
  - Exit 2 with one JSON failure envelope listing exactly the five commands.
- `git diff --check`
  - Exit 0, no output before the implementation commit.

## Commits

- `a183161` — `fix: close campaign foundation review findings` — source,
  tests, README, and plan updates.
- This report is committed as the immediately following documentation commit;
  its hash is recorded in the final task handoff because a commit cannot embed
  its own final hash.

## Residual concerns

- No known functional or test blocker remains.
- The create-only primitive deliberately follows the repository's existing
  POSIX descriptor-based design and uses same-directory hard linking for
  atomic no-replace publication. It is verified on the current macOS/POSIX
  environment; portability to a non-POSIX repository backend would require a
  separately designed primitive rather than weakening this path with a
  check-then-save guard.
- Mission selection intentionally treats missions in earlier roadmap phases as
  satisfied ordering context. Evidence-aware availability remains deferred to
  the approved lean runtime and was not added to this foundation wave.
