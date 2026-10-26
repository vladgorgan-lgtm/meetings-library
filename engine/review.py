#!/usr/bin/env python3
"""Needs-review checks, and the rules built from your answers to them.

  ops/review.json          the checks (one item per problem). Written by `seed` and by
                           the sync / middle layer when it finds something unclear.
  rules/resolutions.json   your answers, written by the settings page.
  rules/resolutions.md     the same answers as plain rules (generated, never edit). The
                           middle layer reads this when it parses or enhances notes.

  python3 engine/review.py seed      # (re)build ops/review.json from the notes
  python3 engine/review.py status    # open / answered counts

Item:  {"id", "kind": names|term|inconsistency|held|unclear|empty, "title", "detail",
        "variants": [...], "suggest": {variant: canonical}, "notes": [note ids],
        "origin": curated|auto|middle-layer}
Answer: rules/resolutions.json  {"items": {id: {"response", "map": {variant:
        {"canonical", "not_person"}}, "status": answered|ignored, "ts"}},
        "general": [{"id", "text", "ts"}]}

The deterministic part of an answer (variant -> canonical name, not-a-person) is applied
by build_index.py at build time, so it costs nothing and never edits a note. The free
text is for the middle layer.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libroot import library_root  # noqa: E402

ROOT = library_root()


def use_library(path):
    global ROOT
    ROOT = path


def _read(rel, default):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(rel, obj):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, p)


def _id(*parts):
    return "c-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8]


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------------------------------------------ store

def load_items():
    return _read("ops/review.json", {}).get("items", [])


def load_resolutions():
    r = _read("rules/resolutions.json", {})
    r.setdefault("items", {})
    r.setdefault("general", [])
    return r


def save_resolution(item_id, payload):
    """payload: {response, map, status}. Raises KeyError for an unknown check."""
    if item_id not in {i["id"] for i in load_items()}:
        raise KeyError(item_id)
    r = load_resolutions()
    status = payload.get("status", "answered")
    if status not in ("answered", "ignored", "open"):
        raise ValueError("status")
    if status == "open":                      # reopen: forget the answer
        r["items"].pop(item_id, None)
    else:
        m = {}
        for variant, v in (payload.get("map") or {}).items():
            canonical = str(v.get("canonical", "")).strip()[:120]
            not_person = bool(v.get("not_person"))
            if canonical or not_person:
                m[str(variant).strip()[:120]] = {"canonical": canonical, "not_person": not_person}
        r["items"][item_id] = {"response": str(payload.get("response", "")).strip()[:4000],
                               "map": m, "status": status, "ts": now()}
    _write("rules/resolutions.json", r)
    write_rules_md()
    return r


def add_general(text):
    text = str(text).strip()[:2000]
    if not text:
        raise ValueError("empty")
    r = load_resolutions()
    r["general"].append({"id": "g-" + hashlib.sha1((text + now()).encode()).hexdigest()[:8],
                         "text": text, "ts": now()})
    _write("rules/resolutions.json", r)
    write_rules_md()
    return r


def delete_general(gid):
    r = load_resolutions()
    r["general"] = [g for g in r["general"] if g["id"] != gid]
    _write("rules/resolutions.json", r)
    write_rules_md()
    return r


# ------------------------------------------------------------------ build

def build(entries):
    """Items joined with answers, for window.LIBRARY.review."""
    byid = {e["id"]: e for e in entries}
    r = load_resolutions()
    out, open_n, done_n = [], 0, 0
    for it in load_items():
        res = r["items"].get(it["id"])
        status = res.get("status", "answered") if res else "open"
        if status == "open":
            open_n += 1
        else:
            done_n += 1
        refs = [{"id": n, "title": byid[n]["title"], "day": byid[n]["day"],
                 "sensitive": byid[n].get("sensitive", False)}
                for n in it.get("notes", []) if n in byid]
        out.append({**it, "refs": refs, "status": status, "resolution": res})
    return {"items": out, "general": r["general"], "open": open_n, "answered": done_n}


def write_rules_md():
    r, items = load_resolutions(), {i["id"]: i for i in load_items()}
    names, notes = [], []
    for iid, res in r["items"].items():
        it = items.get(iid)
        if not it or res.get("status") != "answered":
            continue
        for variant, m in res.get("map", {}).items():
            if m.get("not_person"):
                names.append(f'- "{variant}" is not a person (company, project, tool or garbled word)'
                             + (f'; call it "{m["canonical"]}"' if m.get("canonical") else ""))
            elif m.get("canonical"):
                kind = "term" if it["kind"] == "term" else "person"
                names.append(f'- "{variant}" means "{m["canonical"]}" ({kind})')
        if res.get("response"):
            where = ", ".join(it.get("notes", [])[:6])
            notes.append(f'- [{it["kind"]}] {it["title"]}: {res["response"]}'
                         + (f"  (notes: {where})" if where else ""))
    lines = ["# Rules from your responses",
             "",
             "Generated from rules/resolutions.json by the settings page. Do not edit by hand.",
             "The middle layer reads this when it parses or enhances notes: apply these before",
             "guessing, and spell names the way they are written here.",
             "", "## Names and terms", ""]
    lines += names or ["(none yet)"]
    lines += ["", "## Your answers to specific checks", ""] + (notes or ["(none yet)"])
    lines += ["", "## General rules", ""] + (
        [f"- {g['text']}" for g in r["general"]] or ["(none yet)"])
    p = os.path.join(ROOT, "rules", "resolutions.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ------------------------------------------------------------------ seed

def load_curated():
    """Library-specific checks (names to verify, terms to map). These come from
    the owner's own notes, so they live in the library at ops/curated-checks.json
    (private, never in the engine). Shape: see templates/curated-checks.example.json."""
    data = _read("ops/curated-checks.json", [])
    return data if isinstance(data, list) else []


SECTION = re.compile(r"^##\s+(Source check|Gemini cross-check)\s*$", re.M)
KEEP = re.compile(r"^(inconsistency|differs|held for review|unclear|ambiguous|garbled|quick notes|"
                  r"attribution|grace period|amounts are|\"performance contract\")", re.I)


def _front(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).split("\n"):
            if ":" in line and not line.startswith((" ", "\t")):
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"')
    return fm


def _bullets(section):
    out, cur = [], None
    for line in section.split("\n"):
        if re.match(r"^- ", line):
            cur = [line[2:].strip()]
            out.append(cur)
        elif cur is not None and re.match(r"^\s{2,}\S", line):
            cur.append(line.strip().lstrip("- ").strip())
    return [" ".join(b) for b in out]


def seed(write=True):
    notes_dir = os.path.join(ROOT, "notes")
    have = {n[:-3] for n in os.listdir(notes_dir) if n.endswith(".md")} if os.path.isdir(notes_dir) else set()
    old = _read("ops/review.json", {}).get("items", [])
    keep_other = [i for i in old if i.get("origin") not in ("auto", "curated")]
    items = []
    for c in load_curated():
        notes = [n for n in c["notes"] if n in have]
        if not notes:
            continue
        it = {"id": _id(c["kind"], c["title"]), "origin": "curated", **c, "notes": notes}
        items.append(it)
    for nid in sorted(have):
        with open(os.path.join(notes_dir, nid + ".md"), encoding="utf-8") as fh:
            text = fh.read()
        fm = _front(text)
        title, date = fm.get("title", nid), fm.get("date", "")
        if fm.get("source") == "gemini" and re.search(r"^tags:.*\bno-summary\b", text, re.M):
            items.append({"id": _id("empty", nid), "origin": "auto", "kind": "empty",
                          "title": f"No content captured: {title} ({date})", "notes": [nid],
                          "detail": "Gemini produced no summary for this meeting. Say what it was about, "
                                    "or mark it as not needed."})
        for m in SECTION.finditer(text):
            rest = text[m.end():]
            nxt = re.search(r"^##\s+", rest, re.M)
            body = rest[:nxt.start()] if nxt else rest
            for b in _bullets(body):
                plain = re.sub(r"\*\*", "", b).strip()
                if not KEEP.match(plain):
                    continue
                low = plain.lower()
                kind = ("held" if low.startswith("held") else
                        "inconsistency" if low.startswith(("inconsistency", "differs", "attribution", "quick notes"))
                        else "unclear")
                label = f"{title} ({date})"
                short = plain if len(plain) <= 110 else plain[:107].rstrip() + "..."
                items.append({"id": _id(kind, nid, plain[:80]), "origin": "auto", "kind": kind,
                              "title": short, "detail": plain, "notes": [nid], "where": label})
    seen, merged = set(), []
    for it in items + keep_other:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        merged.append(it)
    if write:
        _write("ops/review.json", {"generated": now(), "items": merged})
    return merged


if __name__ == "__main__":
    cmd = next((a for a in sys.argv[1:] if not a.startswith("-")), "status")
    if cmd == "seed":
        its = seed()
        kinds = {}
        for i in its:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        print(f"Wrote ops/review.json: {len(its)} checks {kinds}")
        write_rules_md()
    else:
        its, r = load_items(), load_resolutions()
        done = sum(1 for i in its if i["id"] in r["items"])
        print(f"{len(its)} checks, {done} answered, {len(its) - done} open, "
              f"{len(r['general'])} general rules")
