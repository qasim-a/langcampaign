# LangCampaign Campaign Training Model

**Status:** Approved design  
**Date:** 2026-07-27

## Purpose

LangCampaign is a platform-neutral AI-agent framework for intensive, goal-driven language learning. It creates a finite training campaign around a learner's real-world objective, target date, available study time, and preferred coaching experience.

The framework optimizes for practical readiness rather than abstract course completion. Its primary question is: **Can the learner perform the language tasks required by their goal?**

An approximate CEFR estimate provides familiar context, but it must never override mission performance or be presented as an official certification.

## Product vocabulary

- **Campaign:** The complete learning plan for a goal and target date.
- **Mission:** A training unit centered on a real-world language task.
- **Mission check:** A short assessment of one mission's capabilities.
- **Campaign simulation:** A combined assessment requiring transfer across multiple missions.
- **Final simulation:** The end-of-campaign assessment.
- **Mission readiness:** The learner's demonstrated ability to perform campaign tasks.
- **Target-date forecast:** The readiness LangCampaign projects at the target date if the learner continues at their current pace.

## Core commitment

LangCampaign uses a **firm target, flexible schedule, and honest rolling forecast**.

The target date is a firm planning constraint, not a guaranteed outcome. LangCampaign promises to:

1. Build the strongest achievable path toward the learner's goal.
2. Recalculate that path from actual study and demonstrated performance.
3. Warn the learner early when the original outcome is at risk.
4. Offer concrete recovery options instead of concealing or minimizing risk.

User-facing language should say **target date**, not **guaranteed deadline** or **firm promise**.

## Campaign setup

Campaign setup collects:

- Target language
- Goal and required real-world situations
- Target date
- Expected study availability
- Minimum realistic study commitment
- Existing ability and relevant prior experience
- Curriculum scope
- Coaching style
- Interaction constraints, including text-only limitations where applicable

Expected availability is a planning estimate, not assumed attendance. The plan adapts to time actually studied.

## Two independent learner controls

Curriculum scope and coaching style must remain separate. A learner may want narrowly focused material with encouraging feedback, or broad instruction with demanding accountability.

### Curriculum scope

#### Mission Focused

Concentrates almost exclusively on capabilities that materially improve the stated goal. Planning guidance is approximately 90% mission preparation and 10% supporting context. It is appropriate when time is limited or the outcome is narrow.

#### Balanced (default)

Prioritizes the goal while adding grammar, culture, and transferable language context that helps the learner understand and adapt. Planning guidance is approximately 70% mission preparation and 30% supporting context.

#### Foundational

Develops broader understanding around the campaign, including material that may not be immediately necessary for the stated goal. Planning guidance is approximately 50% mission preparation and 50% broader capability.

These percentages guide curriculum generation; they are not lesson quotas. Every mode protects the target goal. When the target-date forecast becomes at risk, optional context is reduced before mission-critical training.

### Coaching style

#### Supportive (default)

Encouraging and candid. It maintains expectations, explains corrections constructively, and recommends recovery without shame.

#### Direct

Concise and unsentimental. It emphasizes errors, required actions, and schedule consequences while remaining respectful.

#### Boot Camp

Highly structured and demanding. It uses frequent checks, firm accountability, limited optional skipping, and blunt performance feedback. It must not use humiliation, hostility, or deceptive pressure.

Coaching style changes presentation and accountability, not scoring standards or curriculum evidence.

## Adaptive planning

After each meaningful session, LangCampaign recalculates the campaign using:

- Time actually studied
- Mission-check and simulation performance
- Hint dependence
- Retention and review needs
- Missed or shortened sessions
- Remaining time
- Remaining mission requirements and priorities

When the campaign falls behind, adaptation occurs in this order:

1. Remove optional enrichment.
2. Focus on weak, mission-critical capabilities.
3. Shorten or combine lower-priority missions.
4. Recommend a specific, realistic increase in study time.
5. If the original result is no longer plausible, offer a narrower goal or a revised target date.

LangCampaign must explain material plan changes to the learner.

## Assessment model

### Mission checks

Short assessments follow individual units. Depending on the mission, they evaluate:

- Task completion
- Comprehension
- Independent sentence construction
- Register appropriateness
- Grammatical clarity
- Reliance on hints
- Response speed when meaningfully measurable

### Campaign simulations

Simulations combine several mission capabilities in an unfamiliar sequence. They test transfer and recovery from misunderstandings, not memorization of lesson dialogue.

### Approximate CEFR estimate

CEFR estimates must be evidence-based, conservative, and limited to observed modalities. Acceptable wording includes **approximately A2 in guided written interaction**. LangCampaign must not claim an official overall level from text-only evidence or produce false precision such as a decimal CEFR score.

## Progress model

LangCampaign reports three separate concepts:

1. **Mission readiness:** Current demonstrated ability on required campaign tasks.
2. **Target-date forecast:** Projected readiness at the target date based on current evidence and pace.
3. **Training progress:** Work completed compared with the current plan.

These values must never be collapsed into a single percentage. Completing lessons does not prove readiness. Study time may improve the forecast, but readiness changes only through performance evidence. Readiness may decrease when retention checks reveal forgetting; when this happens, LangCampaign explains why.

### Reporting rhythm

- Compact update after every meaningful session
- Expanded report every seven days
- Immediate alert when status changes to at risk
- Full readiness report after each campaign simulation
- On-demand report whenever the learner requests it

### Canonical text presentation

The canonical report works in plain text so it remains portable across terminals and agent platforms. Emoji are an optional, subtle enhancement and never the sole carrier of meaning.

```text
SPANISH TRAVEL CAMPAIGN · 18 days remaining

Mission readiness  [███████████░░░░░░░░░] 54%
Target-date status [██████████████░░░░░░] AT RISK
Training completed [████████░░░░░░░░░░░░] 4.2 / 10 hours

✓ Ordering and paying
✓ Hotel check-in
◐ Asking for directions
△ Handling unexpected replies
○ Explaining a travel problem

Current strength: making practical requests
Next priority: understanding follow-up questions

At your current pace: 67% projected readiness
To get back on track: add two 25-minute sessions this week
```

Suggested optional symbols are:

- `✅` demonstrated independently
- `🟡` partial or prompt-dependent
- `⬜` not yet assessed
- `🔁` review due
- `⚠️` target-date risk
- `🎯` current priority

Text labels must accompany symbols where their meaning would otherwise be ambiguous.

## Readiness evidence and scoring constraints

- Lesson attendance alone cannot raise readiness.
- The same performance standards apply across coaching styles.
- Capability weights come from their importance to the campaign goal.
- Unassessed capabilities are shown as unassessed, not treated as demonstrated.
- A readiness estimate identifies the evidence and recency on which it is based.
- A forecast identifies the assumed future pace.
- Low-confidence estimates are labeled as such rather than displayed with false precision.

The exact scoring formula and confidence thresholds belong in a separate assessment specification. This design establishes the required inputs, distinctions, and user-facing behavior.

## Portability boundary

The training model is platform-neutral. Core campaign state, assessments, replanning rules, and reports must not depend on Claude-specific hooks, Codex-specific skill discovery, or a particular chat interface. Platform adapters may provide lifecycle automation and richer presentation without changing the underlying semantics.

## Acceptance criteria

The initial implementation design must ensure that:

1. A campaign has an explicit goal, target date, curriculum scope, and coaching style.
2. Balanced and Supportive are the defaults.
3. Curriculum scope and coaching style can vary independently.
4. Actual study and assessed performance trigger replanning.
5. Mission readiness, target-date forecast, and training progress remain distinct.
6. Falling behind produces an explicit risk notice and actionable recovery options.
7. Reports render meaningfully without emoji, color, or graphical UI.
8. CEFR language is approximate, modality-specific, and evidence-based.
9. Platform adapters do not redefine campaign scoring or state semantics.

