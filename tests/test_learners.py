from pathlib import Path

import pytest

from langcampaign.learners import (
    campaign_state_path,
    list_learner_campaigns,
    normalize_learner_id,
    save_learner_campaign,
    select_campaign,
)
from langcampaign.models import new_campaign
from langcampaign.storage import CampaignState, CampaignStorageError


def state(goal: str = "Text friends", learner: str = "Qasim Ali") -> CampaignState:
    return CampaignState(new_campaign(goal, "Spanish"), learner_id=learner)


def test_learner_id_is_normalized_and_cannot_escape_root(tmp_path):
    assert normalize_learner_id(" Qasim Ali ") == "qasim-ali"
    with pytest.raises(ValueError, match="learner_id must contain letters or numbers"):
        normalize_learner_id("../../")
    path = campaign_state_path(tmp_path, "Qasim Ali", "campaign-1")
    assert path == tmp_path / "qasim-ali" / "campaign-1" / "state.json"


@pytest.mark.parametrize("value", (None, 1, "", "..", "../campaign", "/campaign"))
def test_campaign_state_path_rejects_unsafe_campaign_ids(tmp_path, value):
    with pytest.raises(ValueError, match="campaign_id contains unsafe characters"):
        campaign_state_path(tmp_path, "Qasim Ali", value)


def test_repository_lists_and_selects_the_only_campaign(tmp_path):
    stored = state()
    save_learner_campaign(tmp_path, stored)

    campaigns = list_learner_campaigns(tmp_path, "Qasim Ali")

    assert campaigns == ((stored.campaign.id, "Text friends"),)
    assert select_campaign(tmp_path, "Qasim Ali") == stored


def test_listing_is_deterministic_and_skips_non_directory_or_linked_entries(tmp_path):
    learner_directory = tmp_path / "qasim-ali"
    first = state("First")
    second = state("Second")
    save_learner_campaign(tmp_path, second)
    save_learner_campaign(tmp_path, first)
    (learner_directory / "not-a-campaign").write_text("not a directory")
    (learner_directory / "linked-campaign").symlink_to(
        learner_directory / first.campaign.id,
        target_is_directory=True,
    )
    linked_state = learner_directory / second.campaign.id / "state.json"
    linked_state.unlink()
    linked_state.symlink_to(learner_directory / first.campaign.id / "state.json")

    campaigns = list_learner_campaigns(tmp_path, "Qasim Ali")

    assert campaigns == tuple(sorted(((first.campaign.id, "First"),)))


def test_listing_preserves_storage_errors_for_regular_state_files(tmp_path):
    state_directory = tmp_path / "qasim-ali" / "campaign-1"
    state_directory.mkdir(parents=True)
    (state_directory / "state.json").write_text("not json")

    with pytest.raises(CampaignStorageError, match="invalid campaign storage: malformed JSON"):
        list_learner_campaigns(tmp_path, "Qasim Ali")


def test_selection_never_guesses_between_multiple_campaigns(tmp_path):
    save_learner_campaign(tmp_path, state("Text friends"))
    save_learner_campaign(tmp_path, state("Read social media"))

    with pytest.raises(ValueError, match="campaign selection is ambiguous"):
        select_campaign(tmp_path, "Qasim Ali")


def test_explicit_selection_does_not_follow_a_linked_state_file(tmp_path):
    stored = state()
    path = save_learner_campaign(tmp_path, stored)
    replacement = path.with_name("replacement.json")
    path.rename(replacement)
    path.symlink_to(replacement)

    with pytest.raises(ValueError, match="campaign does not exist"):
        select_campaign(tmp_path, "Qasim Ali", stored.campaign.id)


def test_saving_rejects_a_broken_link_at_the_campaign_directory(tmp_path):
    stored = state()
    campaign_directory = (
        tmp_path / "qasim-ali" / stored.campaign.id
    )
    campaign_directory.parent.mkdir()
    campaign_directory.symlink_to(tmp_path / "missing-campaign", target_is_directory=True)

    with pytest.raises(ValueError, match="campaign directory is not a directory"):
        save_learner_campaign(tmp_path, stored)
