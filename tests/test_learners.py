from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

import langcampaign.learners as learners
from langcampaign.learners import (
    CampaignAlreadyExistsError,
    CampaignSelectionError,
    CampaignSummary,
    EvidenceTransfer,
    activate_campaign,
    campaign_state_path,
    complete_campaign,
    create_and_activate_campaign,
    list_campaign_summaries,
    list_learner_campaigns,
    normalize_learner_id,
    save_learner_campaign,
    select_active_campaign,
    select_campaign,
    transition_campaign,
)
from langcampaign.assessment import AssessmentEvidence
from langcampaign.models import Mission, new_campaign
from langcampaign.storage import (
    CampaignLifecycle,
    LearnerCampaignIndex,
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

    with pytest.raises(CampaignSelectionError, match="campaign selection is ambiguous"):
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


def test_create_only_save_allows_exactly_one_concurrent_creator(tmp_path):
    first = state("First goal")
    second = state("Second goal")
    second = replace(
        second,
        campaign=replace(second.campaign, id=first.campaign.id),
    )
    barrier = Barrier(2)

    def create(campaign_state):
        barrier.wait()
        try:
            return save_learner_campaign(tmp_path, campaign_state, create_only=True)
        except CampaignAlreadyExistsError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(create, (first, second)))

    assert sum(isinstance(result, Path) for result in results) == 1
    assert (
        sum(isinstance(result, CampaignAlreadyExistsError) for result in results)
        == 1
    )
    assert select_campaign(tmp_path, "Qasim Ali", first.campaign.id) in (first, second)
    assert list(tmp_path.rglob(".state.json.*.tmp")) == []


def test_first_campaign_becomes_active_and_second_is_paused(tmp_path):
    first = state("Text friends")
    second = state("Read posts")

    create_and_activate_campaign(tmp_path, first)
    save_learner_campaign(tmp_path, second, create_only=True)

    assert list_campaign_summaries(tmp_path, first.learner_id) == (
        CampaignSummary(first.campaign.id, "Text friends", CampaignLifecycle.ACTIVE),
        CampaignSummary(second.campaign.id, "Read posts", CampaignLifecycle.PAUSED),
    )


def test_resume_switches_active_pointer_without_rewriting_campaign_state(tmp_path):
    first = state("Text friends")
    second = state("Read posts")
    create_and_activate_campaign(tmp_path, first)
    save_learner_campaign(tmp_path, second, create_only=True)
    first_path = campaign_state_path(tmp_path, first.learner_id, first.campaign.id)
    second_path = campaign_state_path(tmp_path, second.learner_id, second.campaign.id)
    original_bytes = (first_path.read_bytes(), second_path.read_bytes())

    activate_campaign(tmp_path, first.learner_id, second.campaign.id)

    assert (first_path.read_bytes(), second_path.read_bytes()) == original_bytes
    assert list_campaign_summaries(tmp_path, first.learner_id) == (
        CampaignSummary(first.campaign.id, "Text friends", CampaignLifecycle.PAUSED),
        CampaignSummary(second.campaign.id, "Read posts", CampaignLifecycle.ACTIVE),
    )


def test_transition_maps_only_explicit_evidence_and_pauses_previous(tmp_path):
    source_campaign = new_campaign("Text friends", "Spanish").with_missions(
        (Mission("source-a", "Source A"), Mission("source-b", "Source B"))
    )
    source_evidence = (
        AssessmentEvidence(
            "source-a", 91, True, "written", datetime(2026, 8, 3, tzinfo=timezone.utc), "A2"
        ),
        AssessmentEvidence(
            "source-b", 74, True, "written", datetime(2026, 8, 3, tzinfo=timezone.utc)
        ),
    )
    source = CampaignState(source_campaign, source_evidence, "Qasim Ali")
    target = CampaignState(
        new_campaign("Read posts", "Spanish").with_missions(
            (Mission("target-a", "Target A"), Mission("target-b", "Target B"))
        ),
        learner_id="Qasim Ali",
    )
    create_and_activate_campaign(tmp_path, source)
    source_path = campaign_state_path(tmp_path, source.learner_id, source.campaign.id)
    source_bytes = source_path.read_bytes()

    transition_campaign(
        tmp_path,
        "Qasim Ali",
        target,
        (EvidenceTransfer("source-a", "target-a"),),
    )

    transferred = select_campaign(tmp_path, "Qasim Ali", target.campaign.id)
    assert transferred.assessment_evidence == (
        replace(source_evidence[0], mission_id="target-a"),
    )
    assert source_path.read_bytes() == source_bytes
    assert select_campaign(tmp_path, "Qasim Ali", source.campaign.id) == source
    assert list_campaign_summaries(tmp_path, "Qasim Ali") == (
        CampaignSummary(source.campaign.id, "Text friends", CampaignLifecycle.PAUSED),
        CampaignSummary(target.campaign.id, "Read posts", CampaignLifecycle.ACTIVE),
    )


def test_failed_transition_keeps_previous_campaign_active(tmp_path, monkeypatch):
    source = state("Text friends")
    target = state("Read posts")
    create_and_activate_campaign(tmp_path, source)

    def fail_publish(*args, **kwargs):
        del args, kwargs
        raise OSError("index publication failed")

    monkeypatch.setattr(learners, "save_learner_index_at", fail_publish)

    with pytest.raises(OSError, match="index publication failed"):
        transition_campaign(tmp_path, source.learner_id, target, ())

    assert select_active_campaign(tmp_path, source.learner_id) == source
    assert list_campaign_summaries(tmp_path, source.learner_id) == (
        CampaignSummary(source.campaign.id, "Text friends", CampaignLifecycle.ACTIVE),
        CampaignSummary(target.campaign.id, "Read posts", CampaignLifecycle.PAUSED),
    )


def test_completed_campaign_cannot_be_reactivated(tmp_path):
    stored = state()
    create_and_activate_campaign(tmp_path, stored)

    complete_campaign(tmp_path, stored.learner_id, stored.campaign.id)

    with pytest.raises(CampaignSelectionError, match="completed"):
        activate_campaign(tmp_path, stored.learner_id, stored.campaign.id)


def test_selecting_active_campaign_requires_a_unique_legacy_candidate(tmp_path):
    with pytest.raises(CampaignSelectionError, match="no active campaign"):
        select_active_campaign(tmp_path, "Qasim Ali")

    only = state()
    save_learner_campaign(tmp_path, only, create_only=True)
    assert select_active_campaign(tmp_path, "Qasim Ali") == only

    save_learner_campaign(tmp_path, state("Read posts"), create_only=True)
    with pytest.raises(CampaignSelectionError, match="ambiguous"):
        select_active_campaign(tmp_path, "Qasim Ali")


def test_lifecycle_operations_materialize_legacy_index_and_reject_bad_index_ids(tmp_path):
    stored = state()
    save_learner_campaign(tmp_path, stored, create_only=True)

    activate_campaign(tmp_path, stored.learner_id, stored.campaign.id)

    index_path = tmp_path / "qasim-ali" / "index.json"
    assert index_path.exists()
    index_path.write_text(
        '{"schema_version": 1, "active_campaign_id": "missing", "completed_campaign_ids": []}'
    )
    with pytest.raises(CampaignStorageError, match="references missing campaign"):
        list_campaign_summaries(tmp_path, stored.learner_id)


def test_transition_rejects_caller_evidence_and_invalid_mapping_boundaries(tmp_path):
    source = CampaignState(
        new_campaign("Text friends", "Spanish").with_missions((Mission("source", "Source"),)),
        learner_id="Qasim Ali",
    )
    create_and_activate_campaign(tmp_path, source)
    target = CampaignState(
        new_campaign("Read posts", "Spanish").with_missions((Mission("target", "Target"),)),
        learner_id="Qasim Ali",
    )
    evidence_target = replace(
        target,
        assessment_evidence=(
            AssessmentEvidence("target", 90, True, "written", datetime(2026, 8, 3, tzinfo=timezone.utc)),
        ),
    )

    with pytest.raises(CampaignSelectionError, match="assessment evidence"):
        transition_campaign(tmp_path, "Qasim Ali", evidence_target, ())
    with pytest.raises(CampaignSelectionError, match="source mission"):
        transition_campaign(
            tmp_path, "Qasim Ali", target, (EvidenceTransfer("missing", "target"),)
        )
