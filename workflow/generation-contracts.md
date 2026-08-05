# Generation contracts

## Campaign setup

Generate one complete candidate containing:

- A stable opaque campaign ID, practical goal, target language, optional target date, and two or three mission shells.
- A coarse roadmap whose active phase contains an eligible first mission.
- Complete mission plans for the roadmap.
- Compact prior knowledge using only learner-stated facts.
- Detailed `MissionContent` for the first mission only.

Use no caller-owned creation or assessment timestamps. Keep assumptions in the hidden roadmap rather than presenting them as learner facts.

## Mission content

The content bundle contains generation ID, candidate number, exact mission capability, scenario, teaching objectives, essential language, guided prompts, assessment prompt, and rubric. Rubric criterion IDs are unique, weights are positive integers totaling 100, and Codex later scores every criterion with an integer from 0 through 100.

Submit the complete bundle to `validate-content`. If candidate one is invalid, use the ordered issue codes/field paths to generate one complete candidate two. If candidate two fails, stop without mutation and offer a clean retry. Never patch or persist a partially valid bundle.

Generate replacement content only when starting a mission with no persisted bundle or when `content_refresh_required` is true. Preserve the mission capability across replacement.

## Assessment

Use the learner's single independent response as evidence. Produce exactly one score per persisted criterion plus one short evidence-based overall result statement. Do not choose the weighted percentage, outcome, progress, review schedule, or next action; submit criterion scores once and render the engine result.
