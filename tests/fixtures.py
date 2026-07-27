from langcampaign.missions import (
    AssessmentScenario,
    MissionPlan,
    MissionPriority,
    PracticeActivity,
)


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
