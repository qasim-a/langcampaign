import json
from datetime import date

import pytest

from langcampaign.models import CampaignType, Mission, new_campaign
from langcampaign.storage import load_campaign, save_campaign


def test_campaign_round_trips_through_versioned_json(tmp_path):
    campaign = new_campaign(
        "Travel independently",
        "French",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 9, 10),
    ).with_missions((Mission("hotel", "Hotel check-in", 2.0),))
    path = tmp_path / "campaign.json"

    save_campaign(path, campaign)
    loaded = load_campaign(path)

    assert loaded == campaign
    assert json.loads(path.read_text())["schema_version"] == 1


def test_unknown_schema_version_is_rejected(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text('{"schema_version": 99, "campaign": {}}')

    with pytest.raises(ValueError, match="unsupported schema_version: 99"):
        load_campaign(path)
