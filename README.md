<div align="center">
  <h1>🌍 LangCampaign</h1>
  <p><strong>Train for what you actually want to do with a language.</strong></p>
</div>

LangCampaign is a Codex language-learning plugin built around practical goals. It creates focused missions, teaches only what you need next, checks what you can do without hints, records evidence-backed progress, and resumes from the exact checkpoint later.

Travel, interviews, and presentations are valid goals—but so are texting friends, talking with family, reading social posts, following creators, playing games, or enjoying books and shows.

## Install

LangCampaign requires Codex and Python 3.11 or newer.

```bash
codex plugin marketplace add qasim-a/langcampaign
codex plugin add langcampaign@langcampaign
```

Start a new Codex conversation after installation. On first use, Codex asks for one-time permission to create LangCampaign’s personal data directory so the same campaigns remain available across repositories.

To update later:

```bash
codex plugin marketplace upgrade langcampaign
```

## Start learning

Invoke `$langcampaign` or make a clear campaign request:

```text
Help me learn Spanish so I can talk comfortably with my partner's family.
I know basic Spanish and have about two hours a week.
```

```text
I mainly want to understand Portuguese tweets. I am a beginner and can
practice for 90 minutes a week.
```

Include the language, practical goal, realistic weekly time, what you already know, and a deadline if one matters. If that is enough, LangCampaign starts without further setup questions. You never need to choose curriculum, coaching, or presentation settings.

## The learning flow

Each mission stays compact:

```text
🎯 Practical capability and scenario
→ focused teaching
→ guided practice
→ announced no-hints check
→ evidence-backed result
→ progress and next action
```

Say `too easy` for a harder version or `too hard` for prerequisite support. Partial performance receives credit without being inflated into a pass.

A typical result looks like:

```text
🟡 Partial — 68%

You communicated the main point. The time expression was ambiguous; use
“a las ocho” for a precise time.

Progress  █████░░░░░  50%
Next: one focused retry.
```

## Continue, pause, and change goals

In any new conversation, invoke `$langcampaign` and say `continue`. LangCampaign loads the active language, mission, persisted content, checkpoint, progress, and next action without asking you to restate them.

You can also ask naturally to:

- Show compact progress or the hidden roadmap summary.
- Pause the active campaign.
- List and resume a paused campaign.
- Mark a campaign complete.
- Start a materially different goal.

An existing campaign’s goal does not change in place. A new language or substantially different real-world outcome creates a new campaign and preserves the old one as paused, so you can return without starting over.

## Data and privacy

LangCampaign stores one automatic local profile, compact generated mission content, checkpoints, assessment evidence, and progress. It does not add accounts, telemetry, hosted storage, or third-party network calls. Full conversations and model reasoning are not stored by LangCampaign.

Default data locations:

- macOS: `~/Library/Application Support/LangCampaign`
- Linux: `$XDG_DATA_HOME/langcampaign` or `~/.local/share/langcampaign`
- Windows: `%LOCALAPPDATA%\LangCampaign`

Ask `$langcampaign` to export your data and provide an existing destination directory. Export never overwrites an existing archive. Reset is recoverable, creates a backup first, and requires the exact confirmation `RESET LANGCAMPAIGN`. Uninstalling the plugin does not delete learning history.

## Troubleshooting

- **Python requirement:** install Python 3.11 or newer, then retry.
- **Storage permission:** approve the one-time personal-data access request; LangCampaign never falls back to the current repository.
- **Progress not saved:** retry the same interaction. Mutation IDs prevent duplicate setup or assessment.
- **Corrupt or newer data:** LangCampaign stops without rewriting it. Export or recovery information remains available when safely readable.

## Current scope

The MVP supports Codex with local persistence and text-based learning. ChatGPT and Claude adapters, cross-device sync, accounts, voice/pronunciation scoring, rich dashboards, and hosted services remain future work. LangCampaign is not an accredited language-testing body.
