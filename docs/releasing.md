# Releasing

The repository is the single source of truth. The `meeting-library-sync` skill is a thin
stub: on every run it checks the latest release tag here, and follows
`skill/INSTRUCTIONS.md` and the code from that tag. A release is therefore all it takes to
update every installation.

## Steps

1. Finish the change and rebuild the demo (`python3 engine/build_index.py --library sample`).
2. Update `VERSION` and move the entries from `[Unreleased]` to a new version in `CHANGELOG.md`.
3. If `templates/config.example.json` or `templates/rates.example.json` gained keys, say so in the
   changelog; installations add missing keys on upgrade and never change existing values.
4. If the change alters what users must do (not only the code), say it under a "Needs attention"
   heading in the changelog; the skill reports that section after an upgrade.
5. Say "push to git" (see `publishing.md`). The scan must pass.
6. Nothing else. The GitHub Action in `.github/workflows/release.yml` creates the tag
   `vMAJOR.MINOR.PATCH` and the GitHub release from `VERSION` and the matching `CHANGELOG.md`
   section, once per version. Claude sessions cannot create tags or releases themselves.

One-time setting: in the repository, Settings, Actions, General, Workflow permissions, choose
"Read and write permissions". If a release does not appear, open the Actions tab and check
the `release` run.

## Version rules

- PATCH: fixes. MINOR: new features, new config keys with safe defaults. Both update
  installations automatically.
- MAJOR: a change that needs a person (schema change, removed setting, new connector). The skill
  asks before upgrading across a major version.
- Never move or delete a published tag. Fix forward with a new patch.

## What must never be in a release

Anything from `notes/`, `data/`, `ops/`, `inbox/`, `sources/`, `config.json` or
`SYNC-EXTENSION.md`. The scan enforces it, and only files from `publishable.py list` are pushed.
Protect `main` and tags on GitHub (branch protection, tag protection): the skill follows
whatever a release contains.
