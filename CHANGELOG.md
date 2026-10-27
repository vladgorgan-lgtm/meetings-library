# Changelog

All notable changes to the Meetings Library kit. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the kit
`VERSION` file (semantic versioning). For a plain language view of the same
history, see [docs/PROGRESS.md](docs/PROGRESS.md).

This repository holds code, documentation and a fictional demo library only.
Real meeting notes and everything generated from them stay on the local disk
(see `.gitignore`).

History before the repository existed was reconstructed from file dates and run
logs, not from commits, so versions 1.0.0 and 1.1.0 have no tag of their own.

## [Unreleased]

### Planned
- Middle layer rules for decisions (what counts as a decision, what makes one "key").
- Engine-side wiring for Gemini notes beyond the sync runbook, and a cost estimate for it.
- Contributor guide.

## [1.3.0] - 2026-10-27

### Added
- `skill/INSTRUCTIONS.md`: the full sync skill runbook now lives in this repository, matched to
  the code. The skill becomes a thin stub that follows the latest release, so every release
  updates every installation.
- Update check at the start of each run (one `git ls-remote`, free). Patch and minor releases
  apply automatically; a new major version asks first. Instructions are cached in the library
  (`ops/skill-cache/`) so a failed fetch falls back to the last good copy.
- `templates/config.example.json`: default config for new installs, including the Gemini and
  local-files settings.
- `docs/releasing.md`: how to cut a release and the version rules.

### Needs attention
- The repository is public from this release. The leak scan still gates every push.
- Installed libraries add any new config keys on upgrade and never change existing values.

## [1.2.2] - 2026-10-26

### Added
- Locked privacy rules: the scan now fails if `.gitignore` loses a required private-data
  rule, or if a guarded file (`.gitignore`, the scan tool and its two lists) changed since
  the owner approved it (`tools/guard.sha256`, `publishable.py approve`).
- `CLAUDE.md`: the privacy, publishing and style rules in the folder itself, so they travel
  with the project.

## [1.2.1] - 2026-10-26

### Added
- `tools/publishable.py`: lists the files that may be published (everything `.gitignore`
  does not exclude) and scans exactly those files for real names, e-mail addresses and
  local paths before any push. `tools/scan-allow.txt` holds harmless example phrases.
- `docs/publishing.md`: what "push to git" does, the rules it follows, and the checklist
  for a new session.

### Changed
- The library folder on disk now matches the repository (same `.gitignore`, `sample/`,
  `templates/`, docs and tools), so publishing is a copy of the allowed files, not a rewrite.
- Private name checks moved from `engine/review.py` into the library's own
  `ops/curated-checks.json`; the UI placeholder text uses an invented name.

## [1.2.0] - 2026-10-26

### Added
- Gemini "Notes by Gemini" as a second source, merged per meeting with Granola as the
  base (`coverage: both` or `gemini-only`), with a ledger, a lookback window and a
  Drive safety net (`gemini.*` in the library config).
- Local settings page and local server (`engine/serve.py`, `Start Meeting Library.command`):
  monthly cost cap, connector toggles, manual add queue, sensitive overrides, and a
  "Run fetch now" button that asks Claude to run the sync (with a fallback page).
- Needs review: checks for unclear names and terms, your answers saved as rules
  (`engine/review.py`), applied at build time without editing notes.
- Insights layer plumbing (`engine/insights.py`): which notes need analysis, merging of
  extra decisions with Granola's own, which are never trimmed; decision groups.
- Fictional demo library in `sample/`, plus `templates/` with example config, rates and
  review checks.
- Repository files: `.gitignore` for private data, this changelog, `docs/PROGRESS.md`.

### Changed
- `engine/review.py` reads library-specific checks from `ops/curated-checks.json`
  instead of embedding them in code.
- Settings page placeholder text no longer contains a real name.
- `VERSION` is now 1.2.0 (it was 1.0.0).

### Notes
- The sync runbook is shipped as `docs/sync-extension.example.md` with placeholders; the
  real one stays local.
- Duplicate copies of `budget_check.py` and `cost_report.py` also exist under `ops/`
  locally; only the `engine/` versions are tracked here.

## [1.1.0] - 2026-10-23

### Added
- Insights layer scaffold: `rules/decisions.md` (placeholder) and `rules/settings.json`.
- README section on the insights layer and decision groups.

### Changed
- Viewer improvements (exact changes not recoverable from file dates; to be confirmed).

## [1.0.0] - 2026-10-21

### Added
- First complete kit: static viewer (`index.html`, `ui/`), data build (`engine/build_index.py`),
  library location rule (`engine/libroot.py`), cost model and monthly budget gate
  (`engine/cost_report.py`, `engine/budget_check.py`) and the demo bundler
  (`engine/bundle_demo.py`).
- Sync log and first Granola backfill (Oct 20).
