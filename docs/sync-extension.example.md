# Sync extension (TEMPLATE; the real copy is SYNC-EXTENSION.md in your library, private)

_Read by the scheduled run after the base `meeting-library-sync` skill._

Local to this library, so it survives skill and kit updates. The base skill handles Granola. This file adds Gemini notes, the manual queue, your settings and your rules. Privacy: all of this is private HR and client material. Read Drive and Gmail only; never write to them; never send contents to any connector; never publish.

## 0. Read settings first (config.json, ops/rates.json)
- `granola.enabled`, `gemini.enabled`, `gemini.drive_safety_net`, `gemini.lookback_days`, `gemini.max_doc_kb`, `local_files.enabled`. A connector that is off is skipped. Never edit, hide or delete notes because a connector is off.
- Budget gate (`engine/budget_check.py`) still runs first, as in the base skill.
- Read `rules/resolutions.md` before writing any note. Apply it: spell names as written there, honour "not a person", obey general rules. Never edit `rules/` or `ops/review.json` by hand except the review additions in step 5.

## 1. Granola (base skill)
Follow the base skill. HARD RULE: when Granola refreshes an existing note whose frontmatter has `sources: [granola, gemini]` or `coverage: both`, keep its `## Gemini cross-check` section and every line ending `*(added from Gemini)*`, and the frontmatter lines `sources`, `coverage`, `drive_id`, `drive_url`, `gemini_checked`. If unsure, do not rewrite the note; list it as "refresh skipped, merged note".

## 2. Gemini (if gemini.enabled)
Window: from the earlier of (last gemini_checked date in ops/gemini-ledger.jsonl) and (today minus lookback_days). Find "Notes by Gemini" emails in Gmail (sender gemini-notes@google.com, page size max 50) in that window and take the Drive doc link from each. If gemini.drive_safety_net: also search Drive for "Notes by Gemini" docs modified in the window and add any not yet in the ledger. Skip shortcuts and duplicates. Skip docs over max_doc_kb: ledger status `skipped`. Read docs with Drive `read_file_content`. Calendar event ids in titles are unreliable for dates; Drive created time confirms the date.
Match each doc to a Granola note: same date, start time within 30 minutes, shared participants. Match found: merge. No match: Gemini-only note. Unsure: Gemini-only note plus a review item.
Templates to copy exactly: see any note with `source: gemini` (Gemini-only) and any with `coverage: both` (merged), e.g. `notes/2026-10-22-matteo-jordan.md` (merged) and `notes/2026-10-23-vendor-call-harbor-systems.md` (Gemini-only) in `sample/`. Rules:
1. No em dashes in text you write (verbatim Gemini/Granola text stays as is).
2. Never invent an owner. Use one only when Gemini names it in brackets. The user's own actions are `**<owner first name>**`.
3. Gemini "Aligned" become `**Decision:**`; "Needs Further Discussion" become `**Open:**`. At most 3 extra decisions only if Details clearly show something was settled, marked `(inferred from Details)`.
4. Recall: 3 to 5 lines, substance first, neutral wording, no guessed genders.
5. participants = invitees minus <owner>; mentioned = people discussed but absent. Keep Gemini's spelling for doubtful names and add tag `needs-name-check`; never merge names you cannot verify. Companies and projects are not people.
6. type: 1:1, client, internal, internal-group, onboarding, separation, community, event ("Weekly Sync" is internal-group). Tags in kebab-case; add `sensitive` when the meeting fits the definition in `config.json` under `sensitive.definition` (the owner edits it on the settings page; default: performance, separations, compensation, security incidents, named staffing or retention); add `gemini-only` for Gemini-only notes.
7. Filename `YYYY-MM-DD-kebab-slug.md` (append HH-MM on collision). Gemini-only frontmatter: title, date, time, updated, type, participants, mentioned, tags, source: gemini, sources: [gemini], coverage: gemini-only, drive_id, drive_url, gemini_checked.
8. Gemini-only body: `## Recall`, `## Decisions & actions`, `## Note` (Summary and Details copied verbatim, entities and mojibake fixed), `## Source check` (single-source warning, names to verify, inconsistencies).
9. Merged note: copy the Granola note verbatim; add the frontmatter lines; append only missing items to Decisions & actions, each ending `*(added from Gemini)*`; add `## Gemini cross-check` (match basis, agrees, added, differs, not carried and why, Granola-only). Unreliable items go in the cross-check as held, not into actions. Do not change `updated:` or `granola_id`.
10. Append one line per doc to ops/gemini-ledger.jsonl: `{"drive_id","title","meeting_at","status":"new|merged|skipped|review","note","flags":[]}`.

## 3. Manual queue (if local_files.enabled or Drive links present)
Read `inbox/queue.json`. For each `pending` item: `drive` = read that doc (Drive); `file` or `transcript` = read `inbox/files/<name>` (txt, md, docx, pdf). Turn it into a note with the Gemini-only template (frontmatter `source: manual`, no `gemini-only` tag unless it is a Gemini doc); if the item has `sensitive: true`, add tag `sensitive`. Transcripts have no summary: write Recall, decisions and actions from them, flag uncertainty. Set the item `status` to `done` with `note` = filename, or `failed` with a short reason. Never delete queue files.

## 4. Rebuild and log
`python3 engine/build_index.py`. Append one line to ops/sync-log.jsonl as the base skill does, adding `gemini_new`, `gemini_merged`, `queue_done`.

## 5. Needs review
If anything unclear came up (garbled names, owners not in the meeting, empty docs, inconsistencies), it is in the note's Source check or cross-check. Then run `python3 engine/review.py seed` so it shows under Settings > Needs review. This keeps existing answers.

## 6. Report
Briefly: what was added or merged (titles and dates), queue items handled, anything skipped or failed, new review items. Make failures loud: a silent Granola or Gmail failure loses data.
