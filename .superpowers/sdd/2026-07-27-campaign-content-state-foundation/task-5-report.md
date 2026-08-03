# Task 5 report: stable JSON command boundary

## Scope

Implemented the stable JSON command boundary in `langcampaign.cli`, including
the `python -m langcampaign` entry point and package exports. The boundary
uses the existing storage parsers and learner repository APIs.

`setup` constructs, parses, validates, derives canonical active-phase priority
IDs and titles, then constructs the `CampaignState` before calling the
repository save function. Invalid priorities and an empty active phase therefore
leave no `state.json` behind.

## TDD evidence

### RED

Command:

```text
python -m pytest tests/test_cli.py -v
```

Output (before production implementation):

```text
collected 0 items / 1 error
E   ModuleNotFoundError: No module named 'langcampaign.cli'
```

The failure was the expected missing command-boundary module.

### GREEN

Command:

```text
python -m pytest tests/test_cli.py -v
```

Output:

```text
collected 7 items
============================== 7 passed in 0.17s ===============================
```

The tests cover successful setup, canonical priority ordering, invalid-plan and
empty-phase rollback, stable unknown-command handling, and one-envelope module
entry point success/error behavior.

## Verification

Command:

```text
python -m pytest tests/test_cli.py tests/test_learners.py tests/test_storage.py -v
```

Output:

```text
collected 53 items
============================== 53 passed in 0.21s ===============================
```

Command:

```text
python -m pytest -v
```

Output:

```text
collected 151 items
============================= 151 passed in 0.24s ==============================
```

Command:

```text
git diff --check
```

Output: no output (exit 0).

## Smoke evidence

The requested bare source-checkout command was run:

```text
python -m langcampaign list-campaigns --learners-root learners --learner-id smoke-test
```

It exited 1 with `No module named langcampaign`, because this `src/`-layout
checkout is not installed as an editable package. The equivalent source-path
smoke command succeeded:

```text
PYTHONPATH=src python -m langcampaign list-campaigns --learners-root learners --learner-id smoke-test
```

Output:

```json
{"success": true, "data": {"campaigns": []}}
```

## Commit

Source and tests commit:

```text
9154346957a15c715d5aa19ea51169cb3a63d1be feat: add agent command boundary
```

## Concerns

The bare `python -m langcampaign` smoke command needs an installed editable
package (or `PYTHONPATH=src`) when executed directly from this source checkout.
No production command-boundary concern was found; all 151 tests passed.
