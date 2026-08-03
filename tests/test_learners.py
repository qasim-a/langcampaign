from dataclasses import replace
from pathlib import Path

import pytest

import langcampaign.learners as learners
from langcampaign.learners import (
    campaign_state_path,
    list_learner_campaigns,
    normalize_learner_id,
    save_learner_campaign,
    select_campaign,
)
from langcampaign.models import new_campaign
from langcampaign.storage import (
    CampaignState,
    CampaignStorageError,
    save_campaign_state,
)


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


def test_repository_rejects_a_state_with_a_different_learner_identity(tmp_path):
    stored = state()
    path = save_learner_campaign(tmp_path, stored)
    save_campaign_state(path, replace(stored, learner_id="Other Learner"))

    with pytest.raises(
        CampaignStorageError,
        match="stored learner_id does not match directory",
    ):
        list_learner_campaigns(tmp_path, "Qasim Ali")
    with pytest.raises(
        CampaignStorageError,
        match="stored learner_id does not match directory",
    ):
        select_campaign(tmp_path, "Qasim Ali")


def test_repository_wraps_an_invalid_stored_learner_id_as_storage_corruption(
    tmp_path,
):
    stored = state()
    path = save_learner_campaign(tmp_path, stored)
    save_campaign_state(path, replace(stored, learner_id="../../"))

    for select in (
        lambda: list_learner_campaigns(tmp_path, "Qasim Ali"),
        lambda: select_campaign(tmp_path, "Qasim Ali"),
        lambda: select_campaign(tmp_path, "Qasim Ali", stored.campaign.id),
    ):
        with pytest.raises(
            CampaignStorageError,
            match="stored learner_id is invalid",
        ):
            select()


def test_repository_rejects_a_state_with_a_different_campaign_identity(tmp_path):
    stored = state()
    path = save_learner_campaign(tmp_path, stored)
    mismatched = replace(
        stored,
        campaign=replace(stored.campaign, id="other-campaign"),
    )
    save_campaign_state(path, mismatched)

    with pytest.raises(
        CampaignStorageError,
        match="stored campaign id does not match directory",
    ):
        list_learner_campaigns(tmp_path, "Qasim Ali")
    with pytest.raises(
        CampaignStorageError,
        match="stored campaign id does not match directory",
    ):
        select_campaign(tmp_path, "Qasim Ali")
    with pytest.raises(
        CampaignStorageError,
        match="stored campaign id does not match directory",
    ):
        select_campaign(tmp_path, "Qasim Ali", stored.campaign.id)


def test_listing_does_not_follow_a_state_file_swapped_to_a_symlink(
    monkeypatch,
    tmp_path,
):
    stored = state()
    path = save_learner_campaign(tmp_path, stored)
    outside = tmp_path / "outside-state.json"
    save_campaign_state(outside, replace(stored, campaign=replace(stored.campaign, goal="Outside")))
    original_open = learners._open_regular_file

    def swap_then_open(directory_fd, name):
        if name == "state.json":
            path.unlink()
            path.symlink_to(outside)
        return original_open(directory_fd, name)

    monkeypatch.setattr(learners, "_open_regular_file", swap_then_open)

    assert list_learner_campaigns(tmp_path, "Qasim Ali") == ()


def test_saving_does_not_write_outside_after_a_campaign_directory_swap(
    monkeypatch,
    tmp_path,
):
    stored = state()
    path = campaign_state_path(tmp_path, stored.learner_id, stored.campaign.id)
    outside = tmp_path / "outside"
    detached = tmp_path / "detached"
    outside.mkdir()
    original_save = learners.save_campaign_state_at

    def swap_then_save(directory_fd, campaign_state):
        path.parent.rename(detached)
        path.parent.symlink_to(outside, target_is_directory=True)
        original_save(directory_fd, campaign_state)

    monkeypatch.setattr(learners, "save_campaign_state_at", swap_then_save)

    save_learner_campaign(tmp_path, stored)

    assert not (outside / "state.json").exists()
    assert (detached / "state.json").exists()
