# Dialogue Attribution Mode (DAM) — Implementation Plan
### AO3 Studio · Read Tab Feature

---

## Overview

Dialogue Attribution Mode (DAM) is a new Read tab overlay mode that colorizes individual quoted dialogue runs by the character who speaks them. Non-dialogue text stays colorless and identical to the base reading view. Toggling DAM on or off is purely cosmetic — no paragraphs restructure, no scroll position changes, no DOM layout shifts. The feature is built on top of the existing character color system and the LM Studio local API pipeline already used for queue evaluation.

This scaffold is also designed as the foundation for a future **Dialogue Audio Mode (DAudio)** layer, in which each attributed dialogue span is backed by an emotion-tagged TTS-generated `.wav` file, playable by clicking the span directly in the reader. All DOM addressability, file naming, click dispatch, and status tracking decisions below are made with that future layer in mind.

---

## Scope Boundaries

**In scope:**
- LLM-powered dialogue attribution per chapter using LM Studio
- Cosmetic span injection into already-rendered paragraph elements
- Attribution caching in SQLite per chapter
- Toggle control in the Read tab right panel
- Auto-enable No POV mode when DAM activates (if not already set)
- Character legend pill row recontextualized for DAM
- Audio scaffold: `data-*` attributes, audio cache directory structure, `dam_audio_status` column, container-level click dispatch stub

**Out of scope (post-MVP / DAudio layer):**
- Emotion tagging chain
- TTS API call and `.wav` generation
- `<audio>` playback element
- Inner-thought / italics attribution
- Manual attribution correction UI
- Multi-model attribution diffing
- Real-time streaming attribution

---

## Architecture

### 1. Data Model

Add three items to SQLite:

**New table: `dam_attributions`**

```sql
CREATE TABLE IF NOT EXISTS dam_attributions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id      TEXT NOT NULL,
    chapter_idx  INTEGER NOT NULL,
    pid          INTEGER NOT NULL,
    dam_seq      INTEGER NOT NULL,  -- sequential index across all spans in the chapter
    quote_text   TEXT NOT NULL,
    speaker_id   TEXT,              -- NULL = unresolved
    confidence   TEXT,              -- 'high' | 'medium' | 'low' | 'unresolved'
    model_id     TEXT,
    generated_at TEXT,
    UNIQUE(work_id, chapter_idx, pid, dam_seq)
);
```

`dam_seq` is a chapter-scoped sequential integer assigned at injection time (0, 1, 2...). It disambiguates multiple quoted lines within the same paragraph and forms part of the audio filename key.

**New columns on chapter/reader state row:**

```sql
ALTER TABLE reader_chapters ADD COLUMN dam_status TEXT DEFAULT 'none';
-- values: 'none' | 'pending' | 'complete' | 'stale'

ALTER TABLE reader_chapters ADD COLUMN dam_audio_status TEXT DEFAULT 'none';
-- values: 'none' | 'pending' | 'complete' | 'stale'
```

`dam_status` and `dam_audio_status` have independent lifecycles. Attributions can be complete while audio is still pending, and audio can go stale (e.g. a new voice clone is uploaded) while attributions remain valid. They are independently queryable and independently re-runnable.

`dam_status` is set to `stale` when the fandom's character roster changes after attributions were generated. `dam_audio_status` is set to `stale` when voice clone assets for any speaking character in the chapter are updated.

---

### 2. Audio Cache Directory Structure

All generated `.wav` files are stored locally alongside existing reader assets:

```
config/
  ao3studio.sqlite
  audio_cache/
    {work_id}/
      ch{chapter_idx}/
        {pid}_{dam_seq}.wav
```

**Naming convention:** `{pid}_{dam_seq}.wav` inside `config/audio_cache/{work_id}/ch{chapter_idx}/`.

The `work_id` folder and `ch{chapter_idx}` subfolder structure serves two purposes: manual inspection is trivial (open the folder, see all of one chapter's audio), and chapter-level cache invalidation is a single `rmdir` rather than a filtered file delete. When a chapter's attributions go stale and the user triggers a re-run, wipe `ch{chapter_idx}/` and regenerate.

**Path resolver (single function, no database lookup):**

```python
AUDIO_CACHE_DIR = Path("config/audio_cache")

def resolve_audio_path(work_id: str, chapter_idx: int, pid: int, dam_seq: int) -> Path:
    return AUDIO_CACHE_DIR / work_id / f"ch{chapter_idx}" / f"{pid}_{dam_seq}.wav"
```

Add `config/audio_cache/` to `.gitignore` alongside the existing database and browser profile exclusions.

---

### 3. Prompt Contract

#### Request payload sent to LM Studio (`dam_request`)

```json
{
  "mode": "dialogue_attribution",
  "fandom": "...",
  "characters": [
    { "id": "char_001", "name": "Alex Chen", "aliases": ["Alex", "she"] },
    { "id": "char_002", "name": "Max Caulfield", "aliases": ["Max", "Maxine"] }
  ],
  "chapter": {
    "work_id": "...",
    "chapter_index": 3,
    "paragraphs": [
      { "pid": 0, "text": "\"I never asked for this,\" she said quietly." },
      { "pid": 1, "text": "Max looked away. \"Neither did I.\"" }
    ]
  }
}
```

Only paragraphs containing at least one quoted string are included. Purely narrative paragraphs are excluded from the payload to minimize token usage.

#### Expected LLM response (`dam_response`)

```json
{
  "attributions": [
    {
      "pid": 0,
      "dialogues": [
        { "text": "I never asked for this,", "speaker_id": "char_001", "confidence": "high" }
      ]
    },
    {
      "pid": 1,
      "dialogues": [
        { "text": "Neither did I.", "speaker_id": "char_002", "confidence": "high" }
      ]
    }
  ],
  "unresolved": []
}
```

`unresolved` contains `pid` values where dialogue was detected but no speaker could be determined. These receive no span injection and render as default text color.

`dam_seq` is assigned by the injector after the LLM response is received — it is not part of the LLM contract. The injector walks attributions in document order and assigns a monotonically increasing integer across all spans in the chapter.

#### System prompt for LLM

```
You are a dialogue attribution engine for fanfiction. Given a list of characters with aliases
and a list of numbered paragraphs, identify every quoted dialogue string and attribute it to
a speaker.

Rules:
- Only attribute text inside quotation marks or em-dash dialogue formatting.
- Use attribution tags ("she said", "Max replied", "he whispered") as your primary signal.
- Use conversational context and alias matching as secondary signals.
- If you cannot attribute a quote with at least medium confidence, add its pid to "unresolved"
  and omit it from attributions.
- Never fabricate a speaker. Omit rather than guess.
- Return ONLY valid JSON matching the dam_response schema. No prose, no markdown.
```

---

### 4. Backend Service: `DamService`

Create `services/dam_service.py`:

```python
class DamService:

    def build_request_payload(self, work_id, chapter_idx, characters, paragraphs) -> dict:
        """
        Filter paragraphs to those containing quoted text.
        Build and return the dam_request dict.
        """

    def call_lm_studio(self, payload: dict) -> dict:
        """
        POST to the existing LM Studio local API endpoint.
        Enforce strict JSON output mode.
        Validate response against dam_response schema.
        Raise DamParseError on invalid response.
        """

    def persist_attributions(self, work_id, chapter_idx, response: dict, model_id: str):
        """
        Assign dam_seq to each dialogue across all attributions in document order.
        Upsert dam_attributions rows including dam_seq.
        Set dam_status = 'complete' on the chapter row.
        """

    def get_attributions(self, work_id, chapter_idx) -> list[dict]:
        """
        Return all persisted attributions for a chapter, ordered by (pid, dam_seq).
        Returns empty list if dam_status is 'none'.
        """

    def mark_stale(self, work_id):
        """
        Set dam_status = 'stale' for all chapters of a work
        when the fandom character roster changes.
        """

    def mark_audio_stale(self, work_id):
        """
        Set dam_audio_status = 'stale' for all chapters of a work
        when voice clone assets for any character in the fandom are updated.
        """

    def clear_attributions(self, work_id, chapter_idx):
        """
        Delete all dam_attributions rows for a chapter.
        Reset dam_status = 'none' and dam_audio_status = 'none'.
        Wipe config/audio_cache/{work_id}/ch{chapter_idx}/ directory.
        """
```

Reuse the existing LM Studio API client and settings already wired for queue evaluation. No new API configuration needed.

---

### 5. Frontend: Read Tab Changes

#### Right-panel control additions

Add a **Dialogue Mode** toggle pill to the reader controls section, grouped near the existing POV controls. The pill reflects `dam_status`:

| State | Appearance | Behavior |
|---|---|---|
| `off` | Inactive pill | DAM disabled, no spans active |
| `on — no data` | Active pill + "Analyze" button | Triggers LM Studio run |
| `on — complete` | Active pill, colored dialogue visible | Toggle off removes color |
| `on — stale` | Active pill + stale indicator + "Re-run" button | Prompts re-run |
| `on — pending` | Active pill + spinner | LM Studio call in progress |

When DAM is toggled on for the first time on a chapter, if `dam_status` is `'none'`, surface an **"Analyze Chapter"** button. Do not auto-run the LLM without user intent.

When DAM is activated, if No POV is not already enabled at the work level, automatically enable it. Log this as an auto-action so it can be reversed cleanly if DAM is disabled.

#### Character legend

Reuse the existing POV tint pill row. When DAM is active, relabel it as speaking characters for the current chapter based on which `speaker_id` values appear in the chapter's attributions. Characters with no attributed dialogue in this chapter are hidden from the legend.

#### Container-level click dispatch (audio scaffold)

Install a **single delegated click listener** on the chapter container element at DAM scaffold time. This listener is dormant until the DAudio layer activates it. Event delegation on the container — not individual listeners per span — is required because a long chapter can have hundreds of `.dam` spans.

```python
# Installed during DAM scaffold on the chapter container element:
chapter_container.on('click', handle_chapter_click)

def handle_chapter_click(event):
    """Delegated click handler. Routes .dam span clicks to audio dispatch stub."""
    target = event.args.get('target', {})
    if 'dam' not in target.get('classList', []):
        return
    dataset = target.get('dataset', {})
    work_id     = dataset.get('workId')
    chapter_idx = dataset.get('chapterIdx')
    pid         = dataset.get('pid')
    dam_seq     = dataset.get('damSeq')
    _on_dialogue_click(work_id, chapter_idx, pid, dam_seq)

def _on_dialogue_click(work_id: str, chapter_idx: str, pid: str, dam_seq: str):
    """Audio layer seam. DAudio implementation slots in here — do not remove."""
    pass
```

The `_on_dialogue_click` stub is the seam point. The DAudio layer fills it in without touching anything else in the Read tab.

---

### 6. Span Injector: `DamInjector`

Create `ui/dam_injector.py` (or equivalent in the NiceGUI frontend layer):

```python
class DamInjector:

    def inject(self, chapter_el, attributions: list[dict], char_colors: dict, work_id: str, chapter_idx: int):
        """
        Walk paragraph elements by pid.
        For each attribution (ordered by pid, dam_seq), call _wrap_quote.
        Only inject spans for confidence == 'high' or 'medium'.
        Skip 'low' and 'unresolved' entirely.
        Passes work_id and chapter_idx through for data attribute population.
        """

    def _wrap_quote(self, paragraph_el, quote_text: str, color: str,
                    work_id: str, chapter_idx: int, pid: int,
                    dam_seq: int, speaker_id: str):
        """
        Walk text nodes within paragraph_el only.
        Find quote_text as a substring of a text node.
        Split the text node at match boundaries.
        Insert the following span for the match:

            <span
              class="dam"
              style="--dam-c: {color};"
              data-work-id="{work_id}"
              data-chapter-idx="{chapter_idx}"
              data-pid="{pid}"
              data-dam-seq="{dam_seq}"
              data-speaker-id="{speaker_id}"
            >

        Never touch element nodes. Never replace innerHTML wholesale.
        Handles multiple occurrences within the same paragraph.
        """

    def clear(self, chapter_el):
        """
        Remove all .dam spans from chapter_el.
        Merge adjacent text nodes back (normalize).
        Paragraph structure is restored exactly as before injection.
        """
```

**Critical constraint:** `_wrap_quote` operates on text nodes only, never via `innerHTML` string replacement. This prevents breaking AO3's existing span markup, HTML entities, or any inline formatting already present in the reader HTML.

**Span data attribute contract:**

| Attribute | Value | Purpose |
|---|---|---|
| `data-work-id` | work identifier | Audio path resolution |
| `data-chapter-idx` | chapter index integer | Audio path resolution |
| `data-pid` | paragraph index integer | Audio path resolution |
| `data-dam-seq` | chapter-scoped sequence integer | Audio path disambiguation; sequential playback |
| `data-speaker-id` | character identifier | Audio status display; future per-character mute |

These five attributes are populated by the injector at injection time. DAM does not use them for any visual logic — they exist solely to make the DOM self-describing for the DAudio layer without any database lookup at click time.

#### CSS (add to reader stylesheet)

```css
/* DAM spans — cosmetic only, zero layout impact */
.dam {
  color: var(--dam-c);
}

/* When DAM container class is removed, spans are invisible — color inherits from prose */
.read-chapter-container:not(.dam-active) .dam {
  color: inherit;
}

/* Audio scaffold: clickable cursor when DAudio is active (class added by DAudio layer) */
.dam-audio-active .dam[data-work-id] {
  cursor: pointer;
}
```

The `dam-active` class lives on the chapter container. Adding or removing it is the entire DAM toggle mechanism. The spans remain in the DOM permanently after first injection. The `dam-audio-active` class is a placeholder for the DAudio layer — DAM does not set it.

---

### 7. Stale Detection Hook

In the existing **Edit Fandom** character save path, after any character create/update/delete:

```python
# After character roster changes are committed:
dam_service.mark_stale(work_id)        # attributions may reference stale character IDs
dam_service.mark_audio_stale(work_id)  # voice clone assignments may have changed
```

This ensures that if characters are renamed, recolored, or removed after DAM has run, the Read tab surfaces stale indicators for both attribution and audio status independently.

---

## File Checklist

| File | Action |
|---|---|
| `services/dam_service.py` | **Create** — full service class including `mark_audio_stale` and audio cache wipe in `clear_attributions` |
| `migrations/add_dam_tables.sql` | **Create** — `dam_attributions` table (with `dam_seq`) + `dam_status` column + `dam_audio_status` column |
| `ui/dam_injector.py` | **Create** — span injector with full `data-*` attribute population |
| `ui/read_tab.py` | **Modify** — add DAM toggle pill, Analyze button, stale indicator, legend relabeling, No POV auto-enable, container click dispatch stub |
| `services/lm_studio_client.py` | **Modify** — add DAM request builder and response validator (or thin wrapper) |
| `repositories/dam_repository.py` | **Create** — SQLite CRUD for `dam_attributions`, `dam_status`, and `dam_audio_status` |
| `ui/reader_styles.css` | **Modify** — add `.dam`, container inactive rule, and `dam-audio-active` cursor placeholder |
| `services/fandom_service.py` | **Modify** — call `mark_stale` and `mark_audio_stale` after character roster save |
| `tests/test_dam_service.py` | **Create** — unit tests for payload builder, response validator, persistence, `dam_seq` assignment |
| `tests/test_dam_injector.py` | **Create** — unit tests for span injection, `data-*` attribute population, multi-quote paragraphs, and clear/normalize |
| `config/audio_cache/` | **Create directory** — add to `.gitignore` alongside database and browser profile exclusions |
| `.gitignore` | **Modify** — add `config/audio_cache/` entry |

---

## Implementation Order

1. **Migration** — add `dam_attributions` table (with `dam_seq`), `dam_status` column, and `dam_audio_status` column. Verify with existing schema tests.
2. **Repository** — `DamRepository` CRUD. Unit test all paths including upsert conflict behavior and `dam_seq` ordering.
3. **Service** — `DamService`. Unit test payload builder and response validator with fixture JSON. Verify `dam_seq` is assigned in document order. Integration test against LM Studio using an existing downloaded chapter.
4. **Injector** — `DamInjector`. Unit test text node walking, multi-quote paragraphs, full `data-*` attribute population, and clear/normalize. Test against AO3 HTML samples that contain existing inline spans to confirm no nesting breakage. Verify `data-dam-seq` matches persisted `dam_seq` values.
5. **Read tab UI** — wire toggle pill, Analyze button, spinner, stale indicator, legend relabeling, No POV auto-enable. Install container click dispatch stub with `_on_dialogue_click` seam. Use `dam_status` to drive all button states.
6. **Stale hook** — add `mark_stale` and `mark_audio_stale` calls in fandom character save path. Test that editing a character updates both status columns on affected works.
7. **CSS** — add DAM span rules and `dam-audio-active` cursor placeholder to reader stylesheet. Verify toggle on/off causes no layout reflow.
8. **Audio cache directory** — create `config/audio_cache/`, add to `.gitignore`. Verify `resolve_audio_path()` constructs correct paths for edge cases (single quote per paragraph, multiple quotes per paragraph).
9. **Regression** — verify existing character-name inline highlighting, POV tinting, No POV toggle, and scroll position restore are unaffected.

---

## Key Constraints Summary

- Span injection touches **text nodes only** — never `innerHTML` wholesale replacement
- `.dam` spans carry `color: var(--dam-c)` plus **five `data-*` attributes** — no display, padding, background, or font changes
- Toggle is a **class add/remove on the container** — spans stay in DOM, no re-render
- LLM runs **on user intent only** — no auto-run on chapter load
- Unresolved and low-confidence dialogue receives **no span** — renders as default prose color
- No POV auto-enable is **reversible** — tracked so disabling DAM can restore prior No POV state
- Attributions are **chapter-scoped and cached** — LLM does not re-run on chapter navigation unless `dam_status` is `stale` and user triggers re-run
- `dam_status` and `dam_audio_status` are **independent columns** — stale audio does not require re-running attribution
- Click dispatch is **delegated to the container** — one listener, not one per span
- `_on_dialogue_click` is a **named stub** — the DAudio layer fills it in without touching the rest of the Read tab
- Audio files follow the **`{pid}_{dam_seq}.wav`** convention inside `config/audio_cache/{work_id}/ch{chapter_idx}/` — chapter-level invalidation is a single directory wipe
