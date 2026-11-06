# Backlog

Ideas and planned work for the Meeting Library, grouped by epic. Say "put in the backlog"
in a session to add an item, and "show the backlog" to see it. Keep items free of real
names and meeting content: this file is published with the code.

Status: **idea** (noted, not decided), **next** (wanted soon), **doing**, **done**.

## Epic: Local server (the library's own backend)

The small server on this computer already saves changes, rebuilds the data, starts at
login and answers the page. These items grow it, one feature at a time, staying local.

| Item | Status | Added | Notes |
|---|---|---|---|
| Health strip on the page | next | 2026-11-06 | Last sync time, this month's cost against the cap, failed fetches. |
| Meeting prep brief | next | 2026-11-06 | One click on a person or account: open actions, recent decisions, past conversations. Printable. |
| Fast search on the server | idea | 2026-11-06 | Full text across all notes; enables "what did I tell X about Y" from the dashboard. |
| Weekly digest | idea | 2026-11-06 | Built on a schedule: the week's decisions and open actions, ready on Monday morning. |
| Edit names, tags and sensitivity from the page | idea | 2026-11-06 | The server writes the change and rebuilds. |
| Ask the library questions | idea | 2026-11-06 | The server calls Claude itself. Needs an API key kept in a local file and billed per use. Could also let the server start the sync directly. |
| Phone access at home | idea | 2026-11-06 | Needs a login and careful network settings; notes are sensitive. Do a privacy review first. |

## Epic: Sharing and hosting

| Item | Status | Added | Notes |
|---|---|---|---|
| Read-only mode for colleagues | idea | 2026-11-06 | The static page still works without the server. Make this split explicit. |
| Hosted backend | idea | 2026-11-06 | Database instead of files, logins, hosting, and a decision on what leaves this computer. Separate project with its own privacy review. |

## Epic: Sync and sources

| Item | Status | Added | Notes |
|---|---|---|---|
| Start the sync directly from the button | idea | 2026-11-06 | Scheduled desktop tasks have no API trigger. Needs an API key or the Claude Code command line. Today the button opens the Claude scheduled tasks page. |

## Epic: Housekeeping

| Item | Status | Added | Notes |
|---|---|---|---|
| Ignore all backup files in `.gitignore` | idea | 2026-11-06 | `.bak10` and up are not covered today. Guarded file: needs the owner's yes. |
| Empty the `_to_delete` folder | idea | 2026-11-06 | Old copies of the viewer; already ignored by git. |

## Done

| Item | Date | Version |
|---|---|---|
| Saving through the local server only, auto-start at login | 2026-11-05 | 1.5.0 |
| Run fetch now button on the dashboard and in Settings (opens Claude scheduled tasks) | 2026-11-05 | 1.5.0 |
