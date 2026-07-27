# LangCampaign Codex Vertical Slice

**Status:** Approved design  
**Date:** 2026-07-27

## Objective

Deliver the first complete learner experience:

> A learner can create, complete, save, and resume a real language campaign through Codex without touching Python.

This milestone turns the existing campaign engine into a usable language-learning framework. It proves one platform end to end before the shared workflow is adapted to Claude or other agents.

## Successful learner journey

A learner opens Codex in the LangCampaign repository and says:

```text
Start a LangCampaign.
```

Codex then:

1. Conducts a short setup interview.
2. Creates a Targeted or Flexible campaign.
3. Shows a concise campaign brief and the next few priorities.
4. Generates and persists a coarse internal campaign roadmap.
5. Runs the first learning mission.
6. Conducts an independent mission check.
7. Converts demonstrated performance into structured evidence.
8. Updates readiness, any applicable forecast, and training progress.
9. Saves resumable learner state.
10. Displays a coaching-aware progress report.

In a later Codex session, the learner says:

```text
Continue my Spanish campaign.
```

Codex locates the campaign, loads its evidence and plan, selects the appropriate mission or review, and continues without asking the learner to reconstruct prior context.

## Scope

### Included

- Campaign setup interview
- Mission and mission-map schemas
- Deterministic campaign-planning rules
- Generated mission content
- Structured teaching-session protocol
- Mission checks and assessment evidence
- Basic mission-capability review scheduling
- Campaign setup, learn, review, simulate, progress, and update skills for Codex
- Automatic state loading, validation, and saving
- A repository-local learner-data layout
- Codex installation/bootstrap and health check
- Deterministic end-to-end learner fixtures
- README instructions that become operational rather than aspirational

### Excluded

- Claude and other agent adapters
- Graphical user interface
- Speech recognition, pronunciation scoring, or audio generation
- Accredited or official CEFR certification
- A learned forecasting model
- Cloud accounts, synchronization, or multi-user hosting
- A large pre-authored language-content catalog
- Full vocabulary flashcard or general-purpose spaced-repetition system

## Architecture

```text
Learner
   ↓
Codex LangCampaign skills
   ↓
Shared teaching and assessment protocols
   ↓
Python command boundary
   ↓
Existing LangCampaign engine
   ↓
Repository-local versioned learner state
```

The AI agent owns conversation, explanation, role-play, feedback, and generation of learning content. Python owns validation, deterministic state transitions, evidence persistence, readiness calculations, forecasting, review scheduling, and report data.

Agent instructions must not calculate readiness or modify learner JSON directly. They call a narrow command boundary that validates input and writes state atomically.

## Repository layout

```text
.agents/
└── skills/
    ├── langcampaign-setup/
    ├── langcampaign-learn/
    ├── langcampaign-review/
    ├── langcampaign-simulate/
    ├── langcampaign-progress/
    └── langcampaign-update/

src/langcampaign/
├── cli.py
├── missions.py
├── planning.py
├── reviews.py
└── sessions.py

protocols/
├── teaching.md
├── assessment.md
└── mission-generation.md

learners/
└── .gitkeep

tests/
├── fixtures/
└── ...
```

`learners/` contents are git-ignored by default. Learner data must never be committed accidentally.

## Learner identity and campaign selection

The first setup asks for a learner name or short local identifier. Identifiers are normalized into safe directory names and never used as authentication.

Each learner may have multiple campaigns. State is stored as:

```text
learners/<learner-id>/<campaign-id>/state.json
```

Codex selects a campaign using this order:

1. Explicit learner and campaign named by the user.
2. The only active campaign for the selected learner.
3. A concise choice when multiple active campaigns exist.

It must not guess when two campaigns are plausible.

## Setup interview

The setup workflow collects only information needed to construct the first plan:

- Target language
- Concrete goal and target situations
- Targeted or Flexible campaign type
- Target date for Targeted campaigns
- Expected and minimum realistic study availability
- Existing ability and relevant experience
- Curriculum scope
- Coaching style
- Preferred activities, interests, and content
- Interaction limitations, including text-only evidence

Balanced curriculum and Supportive coaching remain defaults. Flexible is recommended when no date-bound event exists.

The setup agent summarizes the proposed campaign and asks for confirmation before writing state.

## Setup outputs and roadmap visibility

After confirmation, setup creates two different views of the campaign.

### Learner-facing campaign brief

The learner sees a short orientation containing:

- Confirmed goal and target date when applicable
- Campaign type, curriculum scope, and coaching style
- Expected study rhythm
- A one-sentence explanation of the training approach
- The next three priorities
- The immediately actionable first mission
- Estimated duration of that mission

The brief does not display the entire projected curriculum. Its purpose is to confirm direction and make the next action obvious.

### Internal campaign roadmap

LangCampaign persists a coarse, adaptable planning scaffold containing:

- Broad training phases
- Capabilities expected within each phase
- Critical dependencies
- Approximate sequencing and time allocation
- Planned review and simulation points
- Assumptions that may require reassessment

The roadmap stays deliberately vague. It is a planning hypothesis based on limited initial evidence, not a fixed promise or detailed lesson schedule.

It is hidden during normal sessions to prevent information overload, but it is not secret. When the learner asks to **show my campaign roadmap**, LangCampaign provides a readable summary of phases, current position, major completed capabilities, and likely next areas. It does not expose hidden reasoning or internal chain-of-thought.

LangCampaign always discloses material consequences even when the roadmap is not shown, including:

- Target-date risk
- Increased study requirements
- Removal of missions because of time pressure
- A recommendation to narrow the goal or revise the date
- Major changes to the next priorities

After assessments or campaign updates, the roadmap may reorder phases, expand weak capabilities, collapse material already demonstrated, add reviews, or change simulation timing. The learner-facing view remains focused on the next useful steps.

## Mission model

A generated mission contains:

- Stable identifier
- Learner-facing title
- Observable real-world capability
- Rationale tied to the campaign goal
- Priority: critical, supporting, or enrichment
- Weight for readiness calculations
- Prerequisite mission identifiers
- Target vocabulary, structures, register, and cultural context
- Guided practice activities
- Independent assessment scenario
- Explicit success criteria
- Common failure patterns
- Review status and scheduling data

Mission titles describe capabilities, not textbook topics. Use **Explain a delayed arrival** rather than **The future tense**.

The planner rejects mission maps with duplicate identifiers, missing prerequisites, circular prerequisites, non-observable capabilities, or no critical missions.

## Campaign planning

The planner generates a coarse internal roadmap and a detailed mission map for only the next meaningful phase rather than pretending to know the entire future curriculum. Later phases remain broad until evidence justifies generating their missions.

Planning follows this order:

1. Decompose the goal into real situations.
2. Identify observable capabilities for each situation.
3. Mark critical, supporting, and enrichment capabilities.
4. Add prerequisites.
5. Apply curriculum scope.
6. Fit the plan to available time and target date.
7. Add mission checks, reviews, and campaign simulations.

The planner then derives the learner-facing next three priorities from the active phase. These priorities must agree with the internal roadmap but omit speculative later-phase detail.

Mission Focused suppresses most enrichment. Balanced includes transferable context. Foundational adds broader context only when it does not silently displace required campaign work.

Generated mission maps are validated by Python before becoming active.

## Teaching-session protocol

Every learning session follows this sequence:

1. Load and validate state.
2. Check for overdue or high-priority reviews.
3. Select the highest-value available mission.
4. Show the session goal and estimated duration.
5. Elicit existing knowledge before explaining.
6. Teach only the language and context needed for the mission.
7. Run guided practice with progressively fewer hints.
8. Clearly announce the independent mission check.
9. Conduct the check without hidden assistance.
10. Produce structured assessment evidence.
11. Ask Python to record evidence and update state.
12. Show progress, the next priority, and any recovery action.

The agent distinguishes teaching from assessment. Material introduced or corrected during an independent check cannot be credited as independent performance in that check.

## Assessment contract

Assessment uses an agent-produced record validated by Python. Each record contains:

- Mission identifier
- Modality
- Task-completion score
- Comprehension score
- Independent-construction score
- Register score when relevant
- Grammatical-clarity score
- Hint count and hint severity
- Misunderstanding-recovery result when relevant
- Independence flag
- Approximate CEFR evidence when supported
- Concise evidence summary
- Timestamp

The engine derives the normalized mission score from rubric fields; the agent does not submit an unexplained final readiness score.

The evidence summary identifies what the learner accomplished and the main limitation. It must not include hidden reasoning or vague claims such as “did well.”

## Review scheduling

The first version schedules mission capabilities, not individual vocabulary cards.

Each assessed mission receives:

- Last assessment time
- Next review time
- Consecutive successful reviews
- Current review interval
- Review outcome history

Independent success increases the interval. Prompt-dependent or failed performance shortens it and may return the mission to Developing. Critical overdue reviews take precedence over new enrichment missions.

The algorithm must be deterministic, documented, and replaceable. A full vocabulary SRS is outside this milestone.

## Codex skills

### `langcampaign-setup`

Creates a learner and campaign through the setup interview, generates the initial mission map, validates it, saves state, and offers the first mission.

### `langcampaign-learn`

Loads the selected campaign and runs the teaching-session protocol. It never edits state directly.

### `langcampaign-review`

Selects due capabilities and runs retrieval or transfer checks before recording new evidence.

### `langcampaign-simulate`

Combines multiple demonstrated or developing missions into an unfamiliar scenario and records evidence for each capability actually observed.

### `langcampaign-progress`

Renders mission readiness, forecast where applicable, training progress, strengths, limitations, due reviews, and next priority. On explicit request, it also renders the learner-readable roadmap summary.

### `langcampaign-update`

Changes goals, dates, time commitments, campaign type, curriculum scope, coaching style, or preferences through validated engine operations. It explains material effects and preserves relevant evidence.

Natural phrases such as **start a LangCampaign**, **continue my Spanish campaign**, **review what is due**, **show my progress**, and **change my deadline** should activate the appropriate workflow.

## Python command boundary

The command interface exposes structured JSON input and output for agent skills. Required operations are:

- `setup`
- `list-campaigns`
- `show-next`
- `validate-mission-map`
- `record-session`
- `record-assessment`
- `show-progress`
- `show-reviews`
- `update-campaign`
- `validate-state`

Commands return stable machine-readable envelopes with a success flag, data, and actionable error message. Human presentation belongs to the skill, not the command output.

All state-changing commands write atomically. A failed validation leaves the previous state unchanged.

## Coaching and presentation

The existing coaching styles control both language and presentation:

- Supportive uses warm feedback, colorful semantic emoji, and visible celebration of meaningful achievement.
- Direct uses compact, information-first feedback and sparse emoji.
- Boot Camp adds stricter session structure, accountability, and immediate corrective work.

All styles use identical assessment rubrics. No style may inflate or suppress evidence.

## Installation and health check

The Codex-first installation must be repository-local and reversible. It verifies:

- Python 3.11 or later
- LangCampaign package import
- Presence and readability of Codex skills
- Writable learner-data directory
- Successful creation, load, and deletion of temporary test state
- Valid rendering of a sample progress report

The learner-facing completion message is:

```text
✅ LangCampaign is ready for Codex.
🎯 Say: “Start a LangCampaign.”
```

The installer does not modify global Codex configuration in this milestone.

## Error handling

- Missing learner or campaign: offer available choices or setup.
- Ambiguous campaign: ask the learner to choose; never guess.
- Invalid generated mission map: explain the validation error internally, regenerate once, then stop with a concise error if still invalid.
- Corrupt state: preserve the file, refuse mutation, and provide a recovery path.
- Interrupted teaching session: retain the last committed state; unrecorded work is not treated as assessed evidence.
- Failed assessment validation: do not change readiness; ask the agent to produce a corrected structured record.
- Unsupported modality: label it unassessed rather than inferring ability.

## Testing strategy

### Unit tests

- Mission and map validation
- Rubric-to-score calculation
- Review scheduling transitions
- Command-envelope validation
- Learner/campaign selection
- State mutation and rollback behavior

### Protocol fixtures

Deterministic transcripts verify that the skills:

- Separate teaching from independent assessment
- Do not award readiness for attendance
- Use coaching-appropriate presentation
- Preserve casual goals as valid campaigns
- Replan when dates or availability change
- Resume from persisted evidence

### End-to-end acceptance fixtures

1. New learner creates a Flexible casual-conversation campaign.
2. Traveler creates a Targeted campaign and receives a forecast.
3. Learner completes a mission check and receives evidence-backed progress.
4. Learner resumes the campaign in a fresh simulated session.
5. Learner changes availability and sees the forecast update.
6. Failed retention review changes mission status and priority.
7. Campaign simulation records only capabilities actually observed.
8. Malformed agent output cannot corrupt learner state.

## Acceptance criteria

The milestone is complete when:

1. A learner can start a campaign in Codex using natural language.
2. Setup creates a validated mission map and versioned learner state.
3. Setup shows a concise brief with three priorities and one actionable first mission.
4. A coarse internal roadmap is persisted, adapts to evidence, and is hidden by default but revealable on request.
5. Codex can run a complete teaching and independent-assessment session.
6. Assessment evidence, not attendance, updates readiness.
7. A fresh Codex session can resume without reconstructed chat context.
8. Reviews are selected deterministically from persisted scheduling data.
9. Progress and recovery actions follow the selected coaching style.
10. Campaign changes preserve relevant evidence and explain their impact.
11. Learner data is ignored by Git and written atomically.
12. The health check proves the repository-local installation works.
13. End-to-end fixtures cover both Flexible and Targeted campaigns.
14. The README quick start describes commands that work in the repository.
