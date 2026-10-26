#!/usr/bin/env python3
"""
Estimate what the meeting library costs to run, from the sync log.

Each sync run appends one JSON line to ops/sync-log.jsonl. This reads that log,
applies the cost model in ops/rates.json, and prints a per-month breakdown plus
anything that looks like it's running away.

  python3 engine/cost_report.py            # all months
  python3 engine/cost_report.py --month 2026-11
  python3 engine/cost_report.py --json     # machine-readable
  python3 engine/cost_report.py --library kit/sample   # any library

These are ESTIMATES. Scheduled runs draw on the Claude plan, not API billing, so
no invoice exists to reconcile against. The value is the trend and the alerts,
not the absolute number.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libroot import library_root  # noqa: E402

ROOT = library_root()


def use_library(path):
    """Point the cost model at a library root (callers that import this module)."""
    global ROOT
    ROOT = path


def _log():
    return os.path.join(ROOT, "ops", "sync-log.jsonl")


def _rates():
    return os.path.join(ROOT, "ops", "rates.json")


def load_rates():
    with open(_rates(), encoding="utf-8") as fh:
        return json.load(fh)


def load_runs():
    LOG = _log()
    if not os.path.exists(LOG):
        return []
    runs = []
    with open(LOG, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  (skipped malformed log line {n})", file=sys.stderr)
    return runs


def cost_of(run, r):
    """Estimated input/output tokens and USD for one run."""
    inp = (r["base_input_tokens"]
           + run.get("listed", 0) * r["input_tokens_per_meeting_listed"]
           + run.get("fetched", 0) * r["input_tokens_per_meeting_fetched"]
           + run.get("written", 0) * r["input_tokens_per_note_written"])
    out = run.get("written_chars", 0) / r["output_chars_per_token"]
    usd = (inp / 1e6) * r["usd_per_million_input"] + (out / 1e6) * r["usd_per_million_output"]
    return int(inp), int(out), usd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM; default is every month in the log")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--library", help="library root (default: folder above engine/)")
    args = ap.parse_args()

    r, runs = load_rates(), load_runs()
    if not runs:
        print("No runs logged yet — ops/sync-log.jsonl is empty or missing.")
        print("The sync appends to it on each run; the first report needs at least one.")
        return

    months, alerts = defaultdict(lambda: {
        "runs": 0, "listed": 0, "fetched": 0, "written": 0,
        "refreshed": 0, "new": 0, "input": 0, "output": 0, "usd": 0.0,
        "empty_runs": 0}, ), []

    for run in runs:
        key = str(run.get("ts", ""))[:7] or "unknown"
        if args.month and key != args.month:
            continue
        inp, out, usd = cost_of(run, r)
        m = months[key]
        m["runs"] += 1
        for f in ("listed", "fetched", "written", "refreshed", "new"):
            m[f] += run.get(f, 0)
        m["input"] += inp
        m["output"] += out
        m["usd"] += usd
        if not run.get("written"):
            m["empty_runs"] += 1

        total = run.get("notes_total") or 0
        if (total and not run.get("backfill")
                and run.get("written", 0) / total > r["warn_rewrite_ratio"]):
            alerts.append(f"{run.get('ts', '?')}: rewrote {run['written']} of {total} notes "
                          f"— that's a rewrite-everything pattern, usually a bug in the "
                          f"updated_at comparison rather than real activity.")
        if usd > r["warn_run_usd"]:
            alerts.append(f"{run.get('ts', '?')}: single run estimated at ${usd:.2f}, "
                          f"over the ${r['warn_run_usd']:.2f} per-run threshold.")

    if args.as_json:
        print(json.dumps({"months": months, "alerts": alerts}, indent=2, default=float))
        return

    print(f"\n  Meeting library — estimated run cost ({r['model']}, "
          f"${r['usd_per_million_input']:.0f}/M in, ${r['usd_per_million_output']:.0f}/M out)\n")
    print(f"  {'month':<9} {'runs':>5} {'new':>5} {'refr':>5} {'quiet':>6} "
          f"{'tokens':>10} {'est. USD':>9}")
    print("  " + "-" * 54)

    grand = 0.0
    for key in sorted(months):
        m = months[key]
        grand += m["usd"]
        print(f"  {key:<9} {m['runs']:>5} {m['new']:>5} {m['refreshed']:>5} "
              f"{m['empty_runs']:>6} {m['input'] + m['output']:>10,} {m['usd']:>8.2f}")

    print("  " + "-" * 54)
    print(f"  {'total':<9} {'':>5} {'':>5} {'':>5} {'':>6} {'':>10} {grand:>8.2f}\n")

    last = sorted(months)[-1]
    m = months[last]
    if m["runs"]:
        per = m["usd"] / m["runs"]
        print(f"  {last}: ${per:.2f} per run across {m['runs']} runs.")
        if m["empty_runs"]:
            share = m["empty_runs"] / m["runs"]
            print(f"  {m['empty_runs']} of {m['runs']} runs ({share:.0%}) found nothing new "
                  f"— roughly ${m['empty_runs'] * per:.2f} spent confirming no change.")
            if share > 0.5:
                print("  More than half the runs were empty. A less frequent schedule would "
                      "cost less for the same coverage.")
        if m["usd"] > r["warn_monthly_usd"]:
            alerts.append(f"{last}: ${m['usd']:.2f} is over the "
                          f"${r['warn_monthly_usd']:.2f} monthly threshold.")

    if alerts:
        print("\n  ALERTS")
        for a in alerts:
            print(f"   ! {a}")
    else:
        print("\n  No alerts. Nothing is running away.")
    print()


if __name__ == "__main__":
    main()
