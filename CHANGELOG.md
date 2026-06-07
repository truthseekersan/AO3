# Changelog

## 2026-06-06

### Added
- Added fandom-wide custom styling context menu for character names and dialogue (Disable Name Color, Disable Name Glow, Give dialogue name look, Give POV dialogue name look) on the Tinted Dialogue icon.
- Added right-click character pill expansion directly in the Read tab's side panel.
- Added click-to-collapse anywhere in the right panel to close expanded character cards.
- Added per-character custom dialogue tint color configurations (dialog + color picker + toggle) next to the reader font style icon.

### Changed
- Integrated custom dialogue tint settings into paragraph color styling, using the custom color when enabled and falling back to the character's own profile color when disabled.

### Fixed
- Fixed timer `RuntimeError: The parent slot of the element has been deleted` during reader center container clear by deactivating pending scroll timers.
- Fixed right-panel render crash (`NameError: name 'character_tag_suggestion_js' is not defined`) by defining the tag suggestion helper locally inside `_render_character_expanded_panel`.

### Tests
- Added test coverage for disabling name color/glow, dialogue name look styling, and custom dialogue tinting overrides.

## 2026-06-05

### Added
- Added compact fandom creation through cached AO3 media-directory suggestions, including category cache controls.
- Added portable fandom backup/import plumbing and cleanup-gated fandom deletion flow.
- Added character reader font overrides, per-work POV timeline persistence, and restored Read scroll position memory.

### Changed
- Refined left-panel fandom search, fandom rows, local stats, and immediate fandom theme refresh behavior.
- Tightened Edit Fandom character-pill editing, canonical character tag search, cleanup controls, and live color refresh.
- Preserved Browse/filter/tab state per fandom and reduced visible Read-tab scroll jump during restore.

### Fixed
- Fixed Queue cleanup consistency, manual queue targeting, and cluster rename flow.
- Fixed stuck fandom style override toggles and character color picker reversion.
- Fixed AO3 fandom directory cache selection/search issues and added Cartoons & Comics & Graphic Novels as a cache category.

## 2026-06-04

### Changed
- Refined Read-tab POV handling so `No POV` is a work-level toggle that masks POV across chapters without mutating the per-work POV timeline.
- Kept Read paragraph rendering on the same tint pipeline for selected POV and `No POV`, preserving the off-white/grey alternating neutral tones.

### Fixed
- Fixed Read character highlighting so inline character-name spans no longer create nested paragraphs or split AO3 paragraphs visually.
- Fixed `No POV` toggle behavior so turning it off restores the chapter/work POV timeline state.

### Tests
- Added regression coverage for work-level `No POV` persistence, POV timeline preservation, neutral paragraph tinting, and AO3 paragraph preservation during character highlighting.

## 2026-06-03

### Added
- Added named evaluation queues backed by work clusters, with nested schema pills for Queue and Evaluated navigation.
- Added the Evaluated workspace tab for completed and partially completed evaluation batches.
- Added Queue batch evaluation runner scaffolding for sequential LM Studio-powered evaluation, reader-text sampling, API settings, and queue evaluation configuration.
- Added Queue and Evaluated cleanup modes for cluster-level and schema-slot cleanup.
- Added AO3 metadata filters to Works and standardized local metadata sorting across Browse, Works, Queue, and Evaluated.
- Added Read-tab character POV tint pills using character profiles from Edit Fandom. Selected character tint uses ScriptStudio's two-tone alternating paragraph method while preserving existing inline character-name coloring.

### Changed
- Reframed Browse "save page" behavior as saving a named evaluation queue.
- Improved Browse/Queue/Evaluated tab responsiveness by using cached render models and lazy inline panel hydration.
- Reduced Browse right-panel clutter by consolidating duplicate apply controls and sharing one refresh-style apply icon pattern.
- Standardized AO3 metadata sort pill order: Updated, Word Count, Bookmarks, Kudos, Hits, Comments, Creator, Title, Posted.
- Corrected local AO3 date sorting so display dates such as `08 Jan 2026` sort chronologically for Updated and Posted.
- Refined Queue and Evaluated right-panel pills, schema pills, cleanup header behavior, hover/selection states, and spacing.
- Kept queued and evaluated works protected from smart purge unless explicitly removed through queue/evaluated cleanup flows.

### Fixed
- Fixed Queue/Evaluated AO3 metadata sorting so local sort and direction controls actually affect selected cluster contents.
- Fixed cleanup trash disarming in Queue and Evaluated right panels.
- Fixed Browse accordion scroll and hydration behavior regressions from lazy panel rendering.
- Fixed visual inconsistencies in Queue/Evaluated cluster pill outlines, hover states, selected states, and filter apply buttons.

### Tests
- Expanded unit and integration coverage for queue/evaluated cluster cleanup, Browse URL sort direction, local metadata filtering, chronological AO3 date sorting, lazy render models, and Read character POV tint behavior.
