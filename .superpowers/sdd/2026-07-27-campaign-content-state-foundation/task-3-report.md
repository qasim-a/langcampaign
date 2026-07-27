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
