---
title: "Architecture review: ingestion service"
date: 2026-10-23
time: "15:00"
updated: 2026-10-23T16:15:00Z
type: internal
participants:
  - "[[Priya Raman]]"
  - "[[Matteo Bellini]]"
  - "[[Tomas Novak]]"
mentioned: []
tags: [architecture, platform, ingestion]
source: granola
---
# Architecture review: ingestion service

## Recall
Reviewed options for the ingestion service: keep the current batch design or move to a queue with workers. The group chose the queue, phased over two releases.

## Decisions & actions
- **Decision:** Move ingestion to a queue with workers, starting in release 4.3.
- **Decision:** Keep the batch path available behind a flag for one release.
- [ ] **Priya** - Write the design note and circulate it by Wednesday
- [ ] **Tomas** - Estimate infrastructure cost for the queue

## Note
### Summary
The queue removes the nightly batch window and makes retries explicit.

### Details
Risk: migration of in-flight jobs. The flag gives a rollback path.
