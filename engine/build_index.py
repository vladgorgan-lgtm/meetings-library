#!/usr/bin/env python3
"""
Build the DATA layer: notes/*.md  ->  data/library.js

This script never writes HTML. The viewer (index.html + ui/) is static and the
same for everyone; this produces the one file that is yours:

    window.LIBRARY = { schema, kit, built, title, owner, demo,
                       entries, dash, cost }

Contract 1 (input):  the note format — frontmatter + "## Recall",
                     "## Decisions & actions", "## Note", "## Private notes".
Contract 2 (output): LIBRARY schema 1. Bump SCHEMA when the shape changes and
                     bump SUPPORTED_SCHEMA in ui/app.js in the same release.

Personal settings come from <library>/config.json (owner, aliases, title), never
from this file. No third-party dependencies.

  python3 engine/build_index.py                       # your library
  python3 engine/build_index.py --library kit/sample  # the demo dataset
"""

import html
import json
import math
import os
import re
from datetime import date, datetime, timedelta

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libroot import ENGINE, library_root  # noqa: E402

SCHEMA = 1
ROOT = library_root()
NOTES_DIR = os.path.join(ROOT, "notes")
OUT_DIR = os.path.join(ROOT, "data")
OUT = os.path.join(OUT_DIR, "library.js")


def kit_version():
    for p in (os.path.join(ROOT, "VERSION"), os.path.join(os.path.dirname(ENGINE), "VERSION")):
        if os.path.exists(p):
            return open(p, encoding="utf-8").read().strip()
    return "dev"


def load_config():
    p = os.path.join(ROOT, "config.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


CONFIG = load_config()
# "Jon Smit" -> "John Smith": one spelling per person, from config only.
ALIASES = {k.strip().lower(): v.strip() for k, v in (CONFIG.get("aliases") or {}).items()}


def _load_json(rel, default):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


# Answers from the settings page (Needs review). Deterministic part only: a variant
# spelling becomes the canonical name, or is dropped as "not a person". Notes on disk
# are never edited; the rules apply here, at build time.
RESOLUTIONS = _load_json("rules/resolutions.json", {})
NOT_PERSON, TERMS = set(), {}
_items = {i["id"]: i for i in _load_json("ops/review.json", {}).get("items", [])}
for _iid, _res in (RESOLUTIONS.get("items") or {}).items():
    if _res.get("status") != "answered":
        continue
    _kind = (_items.get(_iid) or {}).get("kind", "names")
    for _v, _m in (_res.get("map") or {}).items():
        _v = _v.strip()
        if _m.get("not_person"):
            NOT_PERSON.add(_v.lower())
        elif _m.get("canonical"):
            if _kind == "term":
                TERMS[_v] = _m["canonical"]
            else:
                ALIASES[_v.lower()] = _m["canonical"]
OVERRIDES = _load_json("rules/overrides.json", {})
SENS_ADD, SENS_REMOVE = set(OVERRIDES.get("add") or []), set(OVERRIDES.get("remove") or [])
SENS_TITLES = [t.lower() for t in (OVERRIDES.get("title_patterns") or [])]
# What counts as sensitive. The definition text is what the sync reads when it tags a note
# (the owner edits it on the settings page, stored in config.json). The keywords are the
# free, deterministic part: a meeting whose title, tags or text contains one is marked here.
DEFAULT_SENSITIVE = ("Performance reviews or concerns about a named person; separations, departures "
                     "and retention risk; compensation, salary and bonus; security incidents; "
                     "named staffing decisions.")
_SC = CONFIG.get("sensitive") or {}
SENS_DEFINITION = (_SC.get("definition") or "").strip() or DEFAULT_SENSITIVE
SENS_KEYWORDS = [k.strip().lower() for k in (_SC.get("keywords") or []) if str(k).strip()]
# tags that describe how a note was captured, not what it is about; never a topic card
TOPIC_EXCLUDE = set({"no-summary", "sensitive", "difficult-conversation",
                                             "gemini-only", "needs-name-check", "gemini-merged"}) \
    | set(CONFIG.get("topic_exclude") or [])
OWNER_NAME = (CONFIG.get("owner") or "").strip()
# names that mean the owner in action lines. Explicit only: a bare first name can
# belong to someone else too (two Alexes), so it is folded only if config says so.
ME = {n.strip().lower() for n in (CONFIG.get("me_aliases") or [])} | (
    {OWNER_NAME.lower(), "me"} if OWNER_NAME else set())


def canon(name):
    return ALIASES.get(name.strip().lower(), name.strip())


def fix_terms(text):
    for bad, good in TERMS.items():
        text = re.sub(r"\b" + re.escape(bad) + r"\b", good, text)
    return text


def canon_owner(name):
    if OWNER_NAME and name.strip().lower() in ME:
        return OWNER_NAME
    return canon(name)

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
HALFLIFE_DAYS = 14.0


# ----------------------------------------------------------------- parsing

def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end].strip("\n"), text[end + 4:].lstrip("\n")

    meta, key = {}, None
    for line in raw.split("\n"):
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and line.strip().startswith("- "):
            if key:
                meta.setdefault(key, [])
                if isinstance(meta[key], list):
                    meta[key].append(clean_scalar(line.strip()[2:]))
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if val == "":
                meta[key] = []
            elif val.startswith("[") and val.endswith("]"):
                meta[key] = [clean_scalar(p) for p in val[1:-1].split(",") if p.strip()]
            else:
                meta[key] = clean_scalar(val)
    return meta, body


def clean_scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return WIKILINK.sub(r"\1", v).strip()


def section(body, heading):
    m = re.search(r"^##\s+" + re.escape(heading) + r"\s*$", body, re.M)
    if not m:
        return ""
    rest = body[m.end():]
    nxt = re.search(r"^##\s+", rest, re.M)
    return (rest[:nxt.start()] if nxt else rest).strip()


def dedupe(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


def as_list(v):
    return [] if not v else (v if isinstance(v, list) else [v])


def day_label(iso, today):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return iso
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    fmt = "%a, %b %-d" if os.name != "nt" else "%a, %b %#d"
    out = d.strftime(fmt)
    return out if d.year == today.year else out + d.strftime(", %Y")


def pretty_time(t):
    if not t or ":" not in t:
        return ""
    try:
        h, m = (int(x) for x in t.split(":")[:2])
    except ValueError:
        return t
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def people_label(people):
    if not people:
        return ""
    if len(people) == 1:
        return people[0]
    f = [p.split()[0] for p in people]
    if len(people) == 2:
        return f"{f[0]} & {f[1]}"
    return f"{f[0]}, {f[1]} & {len(people) - 2} others"


def age_days(iso, today):
    try:
        return max(0, (today - datetime.strptime(iso, "%Y-%m-%d").date()).days)
    except ValueError:
        return 999


def decay(days):
    return math.pow(0.5, days / HALFLIFE_DAYS)


# ----------------------------------------------------------------- actions

ACTION = re.compile(r"^-\s*\[( |x|X)\]\s*(.+)$")
DECISION = re.compile(r"^-\s*\*\*Decision:\*\*\s*(.+)$")
OWNER = re.compile(r"^\*\*(.+?)\*\*\s*[—–-]\s*(.+)$")


def extract_actions(text):
    """Pull open actions and decisions out of a 'Decisions & actions' section."""
    actions, decisions = [], []
    for raw in text.split("\n"):
        line = raw.strip()
        d = DECISION.match(line)
        if d:
            decisions.append(d.group(1).strip())
            continue
        a = ACTION.match(line)
        if not a:
            continue
        done, rest = a.group(1).lower() == "x", a.group(2).strip()
        o = OWNER.match(rest)
        owner, what = (canon_owner(o.group(1)), o.group(2).strip()) if o else ("", rest)
        actions.append({"done": done, "owner": owner, "what": what})
    return actions, decisions


# ----------------------------------------------------------------- collect

def collect():
    entries = []
    if not os.path.isdir(NOTES_DIR):
        return entries
    today = date.today()
    for name in sorted(os.listdir(NOTES_DIR)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(NOTES_DIR, name), encoding="utf-8") as fh:
            meta, body = parse_frontmatter(fh.read())
        if not meta.get("date"):
            continue
        people = dedupe(canon(p) for p in as_list(meta.get("participants"))
                        if p.strip().lower() not in NOT_PERSON)
        if OWNER_NAME:  # the owner is in every meeting; listing them adds noise
            people = [p for p in people if p != OWNER_NAME]
        title = str(meta.get("title") or name[:-3])
        iso = str(meta.get("date"))
        acts_text = section(body, "Decisions & actions")
        acts_text = fix_terms(acts_text)
        actions, decisions = extract_actions(acts_text)
        tags = as_list(meta.get("tags"))
        nid = name[:-3]
        hay = (title + " " + " ".join(tags) + " " + body).lower() if SENS_KEYWORDS else ""
        sensitive = (("sensitive" in tags or nid in SENS_ADD
                      or any(t in title.lower() for t in SENS_TITLES)
                      or any(k in hay for k in SENS_KEYWORDS)) and nid not in SENS_REMOVE)
        entries.append({
            "id": name[:-3],
            "file": "notes/" + name,
            "title": title,
            "date": iso,
            "day": day_label(iso, today),
            "time": pretty_time(str(meta.get("time") or "")),
            "sort": str(meta.get("time") or "00:00"),
            "updated": str(meta.get("updated") or ""),
            "type": str(meta.get("type") or "other"),
            "account": str(meta.get("account") or ""),
            "people": people,
            "who": people_label(people),
            "initial": (people[0][:1] if people else title[:1]).upper(),
            "mentioned": [m for m in dedupe(canon(p) for p in as_list(meta.get("mentioned"))
                                            if p.strip().lower() not in NOT_PERSON)
                          if m not in people and m != OWNER_NAME],
            "tags": tags,
            "sensitive": sensitive,
            "source": str(meta.get("source") or "granola"),
            "url": str(meta.get("granola_url") or ""),
            "drive_url": str(meta.get("drive_url") or ""),
            "coverage": str(meta.get("coverage") or ""),
            "recall": fix_terms(section(body, "Recall")),
            "actions_md": acts_text,
            "actions": actions,
            "decisions": decisions,
            "note": section(body, "Note"),
            "private": section(body, "Private notes"),
            "full": WIKILINK.sub(r"\1", body),
            "age": age_days(iso, today),
        })
    entries.sort(key=lambda e: (e["date"], e["sort"]), reverse=True)
    return entries


# ----------------------------------------------------------------- dashboard

PLAIN_TAGS = TOPIC_EXCLUDE


_GROUPS = []          # filled by merged_decisions, read right after it in build_dashboard


def merged_decisions(decisions, entries):
    """Granola's decisions, plus whatever the insights layer added. The layer is
    optional and can never break the build."""
    for d in decisions:
        d.setdefault("source", "granola")
    try:
        import insights
        insights.use_library(ROOT)
        decisions = insights.merge_into(decisions, entries)
    except Exception as exc:
        print(f"insights layer skipped ({exc})")
    decisions = sorted(decisions, key=lambda d: d["date"], reverse=True)[:60]
    _GROUPS[:] = []
    try:
        _GROUPS.extend(insights.resolve_groups(decisions))
        if insights.settings()["enabled"] and insights.grouping_stale(decisions):
            print("decision grouping is stale: new or removed decisions since the last grouping")
    except Exception as exc:
        print(f"decision grouping skipped ({exc})")
    return decisions


def build_dashboard(entries):
    """Recency-weighted signals. A topic scores on how recent AND how connected
    it is — a tag on three notes across two weeks beats one on five notes in
    March. Half-life is 14 days."""
    topics, people, open_acts, decisions = {}, {}, [], []

    for e in entries:
        w = decay(e["age"])
        reach = len(set(e["people"]) | set(e["mentioned"]))

        for t in e["tags"]:
            if t in PLAIN_TAGS:
                continue
            d = topics.setdefault(t, {"tag": t, "score": 0.0, "notes": [], "people": set()})
            d["score"] += w * (1 + reach * 0.15)
            d["notes"].append({"id": e["id"], "title": e["title"], "day": e["day"], "date": e["date"],
                               "sensitive": e["sensitive"]})
            d["people"].update(e["people"])

        for p in set(e["people"]) | set(e["mentioned"]):
            d = people.setdefault(p, {"name": p, "score": 0.0, "n": 0, "last": e["date"],
                                      "lastDay": e["day"], "present": 0})
            d["score"] += w * (2.0 if p in e["people"] else 1.0)
            d["n"] += 1
            if p in e["people"]:
                d["present"] += 1

        for a in e["actions"]:
            if a["done"]:
                continue
            open_acts.append({**a, "id": e["id"], "title": e["title"],
                              "day": e["day"], "date": e["date"], "age": e["age"],
                              "sensitive": e["sensitive"]})
        for d_ in e["decisions"]:
            decisions.append({"text": d_, "id": e["id"], "title": e["title"],
                              "day": e["day"], "date": e["date"], "sensitive": e["sensitive"]})

    top_topics = sorted(topics.values(), key=lambda d: -d["score"])[:18]   # the page hides sensitive refs, so keep spare
    for t in top_topics:
        t["notes"].sort(key=lambda n: n["date"], reverse=True)
        t["notes_n"] = len(t["notes"])
        t["people_n"] = len(t["people"])
        t["last"] = t["notes"][0]["day"] if t["notes"] else ""
        t["people"] = sorted(t["people"])[:4]
        t["score"] = round(t["score"], 2)

    top_people = sorted(people.values(), key=lambda d: -d["score"])[:14]
    for p in top_people:
        p["score"] = round(p["score"], 2)

    # owners with the most outstanding items; owner aliases folded in canon_owner()
    by_owner = {}
    for a in open_acts:
        key = a["owner"] or "Unassigned"
        by_owner.setdefault(key, []).append(a)
    owners = sorted(by_owner.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    return {
        "topics": top_topics,
        "people": top_people,
        "open": sorted(open_acts, key=lambda a: a["date"], reverse=True),
        "owners": [{"owner": k, "items": v} for k, v in owners],
        "decisions": merged_decisions(decisions, entries),
        "dgroups": _GROUPS,
        "counts": {
            "notes": len(entries),
            "open": len(open_acts),
            "last30": sum(1 for e in entries if e["age"] <= 30),
            "people": len(people),
        },
    }


# ----------------------------------------------------------------- cost

COST_REPORT = os.path.join(ENGINE, "cost_report.py")


def build_cost():
    """Same model as ops/cost_report.py, imported rather than copied so the two
    can never drift. Returns a dashboard-shaped summary, or a reason it can't."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cost_report", COST_REPORT)
        cr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cr)
        cr.use_library(ROOT)
        rates, runs = cr.load_rates(), cr.load_runs()
    except Exception as exc:                       # missing, moved or broken
        return {"available": False, "why": f"Cost model unavailable ({exc})."}

    if not runs:
        return {"available": False,
                "why": "No sync runs logged yet — ops/sync-log.jsonl is empty."}

    months, alerts = {}, []
    for run in runs:
        key = str(run.get("ts", ""))[:7] or "unknown"
        m = months.setdefault(key, {"key": key, "runs": 0, "new": 0, "refreshed": 0,
                                    "empty": 0, "tokens": 0, "usd": 0.0})
        inp, out, usd = cr.cost_of(run, rates)
        m["runs"] += 1
        m["new"] += run.get("new", 0)
        m["refreshed"] += run.get("refreshed", 0)
        m["tokens"] += inp + out
        m["usd"] += usd
        if not run.get("written"):
            m["empty"] += 1

        total = run.get("notes_total") or 0
        if (total and not run.get("backfill")
                and run.get("written", 0) / total > rates["warn_rewrite_ratio"]):
            alerts.append(f"{run.get('ts', '?')}: rewrote {run['written']} of {total} notes "
                          f"— a rewrite-everything pattern, usually a bug in the "
                          f"updated_at comparison rather than real activity.")
        if usd > rates["warn_run_usd"]:
            alerts.append(f"{run.get('ts', '?')}: one run estimated at ${usd:.2f}, over the "
                          f"${rates['warn_run_usd']:.2f} per-run threshold.")

    ordered = [months[k] for k in sorted(months)]
    for m in ordered:
        m["label"] = month_label(m["key"])
        m["usd"] = round(m["usd"], 4)

    last, summary = ordered[-1], []
    if last["runs"]:
        per = last["usd"] / last["runs"]
        summary.append(f"**{last['label']}**: ${per:.2f} per run across "
                       f"{last['runs']} run{'s' if last['runs'] != 1 else ''}.")
        if last["empty"]:
            share = last["empty"] / last["runs"]
            line = (f"{last['empty']} of {last['runs']} runs ({share:.0%}) found nothing new "
                    f"— about ${last['empty'] * per:.2f} spent confirming no change.")
            if share > 0.5:
                line += " More than half were empty; a less frequent schedule would cost " \
                        "less for the same coverage."
            summary.append(line)
        if last["usd"] > rates["warn_monthly_usd"]:
            alerts.append(f"{last['label']}: ${last['usd']:.2f} is over the "
                          f"${rates['warn_monthly_usd']:.2f} monthly threshold.")

    # ---- monthly hard cap (ops/budget_check.py is the gate; this only reports) ----
    budget = {"enabled": False}
    try:
        import datetime as _dt
        cap = float(rates.get("monthly_budget_usd", 0) or 0)
        if cap > 0:
            this_key = _dt.date.today().strftime("%Y-%m")
            this_m = months.get(this_key)
            spent = this_m["usd"] if this_m else 0.0
            budget = {
                "enabled": True,
                "month": this_key,
                "label": month_label(this_key),
                "cap": round(cap, 2),
                "spent": round(spent, 4),
                "remaining": round(max(0.0, cap - spent), 4),
                "used": round(spent / cap, 4),
                "over": spent >= cap,
                "runs": this_m["runs"] if this_m else 0,
            }
            if budget["over"]:
                alerts.insert(0, f"Over the ${cap:.2f} cap for {budget['label']}: "
                                 f"${spent:.2f} estimated. Syncing is paused until "
                                 f"the 1st; a manual run can still override it.")
    except Exception:
        budget = {"enabled": False}

    return {
        "available": True,
        "model": rates["model"],
        "budget": budget,
        "months": ordered,
        "runs": sum(m["runs"] for m in ordered),
        "new": sum(m["new"] for m in ordered),
        "refreshed": sum(m["refreshed"] for m in ordered),
        "empty": sum(m["empty"] for m in ordered),
        "tokens": sum(m["tokens"] for m in ordered),
        "total_usd": round(sum(m["usd"] for m in ordered), 4),
        "summary": summary,
        "alerts": alerts,
    }


def month_label(key):
    try:
        return datetime.strptime(key, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return key



# ----------------------------------------------------------------- settings snapshot

def review_snapshot(entries):
    try:
        import review
        review.use_library(ROOT)
        return review.build(entries)
    except Exception as exc:
        print(f"review snapshot skipped ({exc})")
        return {"items": [], "general": [], "open": 0, "answered": 0}


def review_config():
    try:
        import review
        review.use_library(ROOT)
        return review.load_review_cfg()
    except Exception:
        return {}


def settings_snapshot():
    """What the settings page shows. Read-only copy; the server writes the real files."""
    cfg = CONFIG
    rates = _load_json("ops/rates.json", {})
    return {
        "cap": {"monthly_budget_usd": rates.get("monthly_budget_usd", 10),
                "warn_monthly_usd": rates.get("warn_monthly_usd", 8),
                "warn_run_usd": rates.get("warn_run_usd", 1.0)},
        "connectors": _load_json("ops/connectors.json", {}),
        "granola": cfg.get("granola") or {"enabled": True},
        "gemini": cfg.get("gemini") or {"enabled": True, "lookback_days": 2, "drive_safety_net": True,
                                         "max_doc_kb": 200, "backfill_from": "2026-09-01"},
        "local_files": cfg.get("local_files") or {"enabled": True, "max_mb": 5},
        "topic_exclude": sorted(TOPIC_EXCLUDE),
        "queue": _load_json("inbox/queue.json", {"items": []}).get("items", []),
        "overrides": {"add": sorted(SENS_ADD), "remove": sorted(SENS_REMOVE),
                      "title_patterns": OVERRIDES.get("title_patterns") or []},
        "sensitive": {"definition": SENS_DEFINITION, "default": DEFAULT_SENSITIVE,
                      "is_default": SENS_DEFINITION == DEFAULT_SENSITIVE,
                      "keywords": [k for k in (_SC.get("keywords") or []) if str(k).strip()],
                      "title_patterns": OVERRIDES.get("title_patterns") or []},
        "review": review_config(),
        "plan": cfg.get("plan", ""), "cadence": cfg.get("cadence", ""),
    }

# ----------------------------------------------------------------- write

def main():
    entries = collect()
    dash = build_dashboard(entries)
    cost = build_cost()
    library = {
        "schema": SCHEMA,
        "kit": kit_version(),
        "built": datetime.now().strftime("%d %b, %H:%M"),
        "title": CONFIG.get("title") or "Meeting Library",
        "owner": OWNER_NAME,
        "demo": bool(CONFIG.get("demo")),
        "entries": entries,
        "dash": dash,
        "cost": cost,
        "review": review_snapshot(entries),
        "settings": settings_snapshot(),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("/* generated by engine/build_index.py; private, do not share */\n")
        # </script> inside a note must not end the script tag in a bundled page
        fh.write("window.LIBRARY = " +
                 json.dumps(library, ensure_ascii=False).replace("</", "<\\/") + ";\n")
    os.replace(tmp, OUT)  # atomic: the viewer never sees a half-written file
    print(f"Wrote {OUT} ({len(entries)} entries, {dash['counts']['open']} open actions, "
          f"{os.path.getsize(OUT)//1024} KB, schema {SCHEMA})")
    if not entries:
        print("  No notes yet in", NOTES_DIR, "— the viewer will show an empty dashboard.")
    print("Top topics: " + ", ".join(f"{t['tag']}({t['score']})" for t in dash["topics"][:6]))
    print("Cost: " + (f"${cost['total_usd']:.2f} est. across {cost['runs']} runs"
                      if cost.get("available") else cost["why"]))


if __name__ == "__main__":
    main()
