#!/usr/bin/env python3
"""Local server for the Meeting Library: lets the page save settings and answers.

  python3 engine/serve.py [--port 8765] [--no-open]

Binds to 127.0.0.1 only. Writes only a short whitelist of files (settings, your
answers, the manual-add queue, sensitive overrides), each backed up first. It
never touches notes/. Stop it with Ctrl+C or by closing the terminal window.
Python standard library only.
"""
import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libroot import ENGINE, library_root  # noqa: E402
import review  # noqa: E402

ROOT = library_root()
review.use_library(ROOT)
TOKEN = secrets.token_urlsafe(24)
PORT = 8765
LOCK = threading.Lock()
STATIC_DIRS = ("ui", "data", "notes")
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json", ".md": "text/markdown; charset=utf-8",
        ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}
ROUTINES_URL = "https://api.anthropic.com/v1/claude_code/routines/{id}/fire"
FALLBACK_URL = "https://claude.ai/code/routines"


def p(rel):
    return os.path.join(ROOT, rel)


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(rel, default):
    try:
        with open(p(rel), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def backup(rel):
    src = p(rel)
    if not os.path.exists(src):
        return
    d = p("ops/backups/settings")
    os.makedirs(d, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(src, os.path.join(d, f"{rel.replace('/', '__')}.{stamp}.bak"))
    mine = sorted(f for f in os.listdir(d) if f.startswith(rel.replace('/', '__') + "."))
    for old in mine[:-20]:
        os.remove(os.path.join(d, old))


def write_json(rel, obj):
    backup(rel)
    os.makedirs(os.path.dirname(p(rel)), exist_ok=True)
    tmp = p(rel) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, p(rel))


def log(action, detail=""):
    os.makedirs(p("ops"), exist_ok=True)
    with open(p("ops/settings-log.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now(), "action": action, "detail": detail}, ensure_ascii=False) + "\n")


def rebuild():
    r = subprocess.run([sys.executable, os.path.join(ENGINE, "build_index.py"), "--library", ROOT],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]


def num(v, lo, hi, name):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return v


def flag(v):
    return bool(v)


# ---------------------------------------------------------------- actions

def save_settings(b):
    changed = []
    if "cap" in b:
        c = b["cap"]
        cap = num(c["monthly_budget_usd"], 0, 1000, "monthly cap")
        warn = num(c["warn_monthly_usd"], 0, 1000, "monthly warning")
        run = num(c["warn_run_usd"], 0, 1000, "per-run warning")
        if warn > cap:
            raise ValueError("the monthly warning cannot be higher than the cap")
        rates = read_json("ops/rates.json", {})
        rates.update(monthly_budget_usd=cap, warn_monthly_usd=warn, warn_run_usd=run)
        write_json("ops/rates.json", rates)
        changed.append("cap")
    cfg = read_json("config.json", {})
    if "granola" in b:
        cfg["granola"] = {"enabled": flag(b["granola"].get("enabled"))}
        changed.append("granola")
    if "gemini" in b:
        g = {**(cfg.get("gemini") or {}), **b["gemini"]}
        cfg["gemini"] = {
            "enabled": flag(g.get("enabled")), "sender": "gemini-notes@google.com",
            "lookback_days": int(num(g.get("lookback_days", 2), 1, 30, "look-back days")),
            "backfill_from": str(g.get("backfill_from", "2026-09-01"))[:10],
            "drive_safety_net": flag(g.get("drive_safety_net")),
            "skip_shortcuts": True,
            "max_doc_kb": int(num(g.get("max_doc_kb", 200), 10, 2000, "max document size")),
        }
        changed.append("gemini")
    if "local_files" in b:
        l = b["local_files"]
        cfg["local_files"] = {"enabled": flag(l.get("enabled")),
                              "max_mb": int(num(l.get("max_mb", 5), 1, 25, "max file size"))}
        changed.append("local_files")
    if "topic_exclude" in b:
        tags = sorted({re.sub(r"[^a-z0-9\-_ ]", "", str(t).lower()).strip() for t in b["topic_exclude"]} - {""})
        cfg["topic_exclude"] = tags[:60]
        changed.append("topic_exclude")
    if "review" in b:
        rv = b["review"]
        cfg["review"] = {"weights": {k: int(num(v, 0, 50, "weight " + k)) for k, v in (rv.get("weights") or {}).items()
                                      if k in ("money", "commitment", "people", "external", "recent", "reach", "granola_prior")},
                         "must_threshold": int(num(rv.get("must_threshold", 45), 0, 100, "must-resolve threshold"))}
        changed.append("review")
    if "sensitive" in b:
        sv = b["sensitive"]
        words = []
        for k in (sv.get("keywords") or []):
            k = re.sub(r"\s+", " ", str(k)).strip().lower()[:60]
            if k and k not in words:
                words.append(k)
        cfg["sensitive"] = {"definition": str(sv.get("definition", "")).strip()[:2000], "keywords": words[:60]}
        pats = []
        for t in (sv.get("title_patterns") or []):
            t = re.sub(r"\s+", " ", str(t)).strip().lower()[:80]
            if t and t not in pats:
                pats.append(t)
        o = read_json("rules/overrides.json", {"add": [], "remove": [], "title_patterns": []})
        o["title_patterns"] = pats[:60]
        write_json("rules/overrides.json", o)
        changed.append("sensitive")
    if any(k in b for k in ("granola", "gemini", "local_files", "topic_exclude", "review", "sensitive")):
        write_json("config.json", cfg)
    # turning a connector off only stops future fetching; notes are never touched
    log("settings", ",".join(changed))
    ok, out = rebuild()
    return {"ok": ok, "changed": changed, "build": out}


def answer(b):
    review.save_resolution(str(b["id"]), b)
    log("answer", str(b["id"]) + " " + b.get("status", "answered"))
    ok, out = rebuild()
    return {"ok": ok, "build": out}


def general(b):
    fields = (b.get("text", ""), b.get("scope", "all"), b.get("scope_value", ""), b.get("weight", 3))
    if b.get("delete"):
        review.delete_general(str(b["delete"]))
    elif b.get("update"):
        review.update_general(str(b["update"]), *fields)
    else:
        review.add_general(*fields)
    log("general-rule", "delete" if b.get("delete") else "update" if b.get("update") else "add")
    ok, out = rebuild()
    return {"ok": ok, "build": out}


def bulk(b):
    ids = [str(i) for i in (b.get("ids") or [])][:200]
    review.bulk_resolve(ids, b.get("status", "ignored"), b.get("response", ""))
    log("bulk", f"{b.get('status', 'ignored')} x{len(ids)}")
    ok, out = rebuild()
    return {"ok": ok, "build": out}


def sensitive(b):
    nid = str(b["id"])
    if not re.fullmatch(r"[a-z0-9\-]+", nid) or not os.path.exists(p(f"notes/{nid}.md")):
        raise ValueError("unknown note")
    o = read_json("rules/overrides.json", {"add": [], "remove": [], "title_patterns": []})
    for k in ("add", "remove"):
        o[k] = [x for x in o.get(k, []) if x != nid]
    o["add" if b.get("value") else "remove"].append(nid)
    write_json("rules/overrides.json", o)
    log("sensitive", f"{nid}={bool(b.get('value'))}")
    ok, out = rebuild()
    return {"ok": ok, "build": out}


def queue_add(b):
    q = read_json("inbox/queue.json", {"items": []})
    kind = b.get("kind")
    item = {"id": "q-" + secrets.token_hex(4), "kind": kind, "added": now(), "status": "pending",
            "hint": str(b.get("hint", ""))[:200], "sensitive": flag(b.get("sensitive"))}
    if kind == "drive":
        link = str(b.get("value", "")).strip()
        if not re.match(r"^https://(docs|drive)\.google\.com/", link):
            raise ValueError("that does not look like a Google Docs or Drive link")
        item["value"] = link[:500]
    elif kind in ("transcript", "file"):
        cap = int(read_json("config.json", {}).get("local_files", {}).get("max_mb", 5)) * 1024 * 1024
        name = re.sub(r"[^A-Za-z0-9._\- ]", "_", str(b.get("name", "pasted-text.txt")))[:80] or "file.txt"
        if kind == "transcript":
            raw = str(b.get("value", "")).encode("utf-8")
            name = "transcript-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".txt"
        else:
            raw = base64.b64decode(b.get("content_b64", ""), validate=True)
        if not raw:
            raise ValueError("nothing to add")
        if len(raw) > cap:
            raise ValueError(f"larger than the {cap // 1048576} MB limit in settings")
        os.makedirs(p("inbox/files"), exist_ok=True)
        stored = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{name}"
        with open(p("inbox/files/" + stored), "wb") as fh:
            fh.write(raw)
        item["value"], item["name"] = "inbox/files/" + stored, name
    else:
        raise ValueError("unknown kind")
    q["items"].append(item)
    write_json("inbox/queue.json", q)
    log("queue-add", f"{kind} {item['id']}")
    ok, out = rebuild()
    return {"ok": ok, "item": item}


def queue_remove(b):
    q = read_json("inbox/queue.json", {"items": []})
    q["items"] = [i for i in q["items"] if i["id"] != b.get("id") or i.get("status") != "pending"]
    write_json("inbox/queue.json", q)
    log("queue-remove", str(b.get("id")))
    rebuild()
    return {"ok": True}


def run_now(_b):
    """Ask Claude to run the scheduled task now. Needs ops/routine.json with the routine id
    and its token (kept on this computer only; never put it in the page or in chat)."""
    cfg = read_json("ops/routine.json", {})
    if not cfg.get("id") or not cfg.get("token"):
        return {"ok": False, "fallback_url": FALLBACK_URL,
                "message": "No routine token saved yet, so the page cannot start the run itself. "
                           "Open the Run now page instead, or add ops/routine.json (see README)."}
    req = urllib.request.Request(
        ROUTINES_URL.format(id=cfg["id"]), method="POST",
        data=json.dumps({"text": "Run the meeting library sync now (started from the settings page)."}).encode(),
        headers={"Authorization": "Bearer " + cfg["token"], "Content-Type": "application/json",
                 "anthropic-version": "2023-06-01",
                 "anthropic-beta": cfg.get("beta", "experimental-cc-routine-2026-04-01")})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")[:300]
        log("run-now", "fired")
        return {"ok": True, "message": "Run started in Claude. New notes appear here when it finishes.", "detail": body}
    except urllib.error.HTTPError as e:
        log("run-now", f"http {e.code}")
        msg = {401: "The routine token was refused. Generate a new one and replace ops/routine.json.",
               429: "Too many runs this hour (limit 30 per routine). Try again later."}.get(e.code, f"Claude answered {e.code}.")
        return {"ok": False, "message": msg, "fallback_url": FALLBACK_URL}
    except Exception as e:  # network down, DNS, timeout
        return {"ok": False, "message": f"Could not reach Claude ({e.__class__.__name__}).", "fallback_url": FALLBACK_URL}


ROUTES = {"/api/settings": save_settings, "/api/answer": answer, "/api/general": general, "/api/bulk": bulk,
          "/api/sensitive": sensitive, "/api/queue/add": queue_add, "/api/queue/remove": queue_remove,
          "/api/run": run_now, "/api/rebuild": lambda b: dict(zip(("ok", "build"), rebuild()))}


class H(BaseHTTPRequestHandler):
    server_version = "MeetingLibrary"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "bad host"})
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            html = open(p("index.html"), encoding="utf-8").read()
            inject = (f'<script>window.ML_SERVER={{token:"{TOKEN}"}};</script>')
            return self._send(200, html.replace("</head>", inject + "</head>", 1), MIME[".html"])
        parts = path.lstrip("/").split("/")
        if parts[0] in STATIC_DIRS and ".." not in parts and len(parts) > 1:
            f = os.path.realpath(p("/".join(parts)))
            if f.startswith(os.path.realpath(ROOT) + os.sep) and os.path.isfile(f):
                ext = os.path.splitext(f)[1].lower()
                return self._send(200, open(f, "rb").read(), MIME.get(ext, "application/octet-stream"))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "bad host"})
        origin = self.headers.get("Origin", "")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self._send(403, {"error": "bad origin"})
        if not secrets.compare_digest(self.headers.get("X-ML-Token", ""), TOKEN):
            return self._send(403, {"error": "bad token; reload the page"})
        fn = ROUTES.get(self.path)
        if not fn:
            return self._send(404, {"error": "unknown action"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 40 * 1024 * 1024:
                return self._send(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            with LOCK:
                out = fn(body)
            self._send(200, out)
        except (ValueError, KeyError) as e:
            self._send(400, {"ok": False, "error": str(e) or "invalid request"})
        except Exception as e:
            self._send(500, {"ok": False, "error": f"{e.__class__.__name__}: {e}"})


def main():
    global PORT
    a = sys.argv[1:]
    if "--port" in a:
        PORT = int(a[a.index("--port") + 1])
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Meeting Library at {url}  (Ctrl+C to stop)")
    if "--no-open" not in a:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
