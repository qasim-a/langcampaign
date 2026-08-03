# Task 6 report: foundation acceptance and documentation

## Acceptance

The public command-boundary acceptance flow was added in
`tests/test_content_state_flow.py`. It creates a campaign through `setup`,
loads the newly persisted state through `validate-state`, and reveals the
roadmap only through `show-roadmap`.

Command:

```text
python -m pytest tests/test_content_state_flow.py -v
```

Output:

```text
collected 1 item
tests/test_content_state_flow.py::test_setup_persists_hidden_roadmap_and_fresh_process_can_reveal_summary PASSED
============================== 1 passed in 0.03s ===============================
```

The acceptance assertion confirms that the roadmap summary includes the active
phase and does not expose the internal learner-script assumption.

## Documentation

`README.md` now describes the campaign-content foundation and clarifies that
Codex teaching and setup skills are planned, not operational.

## Verification

Command:

```text
python -m pytest -v
```

Output:

```text
collected 164 items
============================= 164 passed in 0.33s ==============================
```

Command:

```text
python -m pip install -e '.[test]'
```

Output: editable installation succeeded.

Command:

```text
python -m compileall -q src
```

Output: no output (exit 0).

Command:

```text
git diff --check
```

Output: no output (exit 0).

## Commit

Acceptance test and README update:

```text
dae22b899d0bbcd0cfe0f0be1c0a2f4122806014 docs: describe campaign content foundation
```

## Concerns

None. The first editable-install attempt could not resolve PyPI dependencies
inside the sandbox; the approved network-enabled retry succeeded.
