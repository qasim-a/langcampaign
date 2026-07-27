import pytest

from langcampaign.missions import AssessmentScenario, validate_mission_map
from tests.fixtures import delayed_arrival


def test_valid_mission_map_links_content_to_readiness_missions():
    plan = delayed_arrival()

    validate_mission_map((plan,), ("delayed-arrival",))


@pytest.mark.parametrize(
    ("build_invalid_content", "message"),
    [
        (
            lambda: delayed_arrival(practice=()),
            "practice must not be empty",
        ),
        (
            lambda: AssessmentScenario("Respond appropriately.", ()),
            "success_criteria must not be empty",
        ),
    ],
)
def test_mission_content_rejects_unassessable_content(
    build_invalid_content, message
):
    with pytest.raises(ValueError, match=message):
        build_invalid_content()


def test_mission_map_requires_exactly_one_plan_per_readiness_mission():
    with pytest.raises(ValueError, match="mission plan ids must match readiness mission ids"):
        validate_mission_map(
            (delayed_arrival(),), ("delayed-arrival", "hotel-check-in")
        )


def test_mission_map_rejects_missing_prerequisites():
    plan = delayed_arrival(prerequisite_ids=("hotel-check-in",))

    with pytest.raises(ValueError, match="mission prerequisite does not exist"):
        validate_mission_map((plan,), ("delayed-arrival",))


def test_mission_map_rejects_missing_and_circular_prerequisites():
    first = delayed_arrival(prerequisite_ids=("hotel-check-in",))
    second = delayed_arrival(
        id="hotel-check-in",
        title="Complete a hotel check-in",
        capability="Complete a hotel check-in and respond to a reservation question.",
        prerequisite_ids=("delayed-arrival",),
    )

    with pytest.raises(ValueError, match="mission prerequisites must be acyclic"):
        validate_mission_map(
            (first, second), ("delayed-arrival", "hotel-check-in")
        )
