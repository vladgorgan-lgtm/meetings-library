# Publishing to GitHub ("push to git")

The library folder on the computer is the working copy. GitHub holds only what is
safe to share: code, docs, templates and the fictional demo in `sample/`. Real notes,
config, logs and generated data never leave the disk (see `.gitignore`).

## The command

Say "push to git" in a session where the library folder is attached. Claude then:

1. Attaches the repo `vladgorgan-lgtm/meetings-library` with push access and clones it.
2. Runs `python3 tools/publishable.py scan` in the library folder. It checks every file
   that would be published against the real names in the private data. If anything is
   found, Claude stops and reports the file and the term. Nothing is pushed.
3. Runs `python3 tools/publishable.py list` and copies exactly those files into the
   clone. Files that are no longer in the list are removed from the clone, so the repo
   mirrors the folder.
4. Shows the file changes (added, changed, removed) in one short summary.
5. Commits with a plain message (what changed and why, one or two lines) and pushes `main`.
6. Reports the commit hash. Tags and releases are done only when asked.

"Log today" is separate: Claude adds an entry to `CHANGELOG.md` (technical) and
`docs/PROGRESS.md` (executive timeline) from what changed in the session, then you can
push.

## Rules that do not bend

- The scan must pass before any commit. A failed scan is never overridden to "get it out".
- Only the files from `publishable.py list` are copied. Claude never copies the folder
  wholesale and never stages `notes/`, `data/`, `ops/`, `inbox/`, `sources/`,
  `config.json`, `SYNC-EXTENSION.md` or the rules built from your answers.
- New private data goes into a private file, never into code. Example: name checks live
  in `ops/curated-checks.json`, not in `engine/review.py`.
- A phrase may be added to `tools/scan-allow.txt` only if it is a harmless example.
  Every line there weakens the check.
- Examples in docs and the UI use invented people and companies.

## New session checklist

- Attach `~/WORK/Meetings` (or open the project that has it).
- Repo access is by the Claude GitHub App on `vladgorgan-lgtm`, limited to this repo.
- If a push is refused with 403, the app lost access: reinstall or re-grant it.

## Versions

`VERSION` and `CHANGELOG.md` use semantic versions. A release is a tag such as `v1.2.0`
on the commit that carries that version. Tags can also be created on GitHub
(Releases, then Draft a new release).
