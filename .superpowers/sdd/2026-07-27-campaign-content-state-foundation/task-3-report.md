# Task 3 report: schema-version 3 learner campaign state

Implementation commit: `670a96367210bc99941e7b6c4d9b24b5d4112d6c`

## RED evidence

`python -m pytest tests/test_storage.py -v` before implementation collected 28
tests with 18 passing and 10 failing. The new failures demonstrated the missing
version-3 behavior: state saves still emitted schema version 2, `CampaignState`
did not accept `learner_id` or `mission_plans`, and version-2 loads lacked the
default content fields.

`python -m pytest tests/test_campaign_flow.py -v` before the public exports
were added failed because `MissionPlan`, `MissionPriority`, `PracticeActivity`,
`AssessmentScenario`, `CampaignRoadmap`, and `RoadmapPhase` were absent from
`langcampaign.__all__`.

## GREEN evidence

- `python -m pytest tests/test_storage.py tests/test_campaign_flow.py -v`:
  29 passed.
- `python -m pytest -v`: 124 passed.
- `git diff --check`: passed with no whitespace errors.

The storage boundary now writes schema version 3, reads versions 1 and 2 with
default content fields, validates tuple-backed campaign content, and converts
malformed JSON payload type, enum, and shape failures to `CampaignStorageError`.

## Review follow-up: immutable campaign missions

Fix commit: `6bcf66fa8cc846fab98a257f05067aa5a19b9ad4`

### RED evidence

After adding `test_campaign_rejects_mutable_or_invalid_mission_collections`,
`python -m pytest tests/test_models.py -v` had 23 passing tests and one
expected failure: a `Campaign` accepted a caller-owned mutable missions list.

### GREEN evidence

- `python -m pytest tests/test_models.py tests/test_storage.py
  tests/test_campaign_flow.py -v`: 53 passed.
- `python -m pytest -v`: 125 passed.
- `git diff --check`: passed with no whitespace errors.

`Campaign` now enforces its declared tuple mission boundary and requires each
contained value to be a `Mission`, preventing mutable mission collections from
entering frozen campaign state.

## Review follow-up: immutable campaign settings

Fix commit: `6120ddeeb6cf4694d4adb5570ff27ad4dcd78b69`

### RED evidence

After adding `test_campaign_rejects_mutable_or_invalid_settings`,
`python -m pytest tests/test_models.py -v` had 24 passing tests and one
expected failure: a `Campaign` accepted a caller-owned mutable settings
dictionary.

### GREEN evidence

- `python -m pytest tests/test_models.py tests/test_storage.py
  tests/test_campaign_flow.py -v`: 54 passed.
- `python -m pytest -v`: 126 passed.
- `git diff --check`: passed with no whitespace errors.

`Campaign` now requires `CampaignSettings`, so mutable or arbitrary settings
objects cannot enter frozen campaign state; existing version-1, version-2, and
version-3 loads continue to construct and validate that record.
