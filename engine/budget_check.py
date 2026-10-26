#!/usr/bin/env python3
"""
Gate the meeting-library sync on a monthly spend cap.

Reads the same log and the same cost model as engine/cost_report.py, adds up the
CURRENT calendar month, and compares it to `monthly_budget_usd` in ops/rates.json.

  python3 engine/budget_check.py           # human-readable, for a person or a skill
  python3 engine/budget_check.py --json    # machine-readable
  python3 engine/budget_check.py --month 2026-11

Exit codes, so a caller can branch without parsing anything:

  0  under the cap  — proceed with the sync
  2  at or over     — do not fetch; report instead
  1  the check itself failed (missing rates, unreadable log)

Exit 1 means UNKNOWN, not OK. A caller that cannot run this check should say so
rather than sync anyway — a broken gate that silently passes is worse than no gate.

This caps an ESTIMATE. Scheduled runs draw on the Claude plan, not API billing,
so crossing the cap does not mean money left an account. It is a runaway guard:
the number it protects against is a sync looping on a bug, not a invoice.
"""

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COST_REPORT = os.path.join(HERE, "cost_report.py")
sys.path.insert(0, HERE)
from libroot import library_root  # noqa: E402

OK, OVER, FAILED = 0, 2, 1


def load_cost_report():
    """Import cost_report so the cost model can never drift between the two."""
    spec = importlib.util.spec_from_file_location("cost_report", COST_REPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.use_library(library_root())
    return mod


def evaluate(month=None):
    """Return a dict describing the month's spend against the cap."""
    cr = load_cost_report()
    rates, runs = cr.load_rates(), cr.load_runs()

    month = month or dt.date.today().strftime("%Y-%m")
    cap = float(rates.get("monthly_budget_usd", 0) or 0)

    spent, counted = 0.0, 0
    for run in runs:
        if str(run.get("ts", ""))[:7] != month:
            continue
        spent += cr.cost_of(run, rates)[2]
        counted += 1

    enabled = cap > 0
    over = enabled and spent >= cap
    remaining = max(0.0, cap - spent) if enabled else None
    per_run = (spent / counted) if counted else 0.0

    # How many more runs fit, at this month's average run cost.
    if enabled and per_run > 0:
        runs_left = int(remaining // per_run)
    else:
        runs_left = None

    return {
        "month": month,
        "cap_usd": round(cap, 2),
        "cap_enabled": enabled,
        "spent_usd": round(spent, 4),
        "remaining_usd": round(remaining, 4) if remaining is not None else None,
        "used_fraction": round(spent / cap, 4) if enabled else None,
        "runs": counted,
        "per_run_usd": round(per_run, 4),
        "runs_remaining_at_this_rate": runs_left,
        "over_budget": over,
        "verdict": "over" if over else ("disabled" if not enabled else "ok"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM; default is the current calendar month")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    ap.add_argument("--library", help="library root (default: folder above engine/)")
    args = ap.parse_args()

    try:
        s = evaluate(args.month)
    except Exception as exc:
        msg = f"budget check FAILED: {exc}"
        print(json.dumps({"error": str(exc), "verdict": "unknown"}) if args.as_json
              else f"  {msg}\n  Treat this as unknown, not as permission to sync.",
              file=sys.stderr)
        return FAILED

    if args.as_json:
        print(json.dumps(s, indent=2))
        return OVER if s["over_budget"] else OK

    if args.quiet:
        return OVER if s["over_budget"] else OK

    if not s["cap_enabled"]:
        print(f"\n  No monthly cap set (monthly_budget_usd is 0). "
              f"{s['month']}: ${s['spent_usd']:.2f} estimated so far.\n")
        return OK

    bar_w = 28
    filled = min(bar_w, int(round(s["used_fraction"] * bar_w))) if s["used_fraction"] else 0
    bar = "#" * filled + "." * (bar_w - filled)

    plural = "" if s["runs"] == 1 else "s"
    per_run = f" (${s['per_run_usd']:.2f} per run)" if s["runs"] else ""

    print(f"\n  Meeting library — budget check for {s['month']}\n")
    print(f"  [{bar}] {s['used_fraction']:.0%} of ${s['cap_usd']:.2f}")
    print(f"  spent ${s['spent_usd']:.2f} est. across {s['runs']} run{plural}{per_run}")

    if s["over_budget"]:
        print(f"\n  OVER BUDGET — ${s['spent_usd']:.2f} of ${s['cap_usd']:.2f}.")
        print("  Do not fetch. Report the state and let the owner decide.")
        print(f"  The cap clears on its own when {s['month']} rolls over.\n")
        return OVER

    print(f"  ${s['remaining_usd']:.2f} left"
          + (f" — about {s['runs_remaining_at_this_rate']} more runs at this month's rate."
             if s["runs_remaining_at_this_rate"] is not None else "."))
    print("\n  Under the cap. Safe to sync.")
    print("  (Estimate from ops/rates.json in the library, not a bill — scheduled runs draw on the Claude plan.)\n")
    return OK


if __name__ == "__main__":
    sys.exit(main())
