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
