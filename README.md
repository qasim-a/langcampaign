# LangCampaign

Goal-driven language campaigns for AI agents.

LangCampaign supports targeted campaigns with honest target-date forecasts and
flexible campaigns for goals such as texting friends, reading social media, and
participating in online communities. Its core engine keeps demonstrated mission
readiness separate from projected readiness and completed training time.

## Resumable campaign state

`save_campaign()` and `load_campaign()` continue to read and write the
original schema-version 1 campaign files. To resume assessment-backed
readiness and CEFR reporting, use `CampaignState`,
`save_campaign_state()`, and `load_campaign_state()`. Campaign-state files
use schema version 2 and contain both the campaign and its
`AssessmentEvidence`; the state loader also accepts version 1 files and
returns empty evidence for them.

## Forecasting MVP policy

The deterministic MVP forecast treats 80% as the readiness target and
estimates up to 15 readiness points per 100 future study minutes. Recovery
advice may recommend a required pace up to 840 total minutes per week (two
hours per day). Above that capacity, it recommends narrowing the goal or
revising the target date instead of displaying an implausible time increase.

Forecast inputs are integer observations. At zero elapsed days, zero studied
minutes means no observed pace yet; positive studied minutes require a
nonzero observation window.

## Development

```bash
python -m pip install -e '.[test]'
python -m pytest -v
```
