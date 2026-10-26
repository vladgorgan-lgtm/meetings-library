# Meeting Library

> **About this repository.** It contains the kit (viewer, engine, docs) and a fictional
> demo in `sample/`. Your own notes, config and generated data are listed in
> `.gitignore` and never committed. Try it: `python3 engine/build_index.py --library sample`.
> History: [CHANGELOG.md](CHANGELOG.md) and [docs/PROGRESS.md](docs/PROGRESS.md).
> Templates for your own library: `templates/`. Rules for working here: [CLAUDE.md](CLAUDE.md);
> how publishing works: [docs/publishing.md](docs/publishing.md).

A durable local archive of Granola enhanced notes, with a browsable dashboard.
Granola's free plan keeps **30 days of history**; this folder is the copy that
survives.

## Layers: what is shared, what is yours

```
 SHIPPED — the kit, identical for everyone        YOURS — never leaves this disk
 ────────────────────────────────────────         ──────────────────────────────
 index.html   ui/app.css   ui/app.js   ◄─ reads ── data/library.js   (generated)
       ▲  contract 2: LIBRARY schema 1                     ▲
 engine/build_index.py  cost_report.py  ── writes ─────────┘
        budget_check.py bundle_demo.py      reads ── notes/*.md      (the archive)
       ▲  contract 1: note format                          config.json
 meeting-library-sync skill (ingest)  ── writes ──►        ops/sync-log.jsonl
                                                           ops/rates.json
```

| Layer | Files | Contains meeting content? | Safe to share? |
|---|---|---|---|
| **UI** | `index.html`, `ui/` | No. Static, reads `window.LIBRARY` | Yes |
| **Engine** | `engine/` | No. Code only | Yes |
| **Ingest** | the `meeting-library-sync` skill | No. Procedure only | Yes |
| **Data** | `notes/`, `data/`, `config.json`, `ops/sync-log.jsonl` | **Yes** | **Never** |
| **Demo** | `sample/`, `demo.html` | Fictional only | Yes |

The two contracts are the only coupling:

1. **Note format** (ingest → engine): frontmatter plus the headings `## Recall`,
   `## Decisions & actions`, `## Note`, `## Private notes`. Renaming a heading
   silently empties that part of the page.
2. **LIBRARY schema** (engine → UI): `data/library.js` sets
   `window.LIBRARY = {schema, kit, built, title, owner, demo, entries, dash, cost}`.
   Change the shape → bump `SCHEMA` in `engine/build_index.py` **and**
   `SUPPORTED_SCHEMA` in `ui/app.js` together. A mismatch shows a clear message
   instead of a blank page.

Data is a `<script>`, not JSON, on purpose: Chrome blocks `fetch()` on `file://`.
Same reason routing uses the URL hash.

## Commands

```bash
python3 engine/build_index.py        # notes/ -> data/library.js  (instant, offline)
python3 engine/budget_check.py       # monthly cap gate: exit 0 ok, 2 over, 1 broken
python3 engine/cost_report.py        # spend per month, runaway alerts
```

Every engine script takes `--library PATH` (or `$MEETING_LIBRARY`); default is
the folder above `engine/`. Try the demo data:

```bash
python3 engine/build_index.py --library sample
```

## Personal settings — `config.json`

| Key | Meaning |
|---|---|
| `owner` | Your name. Dropped from participant lists; action owner for `me_aliases` |
| `me_aliases` | How you appear as an action owner in notes, e.g. `["Jordan"]` |
| `aliases` | Misspelling → canonical name, e.g. `{"Jon Smit": "John Smith"}` |
| `title` | Page title |
| `cadence`, `plan`, `auto_tag_sensitive` | Read by the sync skill |

## Upgrading

Replace `index.html`, `ui/`, `engine/` and `VERSION` from a newer kit, then run
`python3 engine/build_index.py`. Nothing in `notes/`, `config.json` or `ops/` is
touched. The sync skill does this for you when asked to "upgrade the meeting
library".

## Customising the look

Edit `ui/app.css` / `ui/app.js`, rebuild, reload. To offer a UI change to
colleagues, send those two files (or a new kit): they contain no data.
Test against `sample/` before sending.

## Sharing a demo

```bash
python3 engine/build_index.py --library sample
python3 engine/bundle_demo.py --library sample --out demo.html
```

`bundle_demo.py` refuses any library whose `config.json` lacks `"demo": true`,
so a real archive cannot be bundled into a shareable page by accident.

## Privacy

`notes/` and `data/library.js` hold named performance feedback, separations,
compensation and client-confidential material. Keep them local: not published,
not attached, not synced to a connector, not in a shared drive. Sharing the kit
means sharing code and the empty viewer — never this folder.

## Insights layer (decisions)

Optional middle layer between the notes and the dashboard. Granola's own
`**Decision:**` lines are always shown untouched; the layer only *adds* decisions
Granola missed, each with an evidence quote and an importance (3 = "key").

- `rules/decisions.md` and `rules/settings.json`: tunable rules (placeholder for now,
  `enabled` is false). Editing either marks every insight stale.
- `data/insights/<note-id>.json`: one result per meeting (private, like `notes/`).
- `python3 engine/insights.py status`: which notes need analysis (new, changed,
  or rules changed). Quiet days list nothing, so they cost nothing.
- `python3 engine/insights.py validate`: shape check.
- The build merges both sources and drops layer decisions that restate Granola's.
  If the layer breaks, the build still runs without it.
- In the dashboard the x only hides a decision in this browser; it never edits notes.

### Decision groups

`data/groups.json` clusters related decisions under one headline and merges repeats
(the same decision recorded in several meetings shows once, with every source).
It is written by the grouping step and holds a hash of the decision set; when new
decisions arrive the build prints "decision grouping is stale" and the step reruns
(about 40 decisions, a few cents). Keys that disappear are skipped, so a stale file
only means fewer groups. Decisions the layer adds from `sensitive`-tagged notes carry
`sensitive: true` and sit behind "show sensitive" in the Decisions box.
