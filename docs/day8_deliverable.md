# Day 8 Deliverable: Regression Suite + CI Gate

## What was built

One-command regression suite that fails CI on gate breach, with threshold config, timestamped results, and 5 deterministic unit tests for the runtime's policy guards.

**Run commands:**
```
make eval        # full suite, no LLM judge
make eval-judge  # full suite with LLM-as-judge faithfulness scoring
make eval-p0     # P0 cases only (fastest, used as the CI gate)
```

**Exit codes:** 0 = all gates passed, 1 = gate breach. Same command locally and in CI — no special CI mode.

---

## Files

| File | Purpose |
|---|---|
| `evals/run.py` | One-command runner: loads golden set, runs agent, scores cases, writes timestamped results, checks gates, exits 0 or 1 |
| `evals/gates.yaml` | Threshold config: pass rates, faithfulness floor, forbidden regressions, known-gap carve-outs |
| `Makefile` | `make eval`, `make eval-judge`, `make eval-p0` |
| `.github/workflows/eval.yml` | GitHub Actions CI gate: runs `make eval-p0` on every push to main |
| `evals/test_runtime_guards.py` | 5 pytest unit tests for runtime policy guards — zero API calls |
| `evals/results/` | Gitignored — timestamped JSON results written per run, `latest.json` always current |

---

## Gate configuration (`evals/gates.yaml`)

```yaml
min_pass_rate: 0.90
min_p0_pass_rate: 1.0
min_mean_faithfulness: 3.5
max_p95_latency_ms: 12000
forbidden_regressions:
  - hallucination
  - invented_resource
  - missed_escalation

known_gaps:
  - id: adv-neg-001
    reason: "Double-negative detection ceiling"
    owner: "Riddhima Saraf"
    review_date: "2026-10-01"
```

**Known-gap carve-out policy:** a gap excluded from the P0 gate must have all three fields — owner, reason, review_date. Missing any field treats the failure as blocking. This closes the "carve-out as loophole" problem: the exclusion list can't quietly grow without explicit accountability on every entry.

---

## CI gate (`github/workflows/eval.yml`)

Steps in order:
1. Checkout code
2. Install dependencies
3. **Build vector store** (`python -m rag.ingest`) — required because `chroma_db/` is gitignored; CI clones a fresh repo with no database
4. Run `make eval-p0`
5. Upload `evals/results/latest.json` as a CI artifact (even on failure)

**Real bugs found wiring CI:**

**Bug 1: `ANTHROPIC_KEY` empty in CI — wrong secret name.** The secret was saved in GitHub as `NEXTSTEP` instead of `ANTHROPIC_KEY`. Found by adding a debug step that printed "ANTHROPIC_KEY is EMPTY" explicitly, rather than assuming the secret injection was working. Fixed by deleting `NEXTSTEP` and re-adding four correctly named secrets: `ANTHROPIC_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `GOOGLE_MAPS_KEY`.  <!-- pragma: allowlist secret -->
**Bug 2: API key read at import time, not call time.** `agent/runtime.py` and `evals/run_evals_v2.py` both read `ANTHROPIC_KEY` at module load time — before CI's environment variables were injected. Fixed by moving the `anthropic.Anthropic()` client initialization inside the function that actually calls the API, so the key is read fresh at call time rather than locked in as empty when the module first imports.

**Bug 3: Vector store empty in CI.** `chroma_db/` is gitignored, so CI had no data to retrieve from. Fixed by adding `python -m rag.ingest` as an explicit build step in the workflow, same fix as the Day 6 Docker build issue — same class of bug, different environment.

---

## Unit tests (`evals/test_runtime_guards.py`)

5 pytest tests, all passing in 1.14 seconds, zero API calls — the LLM is fully mocked:

| Test | What it asserts |
|---|---|
| `test_unknown_tool_blocked` | Calling a tool not in the registry returns an error to the model and continues — doesn't crash |
| `test_missing_required_args_blocked` | Calling a tool without required args returns `invalid_args` error — handler never called |
| `test_side_effects_blocked_when_disabled` | A `side_effect=True` tool's handler is never called when `allow_side_effects=False` |
| `test_side_effects_allowed_when_enabled` | A `side_effect=True` tool's handler is called when `allow_side_effects=True` |
| `test_max_turns_exceeded` | Loop hitting `max_turns` without a final answer returns `max_turns_exceeded` — doesn't hang |

These tests are deterministic and fast because they mock `AgentRuntime._call_model` entirely — they test the runtime's policy enforcement logic, not the model's behavior.

---

## First CI run results

**26/27 (96.3%), 26/27 P0, ALL GATES PASSED ✓**

Elapsed: 115.6 seconds on GitHub's Ubuntu runner (includes Chroma model download of 79MB on first run).

The one case not passing is `adv-neg-001` (double-negative detection gap), correctly carved out in `gates.yaml` with owner, reason, and review date — not silently ignored.

---

## What exit code 1 actually means in practice

If a push drops the pass rate below 90%, introduces a `hallucination` or `missed_escalation` failure on a non-carved-out case, or breaks a P0 case without a valid carve-out — the GitHub Actions run fails, the PR is blocked, and the failure is visible in the Actions tab before any merge happens. This is the difference between "we have evals" and "evals actually gate the deploy."

---

## Still open, honestly

- **Exit code 2** (Python crash before any cases run) is not yet distinguished from exit code 1 (gate failure) in the Makefile — both show as a failed CI step. A future improvement would catch runner errors separately so a dependency issue doesn't look identical to a real eval regression.
- **No latency tracking yet** — `p95_latency_ms` is computed but currently returns `None` since individual case latencies aren't being recorded per-run. Placeholder in the gate config but not enforced.
- **CI runtime is 115 seconds** — mostly Chroma model download (79MB). Caching the model between runs would bring this under 60 seconds.
- **Unit tests wired into CI as a separate step** — `pytest evals/test_runtime_guards.py -v` runs before `make eval-p0` in the GitHub Actions workflow. A regression in side-effect blocking or arg validation fails CI independently, before the full eval suite runs. Exit codes are split: 0 = gates passed, 1 = gate breach, 2 = runner/infra crash — a dependency break and a real eval regression now look different in the Actions tab.
- **Latency gate removed** — `max_p95_latency_ms` was in `gates.yaml` but the value was hardcoded to `None` in the summarizer, meaning the threshold could never fire. Removed entirely rather than leaving a gate that looks real but isn't. Will be re-added once per-case latency is actually tracked.