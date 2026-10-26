# Meetings Library: progress

## Summary

The Meetings Library keeps a durable local copy of meeting notes and turns them into
a searchable dashboard: topics, people, open actions and decisions. It started on
Oct 20, 2026 as a way to keep Granola notes beyond the free plan's history window,
and grew into a small platform with two note sources (Granola and Google Meet notes
by Gemini), a local settings page, a monthly cost cap, a review workflow for unclear
names, and a decisions layer that adds what the notes missed.

Design principle: the code is shareable, the data never is. Meeting content stays on
the local disk; this repository holds the code, the documentation and a fictional demo.

Where it is heading: richer decision rules, wider sharing with colleagues, a proper
release process.

## Timeline

| Date | What happened | Version |
|---|---|---|
| Oct 20 | First sync from Granola: the archive started and the sync log began. | |
| Oct 21 | First complete kit: viewer, data build, cost model, budget gate, demo bundler. | 1.0.0 |
| Oct 23 | Decisions layer scaffolded: rules and settings files, documentation. Viewer polished. | 1.1.0 |
| Oct 26 | Second source added (Gemini notes, merged per meeting). Local settings page and server, "Run fetch now", needs-review workflow, backups before each risky change. Repository created with a fictional demo. | 1.2.0 |
| Oct 26 (evening) | Publishing made safe and repeatable: one command, a leak scan over exactly the files that may leave the computer, and the library folder aligned with the repository. | 1.2.1 |
| Oct 26 (night) | Privacy rules locked: the publish check refuses to run if the ignore rules or the check itself were changed without the owner's approval. Rules written into the folder for any session. | 1.2.2 |

## How this file is kept

Each working session ends with a short entry here and a matching technical entry in
[CHANGELOG.md](../CHANGELOG.md). Entries before the repository existed were
reconstructed from file dates and run logs.
