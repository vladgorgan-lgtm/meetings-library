#!/usr/bin/env python3
"""Insights layer plumbing: which notes need analysis, and how results merge.

The analysis itself (reading a note, proposing decisions Granola missed) is done
by Claude inside the sync run. This file is the deterministic part around it:

  python3 engine/insights.py status          # notes that need (re)analysis
  python3 engine/insights.py status --json
  python3 engine/insights.py validate        # check data/insights/*.json shape

A note needs analysis when it has no insight yet, the note text changed since
the last analysis, or the rules (rules/decisions.md + settings.json) changed.
Quiet days therefore cost nothing. Insights live in data/insights/<note-id>.json:

  {"id", "note_hash", "rules_hash", "analyzed_at",
   "decisions": [{"text", "importance": 1-3, "evidence"}]}
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libroot import library_root  # noqa: E402

ROOT = library_root()
SETTINGS_DEFAULT = {"enabled": False, "max_added_per_meeting": 3,
                    "min_importance": 2, "dedupe_overlap": 0.5}


def use_library(path):
    global ROOT
    ROOT = path


def _sha(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def settings():
    p = os.path.join(ROOT, "rules", "settings.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return {**SETTINGS_DEFAULT, **json.load(fh)}
    except (OSError, ValueError):
        return dict(SETTINGS_DEFAULT)


def rules_hash():
    """Changes whenever the rules text or any tuning number changes (not 'enabled')."""
    parts = []
    try:
        with open(os.path.join(ROOT, "rules", "decisions.md"), encoding="utf-8") as fh:
            parts.append(fh.read())
    except OSError:
        parts.append("")
    s = {k: v for k, v in settings().items() if k != "enabled"}
    parts.append(json.dumps(s, sort_keys=True))
    return _sha("\n".join(parts))


def note_hash(note_id):
    with open(os.path.join(ROOT, "notes", note_id + ".md"), encoding="utf-8") as fh:
        return _sha(fh.read())


def load_insights():
    out, d = {}, os.path.join(ROOT, "data", "insights")
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            try:
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    out[name[:-5]] = json.load(fh)
            except (OSError, ValueError):
                pass
    return out


def note_ids():
    d = os.path.join(ROOT, "notes")
    return [n[:-3] for n in sorted(os.listdir(d)) if n.endswith(".md")] if os.path.isdir(d) else []


def needs_analysis():
    """[(note_id, reason)]. Empty when the layer is disabled."""
    if not settings()["enabled"]:
        return []
    have, rh, todo = load_insights(), rules_hash(), []
    for nid in note_ids():
        ins = have.get(nid)
        if not ins:
            todo.append((nid, "new"))
        elif ins.get("note_hash") != note_hash(nid):
            todo.append((nid, "note changed"))
        elif ins.get("rules_hash") != rh:
            todo.append((nid, "rules changed"))
    return todo


_WORD = re.compile(r"[a-z0-9]+")


def _tokens(s):
    return {w for w in _WORD.findall(s.lower()) if len(w) > 2}


def overlap(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0


def merge_into(decisions, entries):
    """Append the layer's decisions to the dashboard list. Granola's are never
    trimmed or reordered; a layer decision that restates one of them is dropped."""
    cfg = settings()
    if not cfg["enabled"]:
        return decisions
    ins = load_insights()
    for e in entries:
        sens = bool(e.get("sensitive")) or "sensitive" in e.get("tags", [])   # the page hides these behind a toggle
        mine = ins.get(e["id"], {}).get("decisions", [])
        known = list(e["decisions"])
        added = 0
        for d in sorted(mine, key=lambda x: -int(x.get("importance", 0))):
            text, imp = str(d.get("text", "")).strip(), int(d.get("importance", 0))
            if (not text or imp < cfg["min_importance"]
                    or added >= cfg["max_added_per_meeting"]
                    or any(overlap(text, k) >= cfg["dedupe_overlap"] for k in known)):
                continue
            known.append(text)
            added += 1
            decisions.append({"text": text, "id": e["id"], "title": e["title"],
                              "day": e["day"], "date": e["date"],
                              "source": "claude", "importance": imp, "sensitive": sens,
                              "evidence": str(d.get("evidence", ""))})
    return decisions


def dkey(d):
    """Stable identity of a decision; the page uses the same string for hiding."""
    return d["id"] + "|" + d["text"]


def decisions_hash(decisions):
    return _sha("\n".join(sorted(dkey(d) for d in decisions)))


def load_groups():
    try:
        with open(os.path.join(ROOT, "data", "groups.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def resolve_groups(decisions):
    """Turn data/groups.json (written by the grouping step) into dashboard groups.
    A member is a list of keys: more than one means the same decision recorded in
    several meetings, shown once with all its sources. Keys that no longer exist
    are skipped, so a stale file degrades to fewer groups, never an error."""
    by = {dkey(d): d for d in decisions}
    out = []
    for g in load_groups().get("groups", []):
        items = []
        for member in g.get("members", []):
            ds = [by[k] for k in member if k in by]
            if not ds:
                continue
            items.append({"text": ds[0]["text"], "keys": [dkey(d) for d in ds],
                          "sources": [{"id": d["id"], "title": d["title"], "day": d["day"]} for d in ds],
                          "source": ds[0].get("source", "granola"),
                          "importance": max(int(d.get("importance", 0)) for d in ds),
                          "sensitive": all(d.get("sensitive") for d in ds),
                          "evidence": ds[0].get("evidence", "")})
        if not items:
            continue
        date = max(d["date"] for d in decisions if dkey(d) in {k for i in items for k in i["keys"]})
        out.append({"title": g["title"], "digest": g.get("digest", ""), "note": g.get("note", ""),
                    "date": date, "key": any(i["importance"] >= 3 for i in items), "items": items})
    return out


def grouping_stale(decisions):
    g = load_groups()
    return (not g) or g.get("decisions_hash") != decisions_hash(decisions)


def validate():
    bad = []
    for nid, ins in load_insights().items():
        if nid not in note_ids():
            bad.append(f"{nid}: no matching note")
        for i, d in enumerate(ins.get("decisions", [])):
            if not str(d.get("text", "")).strip():
                bad.append(f"{nid}[{i}]: empty text")
            if int(d.get("importance", 0)) not in (1, 2, 3):
                bad.append(f"{nid}[{i}]: importance must be 1-3")
            if not str(d.get("evidence", "")).strip():
                bad.append(f"{nid}[{i}]: missing evidence quote")
    return bad


if __name__ == "__main__":
    cmd = next((a for a in sys.argv[1:] if not a.startswith("-")), "status")
    if cmd == "validate":
        problems = validate()
        print("\n".join(problems) or "ok")
        sys.exit(1 if problems else 0)
    todo = needs_analysis()
    if "--json" in sys.argv:
        print(json.dumps([{"id": i, "reason": r} for i, r in todo]))
    elif not settings()["enabled"]:
        print("insights layer disabled (rules/settings.json: enabled=false)")
    else:
        print(f"{len(todo)} note(s) need analysis, rules {rules_hash()}")
        for i, r in todo:
            print(f"  {i}  ({r})")
