#!/usr/bin/env python3
"""Which files may leave this computer, and a leak scan over exactly those files.

  python3 tools/publishable.py list [--library PATH]   files git would publish
  python3 tools/publishable.py scan [--library PATH]   same files, checked for real names

"Publishable" means: not excluded by the library's .gitignore. The scan collects real
names from the PRIVATE data (note frontmatter, config.json, rules/resolutions.json,
ops/curated-checks.json) and fails with exit code 2 if any of them appears in a
publishable file or file name. It also flags e-mail addresses and /Users/ paths.
Nothing is sent anywhere; the result is printed locally. Exit 0 means clean.

tools/scan-allow.txt lists phrases that are known false positives, one per line.
tools/scan-ignore-terms.txt lists ordinary words that appear inside private names
(for example "Next" inside a company name) and must not be checked on their own;
the full names are still checked.
Python standard library plus git. Run it before every push.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)


def library_root(argv):
    for i, a in enumerate(argv):
        if a == "--library" and i + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[i + 1]))
        if a.startswith("--library="):
            return os.path.abspath(os.path.expanduser(a.split("=", 1)[1]))
    return DEFAULT_ROOT


def publishable(root):
    """Files in root that .gitignore does not exclude. Uses a throwaway git dir, so
    nothing is created inside the library."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True)
        out = subprocess.run(
            ["git", "-c", "core.excludesFile=/dev/null", "--git-dir", os.path.join(tmp, ".git"),
             "--work-tree", root, "ls-files", "-o", "--exclude-standard", "-z"],
            capture_output=True, check=True).stdout
    return sorted(p for p in out.decode("utf-8").split("\0") if p)


def _json(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def private_terms(root):
    names = set()
    notes = os.path.join(root, "notes")
    if os.path.isdir(notes):
        for f in os.listdir(notes):
            if not f.endswith(".md"):
                continue
            with open(os.path.join(notes, f), encoding="utf-8", errors="ignore") as fh:
                head = fh.read(4000)
            m = re.match(r"^---\n(.*?)\n---", head, re.S)
            if m:
                names.update(x.strip() for x in re.findall(r"\[\[([^\]]+)\]\]", m.group(1)))
    cfg = _json(root, "config.json") or {}
    names.add(cfg.get("owner") or "")
    names.update(cfg.get("me_aliases") or [])
    for k, v in (cfg.get("aliases") or {}).items():
        names.update([k, v])
    res = _json(root, "rules/resolutions.json") or {}
    for item in (res.get("items") or {}).values():
        for k, v in (item.get("map") or {}).items():
            names.add(k)
            if isinstance(v, dict) and v.get("canonical"):
                names.add(v["canonical"])
    for c in _json(root, "ops/curated-checks.json") or []:
        names.update(c.get("variants") or [])
        for k, v in (c.get("suggest") or {}).items():
            names.update([k, v])
    terms = set()
    for n in names:
        n = n.strip()
        if len(n) >= 4:
            terms.add(n)
        for t in re.split(r"[\s/,.&]+", n):
            if len(t) >= 4 and t.isalpha():
                terms.add(t)
    ignore = {w.lower() for w in _lines("scan-ignore-terms.txt")}
    return {t for t in terms if t.lower() not in ignore}


def _lines(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [l.rstrip("\n") for l in fh if l.strip() and not l.startswith("#")]


def allowed_phrases():
    return _lines("scan-allow.txt")


def scan(root):
    terms = private_terms(root)
    allow = allowed_phrases()
    name_pats = [(t, re.compile(r"\b" + re.escape(t) + r"\b", re.I))
                 for t in sorted(terms, key=len, reverse=True)]
    extra = [("e-mail address", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
             ("local user path", re.compile(r"/Users/[A-Za-z0-9._-]+"))]
    files = publishable(root)
    problems = []
    for rel in files:
        full = os.path.join(root, rel)
        text = ""
        if os.path.getsize(full) <= 3_000_000:
            try:
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                text = ""
        for a in allow:
            text = text.replace(a, " ")
        for t, p in name_pats:
            if p.search(rel):
                problems.append((rel, f"real name in file name: {t}"))
            n = len(p.findall(text))
            if n:
                problems.append((rel, f"real name '{t}' x{n}"))
        for label, p in extra:
            n = len(p.findall(text))
            if n:
                problems.append((rel, f"{label} x{n}"))
    return files, terms, problems


def main():
    cmd = next((a for a in sys.argv[1:] if not a.startswith("-")), "")
    root = library_root(sys.argv[1:])
    if cmd == "list":
        print("\n".join(publishable(root)))
    elif cmd == "scan":
        files, terms, problems = scan(root)
        if problems:
            print(f"STOP: {len(problems)} problem(s) in {len(files)} publishable files:")
            for rel, why in problems:
                print(f"  {rel}: {why}")
            print("Fix the file, or add a harmless phrase to tools/scan-allow.txt. Do not push.")
            sys.exit(2)
        print(f"OK: {len(files)} publishable files checked against {len(terms)} private names.")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
