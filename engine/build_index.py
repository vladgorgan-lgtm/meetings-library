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
# Decision rules from the settings page (config.json "decision_rules", private).
#   spelling:   wrong spellings -> the right one, applied to everything the page shows
#   hot_topics: keywords to highlight / group on the Decisions page (applied in the viewer)
_DR = CONFIG.get("decision_rules") or {}
# "Keep fresh" presses on open actions (ops/keeps.json, private): {"<note id>|<action text>": {"count": n, "last": "YYYY-MM-DD"}}
def _apply_pending():
    """pending-changes*.json dropped in inbox/ (downloaded from the page): merge into ops/, then park the file."""
    d = os.path.join(ROOT, "inbox")
    if not os.path.isdir(d):
        return
    for name in sorted(os.listdir(d)):
        if not (name.startswith("pending-changes") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                pend = json.load(fh)
            os.makedirs(os.path.join(ROOT, "ops"), exist_ok=True)
            rem = [k for k in _load_json("ops/removed.json", []) if isinstance(k, str)]
            for k, v in (pend.get("removed") or {}).items():
                rem = [x for x in rem if x != k]
                if v:
                    rem.append(k)
            kp = _load_json("ops/keeps.json", {})
            for k, e in (pend.get("keeps") or {}).items():
                if int(e.get("count", 0)) > 0:
                    kp[k] = {"count": int(e["count"]), "last": str(e.get("last", ""))[:10]}
                else:
                    kp.pop(k, None)
            for rel, obj in (("ops/removed.json", rem[-3000:]), ("ops/keeps.json", kp)):
                with open(os.path.join(ROOT, rel), "w", encoding="utf-8") as fh:
                    json.dump(obj, fh, ensure_ascii=False, indent=2)
            os.replace(os.path.join(d, name), os.path.join(d, name + ".done"))
            print(f"applied {name}")
        except (OSError, ValueError, AttributeError) as exc:
            print(f"pending changes skipped ({name}: {exc})")


_apply_pending()
KEEPS = _load_json("ops/keeps.json", {})
# decisions removed from the quick list with the X (ops/removed.json, private): list of "<note id>|<decision text>"
REMOVED = [k for k in _load_json("ops/removed.json", []) if isinstance(k, str)]
SPELLING = []
for _r in (_DR.get("spelling") or []):
    _right = str(_r.get("right", "")).strip()
    for _w in (_r.get("wrong") or []):
        _w = str(_w).strip()
        if _w and _right and _w.lower() != _right.lower():
            SPELLING.append((re.compile(r"\b" + re.escape(_w) + r"\b", re.I), _right))
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


GEM_RX = re.compile(r"\s*\*\(added from Gemini(?:;\s*([^)]*))?\)\*", re.I)
INF_RX = re.compile(r"\s*\*?\(inferred from Details[^)]*\)\*?", re.I)
OWN_RX = re.compile(r"(?:,\s*|\s+[\u2014\u2013-]+\s+)(?:owner not stated|no owner yet)(?:\s*\(group\))?\.?\s*$", re.I)


def split_notes(text):
    """Take the bookkeeping out of the sentence: (clean text, flags). The page shows the flags as small
    markers with the original wording on hover. Notes on disk are not changed."""
    flags = {}
    m = GEM_RX.search(text)
    if m:
        flags["gemini"] = (m.group(1) or "").strip()
        if "inferred" in flags["gemini"].lower():
            flags["inferred"] = True
        text = GEM_RX.sub("", text)
    if INF_RX.search(text):
        flags["inferred"] = True
        text = INF_RX.sub("", text)
    if OWN_RX.search(text):
        flags["unassigned"] = True
        text = OWN_RX.sub("", text)
    return text.strip(), flags


def fix_spelling(text):
    """Your spelling-fix rules (settings > Spelling fixes). Notes on disk are never edited."""
    if not text:
        return text
    for rx, good in SPELLING:
        text = rx.sub(good, text)
    return text


def fix_terms(text):
    for bad, good in TERMS.items():
        text = re.sub(r"\b" + re.escape(bad) + r"\b", good, text)
    return fix_spelling(text)


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
        title = fix_spelling(str(meta.get("title") or name[:-3]))
        iso = str(meta.get("date"))
        acts_text = section(body, "Decisions & actions")
        acts_text = fix_terms(acts_text)
        actions, decisions = extract_actions(acts_text)
        tags = [fix_spelling(t).lower() for t in as_list(meta.get("tags"))]
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
            "note": fix_spelling(section(body, "Note")),
            "private": fix_spelling(section(body, "Private notes")),
            "full": fix_spelling(WIKILINK.sub(r"\1", body)),
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
    decisions = sorted(decisions, key=lambda d: d["date"], reverse=True)   # no cap: every decision reaches the page
    score_keys(decisions, entries)
    _GROUPS[:] = []
    try:
        _GROUPS.extend(insights.resolve_groups(decisions))
        if insights.settings()["enabled"] and insights.grouping_stale(decisions):
            print("decision grouping is stale: new or removed decisions since the last grouping")
    except Exception as exc:
        print(f"decision grouping skipped ({exc})")
    # spelling fixes last: groups.json matches on the raw text, so keep that as the key
    for d in decisions:
        d["key"] = d["id"] + "|" + d["text"]
        d["text"], d["flags"] = split_notes(fix_spelling(d["text"]))
        d["title"] = fix_spelling(d["title"])
    for g in _GROUPS:
        for k in ("title", "digest", "note"):
            g[k] = fix_spelling(g.get(k, ""))
        for i in g["items"]:
            i["text"], i["flags"] = split_notes(fix_spelling(i["text"]))
            for s in i["sources"]:
                s["title"] = fix_spelling(s["title"])
    return decisions


# How much a meeting matters, from things already in the note: no model calls.
TYPE_BASE = {"client": 35, "internal-group": 20, "internal": 15, "community": 10, "event": 10, "onboarding": 10}


def meeting_importance(entries, decisions):
    n_dec, n_key = {}, {}
    for d in decisions:
        n_dec[d["id"]] = n_dec.get(d["id"], 0) + 1
        if int(d.get("importance", 0) or 0) >= 3:
            n_key[d["id"]] = n_key.get(d["id"], 0) + 1
    out = {}
    for e in entries:
        att, men = len(e["people"]), len(e["mentioned"])
        parts = [("type " + e["type"], TYPE_BASE.get(e["type"], 5)),
                 (f"{att} attendees", min(att, 10) * 4), (f"{men} mentioned", min(men, 5)),
                 (f"{n_dec.get(e['id'], 0)} decisions", min(n_dec.get(e["id"], 0), 5) * 4)]
        if n_key.get(e["id"]):
            parts.append(("key decision", 10))
        if e["account"]:
            parts.append(("client account", 10))
        score = min(100, sum(p for _, p in parts))
        out[e["id"]] = {"score": score, "level": "high" if score >= 55 else "medium" if score >= 35 else "low",
                        "why": [f"{w} (+{p})" for w, p in parts if p]}
    return out


# ---- weight: a 0 to 100 score for every decision and every open action, no model calls ----
# Factors: money, people, client commitment, reach/policy, plus the weight of the meeting it came from.
# The page orders by this weight and by age; it shows no label. The insights layer's own 1-3 rating adds a
# small bonus. Weights can be overridden in rules/key.json (not part of the insights rules hash on purpose:
# changing them must not re-run the model).
KEY_DEFAULT = {"weights": {"money": 25, "people": 25, "client": 25, "reach": 20, "meeting": 15},
               "model_bonus": {"3": 20, "2": 5}}
KEY_RX = {
    "money": re.compile(r"\b(budget\w*|costs?|pric\w+|rates?|salar\w+|bonus\w*|invoic\w+|licen[cs]\w+|purchas\w+|"
                        r"contracts?|margins?|revenue|funding|expens\w+|spend\w*|payroll|hourly|eur|usd)\b|[€$]", re.I),
    "people": re.compile(r"\b(hir\w+|recruit\w+|promot\w+|separation\w*|terminat\w+|dismiss\w*|layoffs?|allocat\w+|"
                         r"staffing|staffed|onboard\w*|reassign\w*|bench|levell?ing|grad(?:e|ing)|performance review\w*|"
                         r"succession|ownership|resign\w*|retention|backfill|headcount)\b", re.I),
    "client": re.compile(r"\b(clients?|customers?|sla|escalat\w+|commitments?|committed|deadlines?|deliver(?:y|ables?)|"
                         r"proposals?|offers?|terms|sow|renewal|roadmap)\b", re.I),
    "reach": re.compile(r"\b(polic(?:y|ies)|process(?:es)?|rules?|guidelines?|standards?|framework|going forward|"
                        r"from now on|all (?:teams?|employees|managers|pms|members)|everyone|company[- ]wide|"
                        r"template|always|never|methodolog\w+)\b", re.I),
}


def key_settings():
    cfg = json.loads(json.dumps(KEY_DEFAULT))
    try:
        with open(os.path.join(ROOT, "rules", "key.json"), encoding="utf-8") as fh:
            o = json.load(fh)
        for k, v in o.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            elif not k.startswith("_"):
                cfg[k] = v
    except (OSError, ValueError):
        pass
    return cfg


def weigh(text, e, importance=0, cfg=None):
    """(score 0-100, why) for one decision or action text from its meeting entry e."""
    cfg = cfg or key_settings()
    w = cfg["weights"]
    top = sum(w.values()) or 1
    hit = [f for f, rx in KEY_RX.items() if rx.search(text or "")]
    pts = [(f, w.get(f, 0)) for f in hit]
    mw = min(100, TYPE_BASE.get(e.get("type"), 5) + min(len(e.get("people", [])), 10) * 4
             + (10 if e.get("account") else 0))
    pts.append(("meeting weight", round(w.get("meeting", 0) * mw / 100)))
    bonus = int(cfg["model_bonus"].get(str(int(importance or 0)), 0))
    if bonus:
        pts.append(("rated by the insights layer", bonus))
    return min(100, round(sum(p for _, p in pts) * 100 / top)), [f"{f} (+{p})" for f, p in pts if p]


def score_keys(decisions, entries):
    """Adds kscore (0-100) and kwhy to every decision."""
    cfg = key_settings()
    by_id = {e["id"]: e for e in entries}
    for d in decisions:
        d["kscore"], d["kwhy"] = weigh(d["text"], by_id.get(d["id"], {}), d.get("importance", 0), cfg)


# ---- action kind (step 1 of the decisions and actions rework) ----
# Each open action gets a label, nothing is moved or hidden:
#   "decide"  the action is really an open question ("investigate whether...", "align on...")
#   "follow"  the action restates or carries out a decision from the same meeting
#   None      a plain task
# Plain rules, no model calls. Tune the two lists below; the page only shows the label.
DECIDE_RX = re.compile(
    r"(?<!check )(?<!see )\b(whether|decide (?:on|if|whether)|decision (?:on|about)|agree on|"
    r"align (?:with .{1,40} )?on|go/no-go|makes? sense|which (?:way|option|approach)|think through|"
    r"figure out|confirm (?:if|acceptance|the decision|approval)|"
    r"(?:get|seek|ask for|obtain) (?:approval|sign[- ]off)|"
    r"explore|investigate|determine)\b", re.I)
_TOK = re.compile(r"[a-z]{4,}")
FOLLOW_MIN = 0.35   # word overlap with a decision from the same meeting


def _toks(t):
    return set(_TOK.findall((t or "").lower()))


def action_kind(what, same_meeting_decisions):
    """(kind, why) for one open action. why is the hover text on the page."""
    m = DECIDE_RX.search(what)
    if m:
        return "decide", 'wording: "' + m.group(0).lower() + '"', ""
    a = _toks(what)
    best, bt, bk = 0.0, "", ""
    for dtext, dkey in same_meeting_decisions:
        b = _toks(dtext)
        j = len(a & b) / max(1, len(a | b))
        if j > best:
            best, bt, bk = j, dtext, dkey
    if best >= FOLLOW_MIN:
        return "follow", "similar to a decision from the same meeting: " + bt[:90], bk
    return None, "", ""



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

    decisions_all = merged_decisions(decisions, entries)
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
    # age label: fresh up to 7 days, check in up to 21, probably done after that.
    # "Keep fresh" restarts the clock; kept twice, an action stays fresh.
    rank = {"fresh": 0, "check": 1, "old": 2}
    by_eid = {e["id"]: e for e in entries}
    dec_by_id = {}
    for d in decisions_all:
        dec_by_id.setdefault(d["id"], []).append((d["text"], d.get("key") or (d["id"] + "|" + d["text"])))
    today_ = date.today()
    for a in open_acts:
        a["key"] = a["id"] + "|" + a["what"]
        a["what"], a["flags"] = split_notes(a["what"])
        a["kscore"], a["kwhy"] = weigh(a["what"], by_eid.get(a["id"], {}))
        a["kind"], a["kind_why"], fk = action_kind(a["what"], dec_by_id.get(a["id"], []))
        if fk:
            a["follow_of"] = fk
        k = KEEPS.get(a["key"]) or {}
        age = a["age"]
        if k.get("last"):
            try:
                age = min(age, (today_ - date.fromisoformat(k["last"])).days)
            except ValueError:
                pass
        a["keeps"] = int(k.get("count", 0))
        a["pinned"] = a["keeps"] >= 2
        a["tier"] = "fresh" if (a["pinned"] or age <= 7) else "check" if age <= 21 else "old"
    open_acts.sort(key=lambda a: a["date"], reverse=True)
    open_acts.sort(key=lambda a: rank[a["tier"]])
    by_owner = {}
    for a in open_acts:
        key = a["owner"] or "Unassigned"
        by_owner.setdefault(key, []).append(a)
    owners = sorted(by_owner.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    return {
        "topics": top_topics,
        "people": top_people,
        "open": open_acts,
        "owners": [{"owner": k, "items": v} for k, v in owners],
        "decisions": decisions_all,
        "dgroups": _GROUPS,
        "removed": REMOVED,
        "mimp": meeting_importance(entries, decisions_all),
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
        "hot_topics": _DR.get("hot_topics") or [],
        "spelling": _DR.get("spelling") or [],
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
