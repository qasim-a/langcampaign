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

The GitHub repository is also the plugin package. It contains both the plugin
manifest and the repository marketplace metadata required by Codex. The exact
learner flow is: add the published GitHub repository as a plugin marketplace,
install the `langcampaign` entry in Codex's plugin browser, and begin a new
conversation so discovery refreshes. The learner does not manually clone a
development checkout, run `pip install`, or create a virtual environment.

The repository marketplace name is `langcampaign`, its sole entry is
`langcampaign`, and its local source path is `./`. The reproducible CLI path is
`codex plugin marketplace add qasim-a/langcampaign` followed by
`codex plugin add langcampaign@langcampaign`; the Plugins Directory may present
the same operations visually. Repository updates use
`codex plugin marketplace upgrade langcampaign`, followed by a new conversation.

The README gives those steps literally, with UI labels verified against the
Codex release used for acceptance. It must not advertise a command or one-click
route that Codex does not actually support. A clean-profile test installs from
the published repository using only that documented flow.

Proposed package shape:

```text
langcampaign/
├── .agents/plugins/marketplace.json
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
compatible interpreter, verifies the bundled package imports, resolves personal
storage, creates a stable local profile when absent, and executes a
non-destructive status probe.

The adapter derives the plugin root from its own resolved file path, never from
the process working directory. It verifies the expected manifest and bundled
`src/langcampaign/__init__.py`, prepends that exact `src/` directory to the
process-local import path, imports LangCampaign, and verifies that the imported
module resolves inside the bundled directory. It ignores ambient `PYTHONPATH`
for package selection and never modifies global Python configuration.

The adapter uses only the Python standard library. It supports macOS, Linux,
and Windows without a shell-specific runtime dependency. If no compatible
interpreter exists, the plugin reports that single requirement with concise
platform-appropriate guidance rather than attempting a privileged or networked
installation.

Plugin upgrades never delete or relocate learner data automatically. The
manifest, marketplace entry, adapter protocol, and profile format each carry an
explicit version so packaging and data compatibility can be tested separately.

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

The adapter creates directories with owner-only access and files with
owner-read/write access where the platform supports those permissions. Every
managed path is resolved beneath the selected data root, uses fixed filenames
or validated opaque identifiers, and is rejected if it traverses a symlink or
is not the expected regular-file/directory type. Model-generated content is
never interpreted as a filesystem path. Adapter input is bounded to 1 MiB and
schema validators bound individual fields and collections before persistence.

Profile and campaign changes use cross-process locks, not merely in-process
mutexes. POSIX uses `flock`; Windows uses an equivalent standard-library
exclusive file lock. Lock order is profile, learner lifecycle, then campaign,
and tests fail on an inversion. Writes use a same-directory temporary regular
file, flush and `fsync`, atomic replace, and best-effort parent-directory sync.
No reader observes partially written JSON.

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
model generation and one committed local state mutation. Deterministic reads,
validation, and one stale-revision reload do not count as generations or
mutations. A rejected write does not count as a committed mutation. Setup may
perform several pure validations before its single create; assessment uses one
generation to evaluate and respond, followed by one submission. The only extra
generation is the documented bounded correction of invalid generated content,
and it still ends in at most one committed mutation. It never creates separate
planner, teacher, and assessor calls for one interaction.

The no-hints boundary is explicit. Codex evaluates the learner against the
persisted mission rubric and submits criterion scores once. The engine derives
the authoritative numeric score and pass/partial/retry outcome. If Codex gives
material help after announcing the check, it must return to guided practice,
refresh content when required, and not submit that response as independent.

Disqualifying help includes supplying or translating the answer, correcting the
learner before scoring, completing a blank or sentence stem, presenting answer
choices, criterion-specific coaching, or giving an example that materially
solves the check. Repeating the prompt verbatim, resolving a transmission or
accessibility problem, and clarifying non-linguistic mechanics are allowed. On
disqualifying help, the adapter calls a public `return-to-practice` operation:
the engine records no evidence, revision-safely restores guided practice, and
sets the content-refresh flag. A new check is required later.

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

Exact resume relies on the schema-v5 mission session already persisted by the
engine: mission and attempt identifiers, mission kind, checkpoint, pending
difficulty adjustment, the validated content bundle (capability, scenario,
teaching objectives, essential language, guided prompts, assessment prompt, and
weighted rubric), latest outcome, selected next action, and content-refresh
flag. Attempt records preserve submitted evidence and results. The transcript
is intentionally not required. The selected next action is persisted after
assessment and is never silently recomputed after restart.

Campaign lifecycle has exactly three durable states: `active`, `paused`, and
`completed`. “Inactive” is learner-facing shorthand for `paused`, not a fourth
state. “Transitioned” is an event: the old active campaign becomes paused and a
new campaign becomes active in one lifecycle transaction. A profile has zero or
one active campaign. Pause clears the active pointer but preserves a resumable
campaign; completion is terminal and cannot be resumed.

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

A goal is materially new when it changes the target language, the real-world
outcome, the intended audience or domain enough to require different success
evidence, or a deadline enough to change the success condition. Rewording the
same outcome, requesting a supporting topic, or changing day-to-day practice
does not create a campaign. When that distinction is genuinely ambiguous,
Codex asks one brief question before mutating state. An existing campaign's
stored goal is immutable; transition provides the clear path forward without
discarding the paused campaign or its evidence.

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

Protocol version 1 uses these envelopes:

```json
{"protocol_version":1,"operation":"status","operation_id":"UUID","input":{}}
{"protocol_version":1,"operation_id":"UUID","success":true,"data":{}}
{"protocol_version":1,"operation_id":"UUID","success":false,"error":{"code":"INVALID_REQUEST","message":"...","retryable":false}}
```

Requests are one UTF-8 JSON object with no trailing content. Responses are
exactly one UTF-8 JSON object followed by one newline. Standard output contains
nothing else, including logs. Expected errors leave standard error empty;
redacted diagnostics for unexpected faults go only to standard error and never
include learner content. Exit codes are stable: `0` success, `2` request or
domain error, `3` unsupported environment, `4` persistence/recovery error, and
`70` unexpected internal fault. Invalid JSON receives the same error envelope
with a null operation ID when no valid ID can be recovered.

Error codes are a versioned closed set for protocol v1:
`INVALID_REQUEST`, `UNSUPPORTED_PROTOCOL`, `UNKNOWN_OPERATION`,
`UNSUPPORTED_ENVIRONMENT`, `NO_CAMPAIGN`, `AMBIGUOUS_CAMPAIGN`,
`INVALID_CONTENT`, `STALE_REVISION`, `IDEMPOTENCY_CONFLICT`, `STATE_CONFLICT`,
`CORRUPT_STATE`, `UNSUPPORTED_SCHEMA`, `UNSAFE_PATH`, `PERSISTENCE_FAILURE`, and
`INTERNAL_ERROR`. Each operation documents its allowed success payload and
error subset; adding a code requires a protocol-compatible specification
change.

Protocol v1 exposes this closed operation set. All identifier fields are
non-empty strings, all mutations include `expected_revision`, and all omitted
fields are rejected rather than silently defaulted:

| Operation | Required `input` beyond resolved profile | Success `data` |
| --- | --- | --- |
| `check-install` | none | environment, plugin version, profile readiness |
| `setup` | complete validated campaign, roadmap, plans, first content | campaign snapshot |
| `status` | optional campaign ID | exact campaign/mission snapshot or choices |
| `list-campaigns` | none | sanitized lifecycle summaries |
| `show-roadmap` | campaign ID | sanitized roadmap |
| `validate-content` | versioned complete content candidate | normalized content or issues |
| `transition` | new complete setup plus explicit evidence transfers | old/new campaign snapshots |
| `resume` | campaign ID, expected revision | campaign snapshot |
| `pause` | active campaign ID, expected revision | paused campaign snapshot |
| `complete` | campaign ID, expected revision | completed campaign snapshot |
| `start-mission` | campaign/mission IDs, expected revision, validated content | mission snapshot |
| `advance-mission` | campaign/mission IDs, attempt, checkpoint, expected revision | mission snapshot |
| `adjust-difficulty` | campaign/mission IDs, attempt, direction, expected revision | mission snapshot |
| `return-to-practice` | campaign/mission IDs, attempt, expected revision | mission snapshot |
| `submit-assessment` | campaign/mission IDs, attempt, rubric scores, independence declaration, modality, result statement, expected revision | assessed snapshot |
| `export` | explicit destination directory | archive path and manifest summary |
| `reset` | exact confirmation token | new profile plus backup/recovery paths |

The implementation ships JSON Schema files for the envelope and every
operation's input and success data. Those schemas are the machine-readable
authority for exact nested fields, bounds, enums, and `additionalProperties:
false`; the table defines the stable semantic surface. Adapter contract tests
load every schema and verify both accepted fixtures and unknown-field rejection.

The adapter does not parse, read, or write campaign `state.json` or learner
`index.json` directly. Its storage responsibilities are limited to the profile,
operation receipts, and orchestration of the specified backup/export/reset
services. Campaign and lifecycle changes remain behind public engine boundaries;
those services obtain consistent engine snapshots rather than interpreting
campaign JSON themselves.

The adapter's operation names and response objects do not mention Codex. A
future MCP or Claude adapter can call the same layer. Codex-specific prompt
instructions translate natural language into these operations and translate
structured outcomes into learner-facing prose.

Expected stale revisions cause one safe status reload. The adapter retries a
mutation only when the operation is defined as idempotent or when no mutation
was published. It never blindly repeats an assessment or setup request.

Every state-changing request requires a UUID `operation_id`. The adapter keeps
a bounded, cross-process-locked receipt ledger of the latest 256 completed
operations per profile, storing the operation name, canonical-input SHA-256,
and response. Reusing an ID and identical input returns the stored response;
reusing it with different input returns `IDEMPOTENCY_CONFLICT`. Eviction is
oldest-first and never removes an in-progress receipt.

The ledger supplements rather than pretends to replace transaction-level
idempotency. Setup and transition reuse a stable campaign ID and treat an
identical existing campaign as success; pause, activation, completion, and
`return-to-practice` are desired-state operations; assessment retains the
engine's mission/attempt duplicate contract. The receipt is committed under the
same applicable profile/lifecycle/campaign lock before success is returned.
Crash-injection tests cover the boundary between domain commit and receipt
publication. A caller that times out must retry the same request with the same
operation ID.

The generated-content validation operation accepts a versioned content bundle
and returns either the normalized bundle or ordered structured issues containing
stable code, JSON field path, and bounded correction message. It never returns
a partially accepted bundle. One correction resubmits the complete candidate;
a second failure terminates that setup/mission-generation attempt without a
state mutation.

Requests never contain authoritative creation, update, assessment, completion,
export, reset, or migration timestamps. The engine or adapter clock creates
them after validation while holding the applicable lock; tests inject a clock
through the existing keyword-only service seam. Learner-provided dates remain
goal data, not audit timestamps.

Compatibility is pinned to the public `langcampaign.cli.run_command` command
boundary; schema-v5 serializers in `langcampaign.storage`; lifecycle operations
in `langcampaign.learners`; and mission invariants in `langcampaign.runtime` and
`langcampaign.runtime_service`. The adapter may translate names and envelopes
but must preserve revision checking, engine-owned timestamps, create-only
setup, exact rubric coverage, derived scoring, persisted next actions, and the
learner-index single-active-campaign invariant. Refactors may move these types
only with contract tests proving the same behavior.

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

## Scoring contract

Each generated mission persists its own rubric before assessment. Every
criterion has a stable ID, description, integer weight, and integer score range
of 0–100; weights must total 100. Codex submits exactly one score per criterion
and one bounded overall result statement. The engine rejects missing, duplicate,
unknown, fractional, or out-of-range scores and computes the weighted result as
`(sum(weight * criterion_score) + 50) // 100`. Scores of 80–100 pass, 40–79 are
partial, and 0–39 retry. Codex never supplies the final percentage or outcome.

Mission attempt numbers are allocated by the engine. A duplicate submission for
the same campaign, mission, attempt, and canonical evidence returns the original
result; different evidence for that completed attempt conflicts. Review items,
next-action selection, and difficulty-adjustment consumption follow the existing
schema-v5 mission-runtime invariants and are persisted in the same assessment
transaction. The delivery layer must not recalculate or override them.

## Upgrade, export, and reset

The profile, operation ledger, and campaign state declare schema versions. The
engine continues to read its supported historical schemas and performs migration
only immediately before a requested write. Before the first write requiring a
newer profile or campaign schema, the adapter holds the profile lock and creates
an owner-only backup with a manifest and SHA-256 checksums. The last three
successful upgrade backups are retained.

Migration is staged in the same filesystem, fully validated and synced, then
published atomically. A failure leaves the original authoritative and moves any
partial staging data to a clearly named recovery area. If installed code cannot
read a newer stored schema, it returns `UNSUPPORTED_SCHEMA` without modifying
data; downgrade is never attempted automatically. Read-only export remains
available whenever the installed version can safely enumerate and copy the
files.

Export takes a consistent snapshot under the profile/lifecycle locks into a ZIP
archive containing only expected regular data files plus a manifest with export
format, creation time, plugin and schema versions, and per-file SHA-256 hashes.
It excludes locks, temporary files, backups, and recovery data; follows no
symlinks; accepts only an explicitly supplied destination directory; refuses to
overwrite; and publishes the archive by atomic rename from a private temporary
file. The learner receives the final path and a plain-language contents note.

Reset requires the exact explicit confirmation token `RESET LANGCAMPAIGN` in a
dedicated reset request. Under the exclusive profile lock it first creates and
verifies an export backup, then atomically moves the current profile and learner
data into a timestamped recovery directory and creates a fresh profile. It does
not recursively delete data. The response reports both the backup and recovery
paths; ordinary uninstall, setup, or conversational wording can never trigger
reset.

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
- Adapter versioned envelopes, typed errors, exit codes, standard-stream
  guarantees, payload bounds, and exactly-one-JSON behavior.
- Cross-process setup replay, duplicate assessment, pause-versus-assessment,
  export-versus-update, and reset-versus-update races on every supported OS.
- Crash injection before and after atomic publication, receipt publication, and
  schema migration, including recovery from partial staging data.
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

Evaluation fixtures and expected traces carry their own schema version and are
pinned to a repository commit. Deterministic tests use fixed inputs, timestamps,
random seeds, and temporary fresh profiles. A live run records the redacted
transcript, scenario version, plugin commit, model identifier, Codex version,
Python version, OS, start time, adapter trace, and measured latency. It never
reuses learner state between scenarios.

Release CI covers `ubuntu-latest`, `macos-latest`, and `windows-latest` with
Python 3.11; an additional job tests the newest Python version the project
declares supported. Filesystem/concurrency suites run with real subprocesses,
not mocked locks. The ten live scenarios run twice from fresh profiles. A
Critical failure is data loss/corruption, unsafe file access, fabricated saved
progress/evidence, or inability to complete the core workflow. An Important
failure is incorrect routing, checkpoint/lifecycle behavior, duplicate mutation,
hint-boundary enforcement, or repeated unnecessary model calls. A Minor failure
is a non-blocking wording or presentation defect. Release requires zero Critical
failures and zero unresolved reproducible Important failures; any one-off
Important failure must be investigated, dispositioned, and rerun.

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
