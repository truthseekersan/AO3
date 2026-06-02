# AO3 Studio

AO3 Studio is a local-first reading, browsing, and evaluation studio for Archive of Our Own.

The short version: it is "IMDb for AO3 fanfics, but better" - a private desktop-style app that caches AO3 metadata, lets you design your own evaluation schemas per fandom, and uses a local AI API to score fic against the criteria that actually matter to you.

Instead of treating popularity as taste, AO3 Studio builds a durable local memory of works, tags, reader state, queues, evaluations, notes, and fandom-specific preferences. It is designed for people who want to choose what to read with more signal than hits, kudos, bookmarks, or vibes from a summary alone.

AO3 Studio is not affiliated with AO3 or the Organization for Transformative Works.

## What It Does

- Browse AO3 by fandom or search URL and cache result pages locally.
- Keep a private SQLite library of works, tags, publication dates, reader state, blocks, favorites, rarity, and evaluations.
- Build custom evaluation schemas with weighted dimensions, groups, prompts, schema colors, and active/default schema selection.
- Save Browse pages as named evaluation queues.
- Evaluate queue clusters one work at a time through LM Studio, using strict JSON output that AO3 Studio can parse and persist.
- Sample downloaded reader text intelligently instead of forcing whole-work prompts or first-chapter-only judgments.
- Compare pending queue work and completed evaluated work by cluster and schema.
- Keep "Works" focused on works the user is reading or intentionally saving, not every fic that has merely been evaluated.
- Protect queued, evaluated, collected, blocked, favorited, and reader-state works from smart cache cleanup.

## Core Idea

AO3 Studio separates four things that are often mashed together:

- Browse cache: AO3 pages and metadata you have looked at.
- Works: fic you are actively keeping, reading, or organizing.
- Queue: named clusters of works waiting to be evaluated under a specific schema.
- Evaluated: completed results for a cluster/schema pair.

That means a fic can be evaluated without being added to Works, and the same saved cluster can later be evaluated under a different schema. Redundant reruns of the same schema are blocked until that schema result is explicitly cleaned up.

## Local AI Evaluation

AO3 Studio currently targets LM Studio's OpenAI-compatible local API for text evaluation and LM Studio's native model-management endpoints for model listing, loading, and unloading.

The queue runner is deliberately sequential:

1. Mark the next queue item as running.
2. Ensure reader text is cached.
3. Build a sample from the configured chapter/word-count rules.
4. Send one strict JSON prompt to LM Studio.
5. Validate and persist scores, notes, evidence, and sample provenance.
6. Mark the item complete or failed.
7. Continue to the next work.

Per-work extraction or validation failures are recorded and the runner continues. Global LM Studio misconfiguration or connectivity failures stop the batch so the remaining queue is untouched.

The JSON contract is app-owned, not schema-authored. Schemas define the dimensions and evaluator guidance; AO3 Studio always requires structured output with:

- `scores`
- `notes_markdown`
- `evidence`
- optional `subscores`

Scores are keyed by the active schema dimension keys.

## Sampling

Queue evaluation uses downloaded AO3 reader HTML without adding the work to Works or marking it as read.

The global queue evaluation configuration controls:

- whether work metadata is included
- whether tags are included
- starting chapter
- chapter window
- target sampled word count
- maximum sampled word count
- empty-chapter skip-forward behavior

Short works can be evaluated as whole works. Long works are sampled according to the configured chapter and word limits, with provenance saved in the evaluation's chapter scope instead of storing the full prompt sample in SQLite.

## UI Shape

AO3 Studio is built as a NiceGUI app with a desktop-oriented three-panel interface:

- Left panel: fandom context, schema/settings access, queue configuration.
- Center panel: Browse, Works, Read, Queue, Evaluated, Analytics, and optional Shared/Admin tabs.
- Right panel: context-specific filters, sort controls, cluster navigation, reader controls, and cleanup modes.

Important tabs:

- Browse: AO3 browse/search results, local filters, tag actions, work cards, and save-page-as-queue.
- Works: user-kept reading library.
- Read: cached reader view with chapter navigation and local style settings.
- Queue: named work clusters and nested schema slots for pending evaluation.
- Evaluated: completed cluster/schema results, schema-slot cleanup, and requeue-under-schema flow.
- Analytics: local counts and evaluation coverage.

## Persistence Model

AO3 Studio stores local state in SQLite under `config/ao3_studio.sqlite` by default. That local database is intentionally ignored by git.

The database includes:

- works and tags
- browse snapshots
- local evaluations
- evaluation batches
- evaluation queue rows
- work sets
- reader assets and chapters
- reading state
- fandom profiles
- schema definitions
- blocks, favorites, tag colors, rarity, and style overrides
- local settings and API configuration

The repository is source code only. Personal databases, browser profiles, cookies, logs, screenshots, local configs, and token-like files are ignored.

## Privacy Boundary

AO3 Studio is local-first by design.

- Your AO3 cookies are not meant to be committed.
- Your SQLite database is not meant to be committed.
- Your browser profile/cache is not meant to be committed.
- Your model configuration and local settings are stored locally.
- Shared Mode exists as a future remote overlay path, but Local Mode remains the source of truth.

If you fork or publish your own copy, check `git status --ignored` before committing anything private.

## Requirements

- Windows is the primary development target.
- Python 3.13 or newer.
- LM Studio for local AI evaluation, optional unless you want queue evaluation.
- AO3 access in your normal browser/session for pages that require login, age confirmation, or AO3's anti-bot checks.

Python dependencies are listed in `requirements.txt` and `pyproject.toml`.

## Quick Start

Windows:

```powershell
.\setup_env.bat
.\run_studio.bat
```

Direct Python:

```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Native desktop mode:

```powershell
python main.py --native
```

By default AO3 Studio runs at:

```text
http://127.0.0.1:8093/
```

## LM Studio Setup

1. Start LM Studio.
2. Enable the local server.
3. Open AO3 Studio Settings.
4. Go to the API tab.
5. Refresh available models.
6. Select the model you want AO3 Studio to use.
7. Configure timeout, temperature, and optional context length.

AO3 Studio normalizes older `http://localhost:1234/v1` style settings and uses LM Studio's native `http://localhost:1234/api/v1` model endpoints for load/unload support.

## Testing

Run the full suite:

```powershell
venv\Scripts\python.exe -m pytest -q
```

Run focused UI/source and repository tests:

```powershell
venv\Scripts\python.exe -m pytest tests\unit\test_ui_style_helpers.py tests\integration\test_sqlite_repositories.py -q
```

## Repository Hygiene

The `.gitignore` intentionally excludes:

- `config/`
- `logs/`
- SQLite databases and journals
- browser profiles and cookies
- virtual environments
- Python caches
- smoke screenshots and local log output
- token-like files
- local shortcuts and OS/editor noise

This is important: AO3 Studio is useful precisely because it remembers personal reading and taste data. That data belongs on your machine, not in the repository.

## Project Status

AO3 Studio is an active local-first application. It has a working Browse/Works/Read/Queue/Evaluated flow, local schema studio, SQLite persistence, LM Studio queue runner, and regression coverage around the core repositories, UI source contracts, parser behavior, and model provider payloads.

Shared/remote overlay pieces are scaffolded but not the source of truth.
