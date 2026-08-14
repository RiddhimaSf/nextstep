"""
evals/drift.py — drift detection between two eval runs.

Compares a baseline result JSON against a latest result JSON and
produces a list of alerts and a summary table. Used by the CI gate
to detect regressions across model, prompt, or data changes.

Usage:
    python -m evals.drift evals/results/baseline.json evals/results/latest.json

Exit codes:
    0 = no drift detected
    1 = drift detected (alerts present)
    2 = runner error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DRIFT_RULES = {
    "pass_rate_drop": 0.03,       # flag if pass rate drops more than 3 points
    "p0_pass_rate_drop": 0.0,     # any P0 regression is a flag
    "faithfulness_drop": 0.3,     # flag if mean faithfulness drops more than 0.3
    "citation_rate_drop": 0.05,   # flag if citation rate drops more than 5 points
}


def load_result(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def compute_citation_rate(result: dict) -> float:
    """Fraction of non-escalation cases where at least one citation appeared."""
    cases = result.get("case_results", [])
    eligible = [c for c in cases if c.get("tool_match", 0) > 0]
    if not eligible:
        return 1.0
    cited = sum(1 for c in eligible if c.get("citation_ok", False))
    return cited / len(eligible)


def compare(baseline: dict, latest: dict) -> tuple[list[str], dict]:
    """
    Compare baseline vs latest run.
    Returns (alerts, summary_table).
    """
    alerts = []
    b = baseline["metrics"]
    l = latest["metrics"]

    b_citation = compute_citation_rate(baseline)
    l_citation = compute_citation_rate(latest)

    # Gate 1: overall pass rate drop
    drop = b["pass_rate"] - l["pass_rate"]
    if drop > DRIFT_RULES["pass_rate_drop"]:
        alerts.append(
            f"DRIFT pass_rate: {b['pass_rate']:.3f} → {l['pass_rate']:.3f} "
            f"(drop: {drop:.3f}, threshold: {DRIFT_RULES['pass_rate_drop']})"
        )

    # Gate 2: P0 regression
    p0_drop = b["p0_pass_rate"] - l["p0_pass_rate"]
    if p0_drop > DRIFT_RULES["p0_pass_rate_drop"]:
        # Find which P0 cases regressed
        b_passing = {c["id"] for c in baseline["case_results"] if c["pass"]}
        l_failing = {c["id"] for c in latest["case_results"] if not c["pass"]}
        regressions = b_passing & l_failing
        alerts.append(
            f"DRIFT P0 regression: {regressions}"
        )

    # Gate 3: faithfulness drop
    if b.get("mean_faithfulness") and l.get("mean_faithfulness"):
        f_drop = b["mean_faithfulness"] - l["mean_faithfulness"]
        if f_drop > DRIFT_RULES["faithfulness_drop"]:
            alerts.append(
                f"DRIFT mean_faithfulness: {b['mean_faithfulness']:.2f} → "
                f"{l['mean_faithfulness']:.2f} (drop: {f_drop:.2f})"
            )

    # Gate 4: citation rate drop
    c_drop = b_citation - l_citation
    if c_drop > DRIFT_RULES["citation_rate_drop"]:
        alerts.append(
            f"DRIFT citation_rate: {b_citation:.3f} → {l_citation:.3f} "
            f"(drop: {c_drop:.3f})"
        )

    # Gate 5: new failure modes
    b_modes = set(baseline.get("failure_modes", {}).keys())
    l_modes = set(latest.get("failure_modes", {}).keys())
    new_modes = l_modes - b_modes
    if new_modes:
        alerts.append(f"DRIFT new failure modes appeared: {new_modes}")

    # Build summary table
    summary = {
        "baseline_timestamp": baseline.get("timestamp"),
        "latest_timestamp": latest.get("timestamp"),
        "metrics": {
            "pass_rate":         {"baseline": b["pass_rate"],        "latest": l["pass_rate"],        "delta": l["pass_rate"] - b["pass_rate"]},
            "p0_pass_rate":      {"baseline": b["p0_pass_rate"],     "latest": l["p0_pass_rate"],     "delta": l["p0_pass_rate"] - b["p0_pass_rate"]},
            "mean_faithfulness": {"baseline": b.get("mean_faithfulness"), "latest": l.get("mean_faithfulness"), "delta": (l.get("mean_faithfulness") or 0) - (b.get("mean_faithfulness") or 0)},
            "citation_rate":     {"baseline": b_citation,            "latest": l_citation,            "delta": l_citation - b_citation},
        },
        "failure_modes": {
            "baseline": baseline.get("failure_modes", {}),
            "latest":   latest.get("failure_modes", {}),
            "new":      list(new_modes),
            "resolved": list(b_modes - l_modes),
        },
        "alerts": alerts,
        "drift_detected": len(alerts) > 0,
    }

    return alerts, summary


def print_report(summary: dict) -> None:
    print("\n=== Drift Report ===")
    print(f"Baseline: {summary['baseline_timestamp']}")
    print(f"Latest:   {summary['latest_timestamp']}")
    print()
    print(f"{'Metric':<20} {'Baseline':>10} {'Latest':>10} {'Δ':>8}")
    print("-" * 52)
    for metric, values in summary["metrics"].items():
        b = values["baseline"]
        l = values["latest"]
        d = values["delta"]
        b_str = f"{b:.3f}" if b is not None else "N/A"
        l_str = f"{l:.3f}" if l is not None else "N/A"
        d_str = f"{d:+.3f}" if d is not None else "N/A"
        flag = " ⚠" if d is not None and d < -DRIFT_RULES.get(f"{metric}_drop", 0.03) else ""
        print(f"{metric:<20} {b_str:>10} {l_str:>10} {d_str:>8}{flag}")

    print()
    b_modes = summary["failure_modes"]["baseline"]
    l_modes = summary["failure_modes"]["latest"]
    all_modes = sorted(set(list(b_modes.keys()) + list(l_modes.keys())))
    if all_modes:
        print(f"{'Failure Mode':<25} {'Baseline':>10} {'Latest':>10}")
        print("-" * 47)
        for mode in all_modes:
            b_count = len(b_modes.get(mode, []))
            l_count = len(l_modes.get(mode, []))
            flag = " NEW" if mode in summary["failure_modes"]["new"] else ""
            resolved = " RESOLVED" if mode in summary["failure_modes"]["resolved"] else ""
            print(f"{mode:<25} {b_count:>10} {l_count:>10}{flag}{resolved}")

    print()
    if summary["alerts"]:
        print("⚠ DRIFT DETECTED:")
        for alert in summary["alerts"]:
            print(f"  {alert}")
    else:
        print("✓ NO DRIFT DETECTED")


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("baseline", help="Path to baseline result JSON")
        parser.add_argument("latest", help="Path to latest result JSON")
        parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
        args = parser.parse_args()

        baseline = load_result(args.baseline)
        latest = load_result(args.latest)

        alerts, summary = compare(baseline, latest)

        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print_report(summary)

        raise SystemExit(0 if not alerts else 1)

    except SystemExit:
        raise
    except Exception as e:
        print(f"\nDRIFT RUNNER ERROR: {e}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()