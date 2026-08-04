# LangCampaign Lean MVP Scope Design

**Date:** 2026-08-03
**Status:** Approved

## Delivery sequence

The scope is deliberately split into independently reviewable plans rather
than one large implementation plan:

1. Complete the existing campaign-content foundation plan: Task 6, whole-branch
   review, verification, and integration.
2. Campaign lifecycle and fast setup: fixed defaults, prior-knowledge context,
   active/paused/completed state, and resumable campaign transitions.
3. Lean mission runtime: small-batch generation, guided practice, no-hints
   checks, evidence capture, simple difficulty adjustment, and compact progress.
4. Codex delivery and evaluation: installable Codex workflow, end-to-end learner
   fixtures, latency checks, and product hardening.

Each post-foundation subsystem receives its own implementation plan after the
foundation API is finalized. This prevents downstream plans from depending on
interfaces that whole-branch review may still change.

## Objective

Deliver a simple, responsive language-learning product that proves
LangCampaign's central promise: turn a learner's practical goal into useful
missions, teach and assess those missions, preserve evidence-backed progress,
and resume later without reconstructing context.

The MVP optimizes for time to first practice and one-response interactions. It
does not expose configuration merely because the underlying engine supports it.

## Product principles

1. A learner should normally receive a useful response after one agent turn and
   one local LangCampaign command.
2. Setup should take one short conversational exchange and usually less than
   two minutes of learner time.
3. Generate only enough detail to act now. Future curriculum remains a coarse
   hypothesis.
4. Give accurate, generous credit for demonstrated ability without treating
   self-report as proof.
5. Preserve past work when goals change, but keep each campaign internally
   coherent.
6. Prefer deterministic local computation for validation, persistence,
   selection, scoring, and progress rendering. Use the language model for
   interpretation, teaching, and content generation.

## Fixed learner experience

The MVP has one presentation and coaching style. It is concise, candid, and
encouraging without an excessively celebratory tone.

- Use colored emojis to communicate status.
- Use a compact text progress bar after meaningful work.
- Avoid decorative color, emoji patterns, banners, and repeated praise.
- Correct errors directly and specifically.
- Credit accomplishments clearly and avoid minimizing partial success.
- Keep assessment standards independent of tone.

Example:

```text
✅ Mission passed

You explained the delay, gave a revised arrival time, and answered the
follow-up without hints.

Progress  ██████░░░░  60%

Next: handle an unexpected reservation problem.
```

The MVP does not expose coaching-style selection or support changing style
during a session. Existing stored style fields may remain for schema
compatibility, but the learner experience uses the fixed style.

## Setup and prior knowledge

Setup asks only for information needed to begin:

1. Target language.
2. Practical goal.
3. Deadline, if one exists.
4. Realistic weekly time.
5. A compact description of existing ability.

The learner may describe ability through situations rather than proficiency
labels. Examples include texting friends, reading social posts, having studied
for several years, or being a complete beginner.

Defaults are applied silently where possible. The MVP does not ask the learner
to choose curriculum scope, coaching style, presentation style, or an exact
daily commitment.

Self-reported ability influences the starting difficulty but is not recorded
as demonstrated progress. The first real mission also acts as calibration. It
confirms applicable skills, identifies missing prerequisites, and awards
evidence-backed credit without requiring a separate placement examination.

Learners can say `too easy` or `too hard`. These signals adjust the next
mission's difficulty; they do not regenerate the entire roadmap or count as
assessment evidence.

## Planning and generation

At setup, LangCampaign creates:

- A coarse internal roadmap.
- Two or three upcoming mission outlines.
- Detailed teaching, practice, and assessment content for the first mission
  only.
- A concise learner-facing brief and immediately actionable first mission.

The roadmap stays hidden by default and remains revealable on request. Later
mission details are generated in small batches as the learner approaches them,
using accumulated evidence. LangCampaign does not generate a detailed full
curriculum upfront.

Generated content is validated once before activation. A validation failure may
trigger one bounded correction attempt. If that attempt fails, the agent
returns a concise error instead of entering an open-ended regeneration loop.

## Mission runtime

A mission uses one continuous agent conversation:

1. State the practical capability and scenario.
2. Teach only the language and context needed now.
3. Run short guided practice with decreasing support.
4. Clearly announce a no-hints check.
5. Evaluate the learner's independent response.
6. Submit one structured evidence record.
7. Show compact progress and the next action.

Teaching and assessment do not require separate agents or serial model calls.
The no-hints phase is independent in the educational sense: language introduced
or corrected during the check is not credited as independently demonstrated in
that check.

## Simple adaptation

The MVP adapts locally rather than rebuilding the whole campaign:

- Pass: record evidence and advance.
- Partial performance: preserve earned credit and schedule focused practice or
  a retry.
- Too easy: increase the next mission's difficulty.
- Too hard: add prerequisite support before retrying.
- Previously demonstrated skill later fails: mark it for review.

The first version may use a simple mission-level `review due` rule. It does not
require vocabulary-card scheduling, complex interval algorithms, or automatic
full-roadmap replanning after every result.

## Campaign lifecycle and goal changes

Campaigns have three learner-relevant lifecycle states:

- **Active:** currently guiding learning.
- **Paused:** preserved and resumable.
- **Completed:** intentionally finished and retained as history.

Only one campaign is normally active for a learner. Resuming a paused campaign
pauses the currently active campaign.

The MVP does not edit an existing campaign's goal. A materially new goal starts
a campaign transition:

1. Pause the current campaign.
2. Create a new campaign for the new goal.
3. Carry forward relevant evidence-backed capabilities.
4. Use self-reported knowledge only to choose initial difficulty.
5. Confirm uncertain or goal-specific capabilities through the first mission.

The previous campaign remains resumable with its roadmap, evidence, and
progress intact. Domain-specific vocabulary or procedures are not carried
forward merely because they appeared in the previous campaign.

## Progress presentation

Progress is rendered deterministically from stored state rather than requiring
another model call. The normal display contains:

- A colored status emoji.
- One short evidence-based result statement.
- A compact text progress bar.
- The next mission or review.

The MVP does not include a graphical dashboard, long motivational summaries,
CEFR estimation, decorative banners, or coaching-specific render variants.

## Architecture and latency

The runtime path is:

```text
Learner message
  → one Codex workflow
  → at most one content-generation/teaching response
  → one local LangCampaign command for validation and persistence
  → compact learner-facing result
```

Local Python validation, JSON commands, and repository persistence should not
create perceptible waiting time. User-visible latency is governed primarily by
model calls. The design therefore avoids:

- Separate planner, teacher, and assessor calls for one interaction.
- Detailed full-curriculum generation.
- Automatic roadmap regeneration after every assessment.
- Repeated validation-regeneration loops.
- Additional agent-platform adapters before the Codex flow is proven.

## Explicitly deferred

- Coaching-style selection and mid-session style changes.
- Curriculum-scope selection.
- In-place goal editing.
- Full placement examinations.
- Detailed full-campaign generation.
- Automatic full-roadmap replanning after each result.
- Multi-mission simulations.
- CEFR estimates.
- Sophisticated spaced-repetition scheduling.
- Natural-language editing of every campaign setting.
- Rich progress dashboards.
- Claude and other agent integrations.

These features may be reconsidered only after observed learner needs justify
their development and latency costs.

## Failure behavior

- Invalid generated content is never persisted.
- One bounded correction attempt is allowed for invalid mission generation.
- A missing or ambiguous campaign produces a concise choice or setup prompt.
- Failure to record assessment evidence leaves readiness unchanged.
- A failed campaign transition leaves the existing campaign active.
- Programmer faults are not converted into learner-input errors.

## Acceptance criteria

The lean MVP is successful when:

1. A new learner completes setup in one short exchange and reaches the first
   practice activity without navigating settings.
2. A learner with prior knowledge begins at a plausible difficulty and can earn
   immediate evidence-backed credit in the first mission.
3. A learner completes teaching, guided practice, a no-hints check, evidence
   persistence, and a progress update in one continuous session.
4. A fresh session resumes the active campaign without requiring the learner to
   restate prior context.
5. `too easy` and `too hard` adjust the next action without rebuilding the full
   roadmap.
6. A new goal creates a new active campaign, pauses the former campaign, and
   carries forward only relevant evidence-backed capability.
7. The learner can explicitly resume the paused campaign with its state intact.
8. Normal progress output uses colored emojis and a compact progress bar but no
   excessive decorative presentation or encouragement.
9. Routine learner actions require no more than one model response and one local
   command; bounded mission-generation correction is the documented exception.

## Estimated remaining effort after the foundation

Using the mission-content model as `1×`, the lean post-foundation MVP is
approximately `5–7×`:

- Codex integration: `1–1.5×`.
- Short setup and small-batch generation: `1.5–2×`.
- Teaching, practice, and no-hints check: `2–2.5×`.
- Evidence, simple progression, and compact progress: `1–1.5×`.
- End-to-end evaluation and hardening: `1–1.5×`.

Some work overlaps across these slices, so the totals are not purely additive.
