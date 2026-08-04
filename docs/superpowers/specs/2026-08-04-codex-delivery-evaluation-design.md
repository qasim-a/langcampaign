# LangCampaign Codex Delivery and Evaluation Design

**Date:** 2026-08-04
**Status:** Approved in conversation; awaiting written-spec review

## Objective

Deliver LangCampaign as a genuinely installable Codex plugin that lets a
learner create, continue, assess, pause, transition, and resume goal-driven
language campaigns through natural conversation. The learner must not need to
clone the repository, install the Python package, manage JSON, choose storage
paths, or know engine command names.

This is the final MVP milestone. It packages the existing campaign engine and
mission runtime into a usable Codex learning experience and adds end-to-end
workflow evaluation. ChatGPT, Claude, hosted persistence, accounts, and voice
remain post-MVP.

## Product boundary

The MVP is a skills-only Codex plugin with a bundled local Python engine. It
does not start an MCP server, call a hosted LangCampaign service, or require
authentication.

```text
Learner conversation
        ↓
Codex skill: interaction and teaching policy
        ↓
Platform-neutral adapter: stable structured commands
        ↓
LangCampaign engine: validation, state, evidence, progress
        ↓
User-level local storage
```

Only invocation metadata and host-specific operational instructions belong to
Codex. Campaign schemas, generation contracts, assessment rules, learner-facing
copy templates, evaluation fixtures, and adapter behavior remain
platform-neutral so later Claude or ChatGPT integrations can reuse them.

Future-proofing means maintaining this boundary. It does not authorize building
or testing another platform adapter in the MVP.

## Installation experience

The GitHub repository is also the plugin package. A supported Codex user
installs LangCampaign from the repository or a marketplace entry and begins in
a new conversation. The installed plugin contains the engine source and invokes
it directly from its installed location; it does not require `pip install`, a
virtual environment, or a separately cloned development checkout.

Proposed package shape:

```text
langcampaign/
├── .codex-plugin/plugin.json
├── skills/
│   └── langcampaign/
│       ├── SKILL.md
│       └── agents/openai.yaml
├── workflow/
│   ├── learner-policy.md
│   ├── generation-contracts.md
│   ├── presentation.md
│   └── examples.md
├── scripts/
│   ├── check_install.py
│   └── langcampaign_adapter.py
├── evaluation/
│   ├── scenarios/
│   └── README.md
└── src/langcampaign/
```

The plugin requires Python 3.11 or newer. The installation check finds a
compatible interpreter, verifies the bundled package imports without modifying
global Python state, resolves personal storage, creates a stable local profile
when absent, and executes a non-destructive status probe.

The adapter uses only the Python standard library. It supports macOS, Linux,
and Windows without a shell-specific runtime dependency. If no compatible
interpreter exists, the plugin reports that single requirement with concise
platform-appropriate guidance rather than attempting a privileged or networked
installation.

Plugin upgrades never delete or relocate learner data automatically.

## Personal storage and identity

The installed learner experience uses a personal data directory independent of
the current repository or Codex workspace:

- macOS: `~/Library/Application Support/LangCampaign`
- Linux: `$XDG_DATA_HOME/langcampaign` when set, otherwise
  `~/.local/share/langcampaign`
- Windows: `%LOCALAPPDATA%\LangCampaign`

The root contains a versioned `profile.json` and the existing `learners/`
repository. Path resolution uses the standard library, rejects missing required
Windows environment state with an actionable installation error, and never
falls back to the current working directory.

The MVP has one automatic local learner profile. During the first successful
installation check, the adapter creates an opaque stable learner identifier
using secure random generation and stores it atomically. It does not ask for a
name, account, email, or learner ID. Every later conversation reuses this
identifier. Campaign setup never creates a second identity.

Malformed, symlinked, or unsupported profile/storage entries fail safely.
Multiple local profiles, login, synchronization, import, and account migration
are post-MVP. A documented export and reset procedure gives the learner control
of local data; reset requires explicit confirmation and is never inferred from
ordinary conversation.

## Invocation boundary

The workflow supports explicit and implicit invocation.

- Explicit: the learner invokes `$langcampaign` and states a request.
- Implicit: Codex activates LangCampaign for a clear request to create,
  continue, assess, pause, transition, resume, or inspect a language-learning
  campaign.

It does not implicitly activate for a one-off translation, grammar question,
pronunciation question, foreign-language writing edit, or general discussion
about language learning. A user may explicitly invoke LangCampaign for those
requests when they want the result connected to a campaign.

The skill description must encode this positive and negative scope clearly.
Explicit invocation always wins.

## Learner setup

A first-time learner may say:

> Help me learn Spanish so I can talk comfortably with my partner's family. I
> know basic Spanish and have about two hours a week.

The skill extracts:

- Target language.
- Practical goal.
- Optional deadline.
- Realistic weekly time.
- Compact prior-knowledge description.

It asks only for genuinely missing information needed to create a coherent
campaign. Setup remains one short exchange when the opening request is
sufficient. It silently uses the fixed Flexible/Targeted, Balanced, and
Supportive defaults established by the engine.

Codex generates a coarse roadmap, two or three upcoming mission outlines, and
detailed compact content plus a weighted rubric only for the first mission. It
validates the campaign and content through the adapter. One invalid content
candidate receives one bounded correction using the returned structured issues;
a second invalid candidate stops with a concise retry option.

After successful persistence, Codex briefly explains the campaign and begins
the first mission. It does not reveal internal assumptions, complete roadmap,
JSON, revisions, rubric arrays, or engine commands unless an explicit developer
diagnostic is requested.

## Mission conversation

One mission remains one continuous Codex conversation:

```text
🎯 Practical capability and scenario
→ focused teaching
→ guided practice with decreasing support
→ clearly announced no-hints check
→ independent response evaluation
→ persisted evidence and outcome
→ compact progress and next action
```

Codex generates learner-facing language while the adapter and engine own the
durable checkpoint. For a normal learner message, the workflow uses at most one
model generation and one local state mutation. It never creates separate
planner, teacher, and assessor calls for one interaction.

The no-hints boundary is explicit. Codex evaluates the learner against the
persisted mission rubric and submits criterion scores once. The engine derives
the authoritative numeric score and pass/partial/retry outcome. If Codex gives
material help after announcing the check, it must return to guided practice,
refresh content when required, and not submit that response as independent.

The engine cannot inspect prose and prove that Codex withheld hints. The skill
must describe this honestly and evaluation must test for hint leakage.

The learner may say `too easy` or `too hard` at any point before assessment.
Codex maps the phrase to the deterministic adjustment command, refreshes
content when required, and continues without rebuilding the roadmap.

## Resume and campaign management

A fresh conversation resolves the local profile and active campaign before
asking the learner to repeat context. A normal resume contains only the current
language, mission title, checkpoint, campaign-goal progress, and immediate
continuation:

```text
🟡 Spanish campaign resumed

Current mission: Ask natural follow-up questions
Status: Guided practice
Progress  ████░░░░░░  40%

Continue when you're ready.
```

Natural requests map to existing engine behavior:

- Continue the active campaign.
- Show compact progress.
- Reveal the sanitized roadmap only on request.
- List active, paused, and completed campaigns.
- Pause the active campaign without selecting a replacement. This milestone
  adds one public `pause-campaign` engine command that atomically clears the
  active learner-index pointer while preserving campaign state. The adapter
  never edits the index directly.
- Start a materially new goal through campaign transition, carrying only
  explicitly mapped evidence.
- Resume a paused campaign.
- Explicitly complete a campaign.

When several campaigns could satisfy a vague resume request, Codex presents a
short numbered choice and does not guess. Completed campaigns remain history
and cannot be resumed.

## Presentation policy

The fixed learner style is concise, candid, and encouraging without an
excessively celebratory tone.

- Use one colored status emoji when status is material.
- Use the engine's ten-segment progress bar after meaningful work.
- Credit demonstrated and partial accomplishments clearly.
- Correct errors directly and specifically.
- State the next action.
- Avoid decorative emoji patterns, banners, long motivational paragraphs,
  CEFR estimates, and rich dashboards.

Reusable learner-facing templates live outside the Codex-specific skill so a
later adapter can produce the same experience.

## Adapter contract

`scripts/langcampaign_adapter.py` is the only script the skill invokes. It
accepts a platform-neutral operation and one JSON request on standard input,
supplies the resolved learner profile and storage root, invokes the public
LangCampaign command boundary, and writes exactly one JSON response to standard
output.

The adapter does not parse, read, or write campaign `state.json` or learner
`index.json` directly. Profile creation is its only storage responsibility.
Campaign operations remain behind the public engine boundary.

The adapter's operation names and response objects do not mention Codex. A
future MCP or Claude adapter can call the same layer. Codex-specific prompt
instructions translate natural language into these operations and translate
structured outcomes into learner-facing prose.

Expected stale revisions cause one safe status reload. The adapter retries a
mutation only when the operation is defined as idempotent or when no mutation
was published. It never blindly repeats an assessment or setup request.

## Failure behavior

- No campaign: offer setup.
- Ambiguous campaign: present a concise choice.
- Invalid content candidate 1: use the returned issues for one correction.
- Invalid content candidate 2: stop and offer a clean retry.
- Stale revision: reload once and either safely retry or ask the learner to
  continue from the refreshed state.
- Persistence failure: say progress was not saved and never claim completion.
- Unsupported environment: report the smallest actionable requirement.
- Missing or malformed personal profile: do not guess an identity or use the
  current directory.
- Unexpected programmer fault: expose a concise diagnostic and nonzero status;
  do not relabel it as learner error.

The adapter preserves exactly-one-JSON-output behavior. The skill converts
expected errors into learner-facing recovery without showing stack traces.
Developer diagnostic details remain available in test/debug output.

## Privacy and data ownership

LangCampaign campaign state, evidence, profile, and generated compact mission
content stay in the personal data directory. The plugin does not add telemetry,
accounts, hosted storage, or third-party network calls.

Documentation distinguishes local LangCampaign persistence from the model
conversation itself, which remains governed by the learner's Codex/OpenAI
environment and policies.

The README documents how to locate, export, and explicitly reset local data.
It does not imply that uninstalling the plugin deletes learning history.

## Evaluation architecture

Evaluation has two layers.

### Deterministic automated tests

Tests cover:

- Plugin manifest and skill-package structure.
- Python 3.11 environment detection and unsupported-version errors.
- macOS, Linux/XDG, Linux fallback, and Windows data-directory resolution.
- Atomic profile creation, reuse, corruption, symlink rejection, and explicit
  reset confirmation.
- Adapter request/response and exactly-one-JSON behavior.
- Setup, status, resume, explicit pause, transition, and completion routing.
- First-mission generation and one-correction validation flow.
- Teaching, guided practice, no-hints, assessment, progress, and next action.
- `too easy`, `too hard`, and accidental-help recovery.
- Safe stale-revision recovery and duplicate assessment handling.
- Persistence failure honesty and programmer-fault propagation.
- Fresh-process recovery with no transcript.
- No direct campaign JSON access from the adapter.
- Representative local latency without network or model calls.

### Codex workflow scenarios

Versioned scenario fixtures cover:

1. Complete beginner with a travel goal.
2. Experienced but rusty learner.
3. Casual texting or social-media goal.
4. Partial independent performance.
5. Struggling learner who says `too hard`.
6. Learner who says `too easy`.
7. Accidental help after the no-hints announcement.
8. New goal followed by resuming the previous campaign.
9. Invalid generated mission requiring one correction.
10. Fresh conversation resuming during guided practice and after assessment.

Each scenario declares expected tool sequence and learner-visible properties.
The evaluation rubric scores goal relevance, unnecessary setup questions,
hint leakage, evidence accuracy, generosity without false credit, response
length, visual restraint, persistence, recovery, and model/tool turn count.

Automated CI can validate scenario structure and deterministic adapter traces
without a live model. Release evaluation runs the scenarios in Codex and stores
redacted results; it does not make nondeterministic live-model calls part of
the ordinary unit-test suite.

## Responsiveness

Installation checks and local adapter operations should normally finish in
milliseconds. Representative automated measurements use generous thresholds
to catch accidental sleeps, subprocess loops, repeated imports, or network
access rather than enforce fragile microbenchmarks.

Visible learner latency is primarily one Codex model response. Generation may
take longer than a local status update, but the workflow does not add serial
planning or assessment generations. If Codex performs a genuinely longer
operation, it provides concise progress rather than leaving the learner without
feedback.

## MVP acceptance criteria

The MVP is complete when:

1. A supported user can install LangCampaign as a Codex plugin from the
   repository without manually cloning a development checkout or installing
   the Python package.
2. A compatible Python environment passes a non-destructive installation check;
   an incompatible environment receives one actionable requirement.
3. One natural opening request can create a campaign and begin the first
   mission without exposing settings or engine internals.
4. A learner completes teaching, guided practice, an announced no-hints check,
   persisted assessment, progress, and next action in one continuous workflow.
5. A fresh conversation resumes the exact active checkpoint and persisted
   result without requiring the learner to restate context.
6. Natural requests can inspect, transition, pause, resume, and complete
   campaigns without exposing JSON or command names.
7. Normal learner messages use at most one model generation and one local state
   mutation, except the single bounded content-correction generation.
8. Local campaign data survives plugin updates and remains exportable and
   explicitly resettable.
9. Deterministic tests pass on supported platforms, and release scenario
   evaluation has no unresolved Critical or Important failures.
10. The README is a concise learner guide with installation, starting,
    continuing, data ownership, troubleshooting, and current limitations.

## Explicitly post-MVP

- ChatGPT adapter and hosted MCP tools.
- Claude adapter.
- Hosted or cross-device persistence.
- Accounts, authentication, and multiple learner profiles.
- Voice and pronunciation scoring.
- Custom visual UI or rich dashboards.
- Telemetry and analytics.
- Public marketplace submission beyond a repository-installable package.
- Sophisticated spaced repetition or full-roadmap regeneration.
