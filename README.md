<div align="center">
  <h1>🌍 LangCampaign</h1>
  <h3><em>Train for what you actually want to do with a language.</em></h3>
</div>

<p align="center">
  <strong>A goal-driven language-learning framework for AI agents that turns practical goals into useful missions, evidence-backed progress, and resumable campaigns.</strong>
</p>

---

## Contents

- [What is LangCampaign?](#-what-is-langcampaign)
- [The lean learner journey](#-the-lean-learner-journey)
- [What a mission looks like](#-what-a-mission-looks-like)
- [Progress and adaptation](#-progress-and-adaptation)
- [New goals and resuming](#-new-goals-and-resuming)
- [Core philosophy](#-core-philosophy)
- [Internal engine reference](#-internal-engine-reference)
- [Current status](#-current-status)

## 🎯 What is LangCampaign?

LangCampaign organizes language learning around a **campaign**: a practical
goal you want to accomplish, with or without a deadline.

Preparing for a trip, interview, or presentation is a valid campaign—but so is
texting friends, understanding social-media posts, talking with family,
following online creators, playing games, or enjoying books and shows with
less translation.

LangCampaign turns that goal into small missions. Each mission develops one
useful capability, gives you guided practice, checks what you can do without
hints, and records evidence that informs the next action.

```text
Your goal → Small practical missions → Independent checks → Evidence-backed progress
```

## ⚡ The lean learner journey

> [!NOTE]
> LangCampaign is currently an early-stage framework. The tested campaign
> engine, campaign-content foundation, and lean setup/lifecycle persistence are
> implemented. Installable Codex teaching workflows and generated mission
> conversations remain future work.

### 1. Describe what you need

Setup uses one short exchange and silently applies its fixed defaults. Tell the
agent:

- The target language.
- The practical goal.
- A deadline, if one exists.
- The weekly time you can realistically use.
- A compact description of what you can already do.

You can describe prior knowledge through real situations: “I can text
friends,” “I studied for two years but struggle to speak,” or “I am a complete
beginner.” You do not need a proficiency label or a self-designed curriculum.

Defaults are applied silently. The lean MVP has one fixed presentation and
coaching style: concise, candid, and encouraging. Setup does not ask you to
choose curriculum scope, coaching style, presentation style, or an exact daily
commitment.

Example:

```text
Help me learn Spanish for independently handling a trip to Mexico in October.
I can spend about two hours per week. I studied Spanish in school and can read
simple messages, but I have trouble answering unfamiliar questions.
```

### 2. Begin immediately

Setup creates a coarse internal roadmap, two or three upcoming mission
outlines, and detailed content only for the first mission. The roadmap stays
hidden during normal learning and can be shown as a concise summary if you ask
for it.

The first real mission doubles as calibration. Self-reported knowledge helps
choose the starting difficulty, but only independently demonstrated ability
becomes progress evidence. There is no separate placement examination before
practice begins.

### 3. Continue in small batches

Later mission details are generated as you approach them, using the evidence
already collected. LangCampaign does not need to generate a detailed full
curriculum upfront or rebuild the whole roadmap after every response.

## 🔁 What a mission looks like

One continuous learning conversation follows this sequence:

```text
🎯 Practical capability and scenario
   ↓
Teach only what is needed now
   ↓
Short guided practice with decreasing support
   ↓
Clearly announced no-hints check
   ↓
Evidence, compact progress, and next action
```

The no-hints check is independent in the educational sense. Language
introduced or corrected during the check is not credited as something you
demonstrated independently in that same check.

## 📊 Progress and adaptation

Normal progress is intentionally compact: one colored status emoji, one short
evidence-based result, a text progress bar, and the next mission or review.

```text
✅ Mission passed

You explained the delay, gave a revised arrival time, and answered the
follow-up without hints.

Progress  ██████░░░░  60%

Next: handle an unexpected reservation problem.
```

Adaptation stays local and understandable:

- A pass records evidence and advances.
- Partial performance preserves earned credit and schedules focused practice
  or a retry.
- `too easy` raises the next mission's difficulty.
- `too hard` adds prerequisite support before a retry.
- A previously demonstrated capability that later fails is marked for review.

The lean learner view does not include a rich dashboard, long motivational
summary, proficiency estimate, multi-mission simulation, or full forecast
controls.

## 🔄 New goals and resuming

Campaigns have three learner-relevant states:

- **Active:** currently guiding learning.
- **Paused:** preserved and resumable.
- **Completed:** intentionally finished and retained as history.

A materially new goal starts a new campaign instead of editing the existing
goal in place. LangCampaign pauses the current campaign, creates the new one,
and carries forward only explicitly mapped evidence-backed capabilities. The
previous campaign keeps its roadmap, evidence, and progress and can be resumed
later. Exactly one campaign is active at a time.

Resuming a paused campaign preserves its state and normally pauses whichever
campaign is currently active.

## 🌱 Core philosophy

- **Train for real use.** Accomplishing the learner's goal matters more than
  completing a generic course.
- **Casual goals count.** Friendship, family, entertainment, and online
  participation are legitimate reasons to learn.
- **Credit demonstrated ability.** Self-report can guide difficulty, but
  progress comes from evidence.
- **Generate only what is useful now.** Keep the roadmap coarse and mission
  details small-batch.
- **Adapt without erasing progress.** Preserve earned credit, prior campaigns,
  and resumable context.
- **Keep the interaction responsive.** Routine learner actions should need no
  more than one model response and one local LangCampaign command.

## 🛠️ Internal engine reference

The platform-neutral engine predates the lean learner workflow and retains
tested APIs for Targeted and Flexible campaign records, configurable stored
curriculum/coaching fields, readiness calculations, approximate CEFR
summaries, target-date forecasts, campaign revision, and richer progress
rendering. These capabilities remain for schema compatibility and internal
development reference; they are not configuration choices or output promises
in the approved lean learner journey.

The campaign-content foundation adds validated mission maps, a coarse hidden
roadmap, repository-local learner state, atomic persistence, and five JSON
commands for future Codex workflows. Only an explicit `show-roadmap` command
reveals a sanitized phase summary; normal setup, validation, and listing
responses omit roadmap details and assumptions.

## 🚧 Current status

The command boundary now validates generated mission maps, stores learner state
under `learners/`, applies lean setup defaults, retains prior-knowledge context
without crediting it as evidence, and supports active/paused/completed campaign
lifecycle commands. The roadmap remains out of normal session output but can
be summarized when a learner asks to see it.

Generated mission conversations, installable Codex teaching workflows,
end-to-end learner evaluation, latency checks, and product hardening remain
future work. LangCampaign is not an accredited language-testing body.
