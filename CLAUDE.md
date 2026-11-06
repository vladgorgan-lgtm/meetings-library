# Rules for working in this project (Claude and people)

This folder is the Meetings Library. It is also published to GitHub
(vladgorgan-lgtm/meetings-library), so some rules never bend.

## Privacy
- Real notes, names, config, logs and anything generated from them stay local. They are
  excluded by `.gitignore` and must never be committed, pasted into code, docs, examples,
  commit messages or release notes.
- Private data goes in private files (for example `ops/curated-checks.json`), never in code.
- Examples use invented people and companies.
- The privacy rules are locked: `.gitignore`, `tools/publishable.py`, `tools/scan-allow.txt`
  and `tools/scan-ignore-terms.txt` are guarded. Do not change them, and never run
  `publishable.py approve`, unless the owner has seen the exact change and said yes in chat.

## Publishing
- "push to git": follow `docs/publishing.md`. Run the scan first; if it fails, stop.
- "log today": add entries to `CHANGELOG.md` and `docs/PROGRESS.md`.
- Never copy the folder wholesale. Only files from `tools/publishable.py list` leave this disk.

## Style
- No em dashes in anything written for the owner; use commas, colons or periods.

## Backlog
- "put in the backlog": add the item to `docs/BACKLOG.md` under the right epic (create an epic
  if none fits) with status `idea`, today's date and a one-line note. Confirm in one line.
- "show the backlog": summarise `docs/BACKLOG.md` by epic, `next` items first.
- When an item ships, move it to the Done table with the date and version.
- Items never contain real names or meeting content: the file is published.
