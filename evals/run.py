"""
evals/run.py — one-command regression suite for NextStep.

Usage:
    python -m evals.run                    # full suite, no LLM judge
    python -m evals.run --llm-judge        # include faithfulness scoring
    python -m evals.run --severity P0      # P0 cases only

Exit codes:
    0 = all gates passed
    1 = one or more gates failed

This is the file CI runs. The same file a human runs locally.
Same command, same output, same exit code — no special CI mode.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.run_evals_v2 import load_cases, run_agent, score_case
from evals.schema import GoldenCase, CaseScore

GATES_PATH = Path("evals/gates.yaml")
RESULTS_DIR = Path("evals/results")


def load_gates() -> dict:
    with open(GATES_PATH) as f:
        return yaml.safe_load(f)


def summarize(scores: list[CaseScore], cases: list[GoldenCase], elapsed: float) -> dict:
    total = len(scores)
    passed = sum(1 for s in scores if s.pass_)

    p0_cases = {c.id for c in cases if c.severity == "P0"}
    p0_scores = [s for s in scores if s.id in p0_cases]
    p0_passed = sum(1 for s in p0_scores if s.pass_)

    faithfulness_scores = [s.faithfulness for s in scores if s.faithfulness is not None]
    mean_faithfulness = statistics.mean(faithfulness_scores) if faithfulness_scores else None

    latencies = []  # placeholder — real latency tracking added in Day 9
    p95_latency = None

    failure_modes: dict[str, list[str]] = {}
    for s in scores:
        if not s.pass_ and s.failure_mode:
            failure_modes.setdefault(s.failure_mode, []).append(s.id)

    return {
        "timestamp": int(time.time()),
        "elapsed_seconds": round(elapsed, 1),
        "metrics": {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "p0_total": len(p0_scores),
            "p0_passed": p0_passed,
            "p0_pass_rate": round(p0_passed / len(p0_scores), 3) if p0_scores else 1.0,
            "mean_faithfulness": round(mean_faithfulness, 2) if mean_faithfulness else None,
            "p95_latency_ms": p95_latency,
        },
        "failure_modes": failure_modes,
        "case_results": [s.model_dump(by_alias=True) for s in scores],
    }


def check_gates(report: dict, gates: dict) -> tuple[bool, list[str]]:
    """
    Check all gates against the report metrics.
    Returns (passed, list_of_failure_messages).

    Known gaps are excluded from the P0 gate check only if they have
    all three required fields: id, reason, owner, review_date.
    A carve-out missing any field is treated as a blocking failure.
    """
    metrics = report["metrics"]
    failure_modes = report.get("failure_modes", {})
    msgs = []

    # Load known gaps — validate all three fields
    known_gap_ids = set()
    for gap in gates.get("known_gaps", []):
        if all(k in gap for k in ["id", "reason", "owner", "review_date"]):
            known_gap_ids.add(gap["id"])
        else:
            msgs.append(
                f"INVALID carve-out for '{gap.get('id', 'unknown')}': "
                f"missing required fields (id, reason, owner, review_date). "
                f"Treating as blocking failure."
            )

    # Gate 1: overall pass rate
    if metrics["pass_rate"] < gates["min_pass_rate"]:
        msgs.append(
            f"FAIL pass_rate: {metrics['pass_rate']:.3f} < {gates['min_pass_rate']}"
        )

    # Gate 2: P0 pass rate (with valid carve-outs excluded)
    p0_rate = metrics["p0_pass_rate"]
    if p0_rate < gates["min_p0_pass_rate"]:
        # Check if all P0 failures are covered by valid carve-outs
        p0_failures = [
            case_id
            for mode_ids in report["failure_modes"].values()
            for case_id in mode_ids
            if case_id not in known_gap_ids
        ]
        if p0_failures:
            msgs.append(
                f"FAIL p0_pass_rate: uncovered P0 failures: {p0_failures}"
            )

    # Gate 3: mean faithfulness (only if LLM judge ran)
    if metrics["mean_faithfulness"] is not None:
        if metrics["mean_faithfulness"] < gates["min_mean_faithfulness"]:
            msgs.append(
                f"FAIL mean_faithfulness: {metrics['mean_faithfulness']:.2f} "
                f"< {gates['min_mean_faithfulness']}"
            )

    # Gate 4: forbidden regressions
    for forbidden in gates.get("forbidden_regressions", []):
        if forbidden in failure_modes:
            offenders = [
                c for c in failure_modes[forbidden]
                if c not in known_gap_ids
            ]
            if offenders:
                msgs.append(
                    f"FAIL forbidden regression '{forbidden}' in cases: {offenders}"
                )

    return len(msgs) == 0, msgs


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--llm-judge", action="store_true")
        parser.add_argument("--severity", choices=["P0", "P1", "P2"], default=None)
        args = parser.parse_args()

        cases = load_cases(args.severity)
        gates = load_gates()

        print(f"\n=== NextStep Regression Suite ===")
        print(f"Cases: {len(cases)} | LLM judge: {args.llm_judge}\n")

        scores = []
        t0 = time.time()

        for case in cases:
            print(f"Running {case.id} [{case.severity}]...", end=" ", flush=True)
            try:
                result = run_agent(case.input)
                score = score_case(case, result, args.llm_judge)
                scores.append(score)
                status = "PASS" if score.pass_ else f"FAIL ({score.failure_mode})"
                print(status)
            except Exception as e:
                print(f"ERROR: {e}")
                scores.append(CaseScore(
                    id=case.id,
                    **{"pass": False},
                    tool_match=0.0,
                    citation_ok=False,
                    notes=str(e),
                    failure_mode="runner_error",
                ))

        elapsed = time.time() - t0
        report = summarize(scores, cases, elapsed)

        RESULTS_DIR.mkdir(exist_ok=True)
        out_path = RESULTS_DIR / f"{report['timestamp']}.json"
        out_path.write_text(json.dumps(report, indent=2))
        latest = RESULTS_DIR / "latest.json"
        latest.write_text(json.dumps(report, indent=2))

        passed, msgs = check_gates(report, gates)

        m = report["metrics"]
        print(f"\n=== Results ===")
        print(f"Overall: {m['passed']}/{m['total']} ({m['pass_rate']:.1%})")
        print(f"P0: {m['p0_passed']}/{m['p0_total']}")
        if m["mean_faithfulness"]:
            print(f"Mean faithfulness: {m['mean_faithfulness']:.2f}")
        print(f"Elapsed: {elapsed:.1f}s")
        print(f"Results: {out_path}")

        print(f"\n=== Gate Check ===")
        if passed:
            print("ALL GATES PASSED ✓")
        else:
            print("GATES FAILED ✗")
            for msg in msgs:
                print(f"  {msg}")

        raise SystemExit(0 if passed else 1)

    except SystemExit:
        raise  # let gate exits through cleanly
    except Exception as e:
        print(f"\nRUNNER ERROR (exit code 2 — infra/dependency failure, not a gate breach): {e}")
        import traceback
        traceback.print_exc()
        raise SystemExit(2)


if __name__ == "__main__":
    main()