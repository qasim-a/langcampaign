# Task 4 report: repository-local learner campaigns

Implementation commit: `806210f6e79bed016c9810ef4ccd5e77f476a331`

## TDD evidence

Before implementation, `python -m pytest tests/test_learners.py -v` failed
during collection with the expected
`ModuleNotFoundError: No module named 'langcampaign.learners'`.

The implementation adds normalized learner IDs, validated campaign path
components, atomic storage through the existing storage boundary, deterministic
campaign discovery, and unambiguous selection. Discovery uses `lstat`-based
type checks: non-directory entries and symlinks are skipped rather than
followed, while malformed regular state files continue to raise the existing
`CampaignStorageError`.

## Verification

- `python -m pytest tests/test_learners.py tests/test_storage.py -v` — 41
  passed.
- `python -m pytest -v` — 139 passed.
- `git diff --check` — passed with no whitespace errors.

The `learners/` repository-local data root is ignored except for its tracked
`.gitkeep` placeholder.

## Review-finding fix: identity binding and concurrent swaps

Fix commit: `40055738735c91a64ace79b69b17aaf0a58b7c7d`

### RED evidence

The three new regressions initially failed: learner-directory/state mismatches
and campaign-directory/state mismatches were accepted, while the deterministic
swap test could not exercise a no-follow open boundary because none existed.

### GREEN evidence

- `python -m pytest tests/test_learners.py tests/test_storage.py -v` — 45
  passed.
- `python -m pytest -v` — 143 passed.
- `git diff --check` — passed with no whitespace errors.

Loaded records now require both `normalize_learner_id(state.learner_id)` and
`state.campaign.id` to match their canonical directory components; mismatches
raise `CampaignStorageError`. Canonical normalization is the explicit identity
policy, so equivalent raw learner labels map to the same canonical repository
identity. Learner traversal keeps directory descriptors open and uses
no-follow `openat` operations. State writes remain atomic, use a temporary file
and replacement within the held campaign directory descriptor, and fsync the
file and directory where supported. Deterministic tests verify swaps cannot
redirect either reads or writes outside the opened repository tree.
