import pytest

from langcampaign.missions import MissionPriority
from langcampaign.roadmaps import (
    CampaignRoadmap,
    RoadmapPhase,
    next_priority_ids,
    next_priorities,
    render_roadmap_summary,
    validate_roadmap,
)
from tests.fixtures import delayed_arrival, plans, roadmap


def test_roadmap_is_valid_and_exposes_only_next_three_priorities():
    current = roadmap()
    current_plans = plans()

    validate_roadmap(current, current_plans)

    assert next_priority_ids(current, current_plans) == (
        "delayed-arrival",
        "hotel-check-in",
        "train-options",
    )
    assert next_priorities(current, current_plans) == (
        "Explain a delayed arrival",
        "Complete a hotel check-in",
        "Ask for another train",
    )


def test_roadmap_summary_is_revealable_without_internal_assumptions():
    output = render_roadmap_summary(roadmap(), plans())

    assert "Core transactions (current)" in output
    assert "Problem recovery" in output
    assert "The learner can read Latin script" not in output


def test_roadmap_rejects_unknown_active_phase_and_unknown_detailed_mission():
    with pytest.raises(ValueError, match="active phase must exist"):
        validate_roadmap(
            CampaignRoadmap(roadmap().phases, "missing", ()), plans()
        )

    broken = CampaignRoadmap(
        (
            RoadmapPhase(
                "core", "Core", "Handle core exchanges.", ("unknown",), False, False
            ),
        ),
        "core",
        (),
    )
    with pytest.raises(ValueError, match="roadmap mission ids must exist"):
        validate_roadmap(broken, plans())


def test_next_priorities_orders_active_phase_by_priority_then_its_declared_order():
    current = CampaignRoadmap(
        (
            RoadmapPhase(
                "core",
                "Core",
                "Handle core exchanges.",
                ("train-options", "hotel-check-in", "delayed-arrival"),
                False,
                False,
            ),
        ),
        "core",
        (),
    )

    assert next_priority_ids(current, plans()) == (
        "hotel-check-in",
        "delayed-arrival",
        "train-options",
    )
    assert next_priorities(current, plans()) == (
        "Complete a hotel check-in",
        "Explain a delayed arrival",
        "Ask for another train",
    )


@pytest.mark.parametrize(
    ("build_invalid_record", "message"),
    [
        (
            lambda: RoadmapPhase(
                "core", "Core", "Handle core exchanges.", [], False, False
            ),
            "mission_ids must be a tuple",
        ),
        (
            lambda: CampaignRoadmap([], "core", ()),
            "phases must be a tuple",
        ),
        (
            lambda: CampaignRoadmap(roadmap().phases, "core-transactions", []),
            "assumptions must be a tuple",
        ),
        (
            lambda: RoadmapPhase(
                "core", "Core", "Handle core exchanges.", (), 1, False
            ),
            "planned_review_after must be a bool",
        ),
    ],
)
def test_roadmap_records_reject_mutable_or_invalid_boundaries(
    build_invalid_record, message
):
    with pytest.raises(ValueError, match=message):
        build_invalid_record()


def test_priority_queries_validate_roadmap_and_count_instead_of_lookup_failures():
    invalid = CampaignRoadmap(roadmap().phases, "missing", ())

    with pytest.raises(ValueError, match="active phase must exist"):
        next_priority_ids(invalid, plans())
    with pytest.raises(ValueError, match="count must be a nonnegative integer"):
        next_priorities(roadmap(), plans(), count=-1)


def test_roadmap_requires_every_plan_exactly_once():
    omitted = CampaignRoadmap(
        (
            RoadmapPhase(
                "core",
                "Core",
                "Handle core exchanges.",
                ("delayed-arrival", "hotel-check-in"),
                False,
                False,
            ),
        ),
        "core",
        (),
    )

    with pytest.raises(ValueError, match="exactly once"):
        validate_roadmap(omitted, plans())


def test_roadmap_rejects_a_prerequisite_in_a_later_phase():
    prerequisite = delayed_arrival(
        id="supporting-prerequisite",
        title="Handle a supporting exchange",
        priority=MissionPriority.SUPPORTING,
    )
    dependent = delayed_arrival(
        id="critical-dependent",
        title="Handle the critical exchange",
        prerequisite_ids=("supporting-prerequisite",),
    )
    misplaced = CampaignRoadmap(
        (
            RoadmapPhase(
                "critical",
                "Critical",
                "Handle the critical exchange.",
                ("critical-dependent",),
                False,
                False,
            ),
            RoadmapPhase(
                "support",
                "Support",
                "Build prerequisite support.",
                ("supporting-prerequisite",),
                False,
                False,
            ),
        ),
        "critical",
        (),
    )

    with pytest.raises(
        ValueError, match="prerequisites must not be in later phases"
    ):
        validate_roadmap(misplaced, (prerequisite, dependent))


def test_active_phase_priorities_are_stably_topological_before_priority_ranking():
    prerequisite = delayed_arrival(
        id="supporting-prerequisite",
        title="Handle a supporting exchange",
        priority=MissionPriority.SUPPORTING,
    )
    dependent = delayed_arrival(
        id="critical-dependent",
        title="Handle the critical exchange",
        prerequisite_ids=("supporting-prerequisite",),
    )
    current = CampaignRoadmap(
        (
            RoadmapPhase(
                "core",
                "Core",
                "Handle linked exchanges.",
                ("critical-dependent", "supporting-prerequisite"),
                False,
                False,
            ),
        ),
        "core",
        (),
    )

    assert next_priority_ids(current, (prerequisite, dependent)) == (
        "supporting-prerequisite",
        "critical-dependent",
    )
