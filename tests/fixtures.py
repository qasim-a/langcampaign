from langcampaign.missions import (
    AssessmentScenario,
    MissionPlan,
    MissionPriority,
    PracticeActivity,
)
from langcampaign.roadmaps import CampaignRoadmap, RoadmapPhase


def delayed_arrival(**changes):
    values = {
        "id": "delayed-arrival",
        "title": "Explain a delayed arrival",
        "capability": "Notify a hotel of a late arrival and answer one follow-up.",
        "rationale": "The learner expects to travel by train before hotel check-in.",
        "priority": MissionPriority.CRITICAL,
        "prerequisite_ids": (),
        "target_vocabulary": ("retraso", "llegar"),
        "target_structures": ("Voy a llegar a...",),
        "register_notes": ("Use polite usted forms with hotel staff.",),
        "cultural_context": (),
        "practice": (
            PracticeActivity("guided", "Complete two delayed-arrival messages."),
        ),
        "assessment": AssessmentScenario(
            prompt="Tell the hotel your train is late and answer when you will arrive.",
            success_criteria=(
                "States that the train is delayed.",
                "Provides a revised arrival time.",
                "Answers one unfamiliar follow-up without a hint.",
            ),
        ),
        "common_failure_patterns": ("States the delay but omits the new time.",),
    }
    values.update(changes)
    return MissionPlan(**values)


def roadmap():
    return CampaignRoadmap(
        phases=(
            RoadmapPhase(
                id="core-transactions",
                title="Core transactions",
                capability_summary="Handle routine hotel and transport exchanges.",
                mission_ids=("delayed-arrival", "hotel-check-in", "train-options"),
                planned_review_after=True,
                planned_simulation_after=False,
            ),
            RoadmapPhase(
                id="problem-recovery",
                title="Problem recovery",
                capability_summary="Correct misunderstandings and request alternatives.",
                mission_ids=(),
                planned_review_after=True,
                planned_simulation_after=True,
            ),
        ),
        active_phase_id="core-transactions",
        assumptions=("The learner can read Latin script.",),
    )


def plans():
    return (
        delayed_arrival(),
        delayed_arrival(
            id="hotel-check-in",
            title="Complete a hotel check-in",
            capability="Complete a hotel check-in and answer a reservation question.",
            priority=MissionPriority.CRITICAL,
        ),
        delayed_arrival(
            id="train-options",
            title="Ask for another train",
            capability="Ask for another train and understand the departure time.",
            priority=MissionPriority.SUPPORTING,
        ),
    )
