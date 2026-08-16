# docs/SHADOW_ROLLOUT.md
## NextStep Agent: Shadow Results + Staged Rollout Plan

**Status:** Shadow complete. Recommendation: proceed to Stage 1 (internal dogfood) with deterministic layer mandatory.
**DRI (Directly Responsible Individual):** Riddhima Saraf
**Last updated:** Day 12 of 14-day FDE sprint
**Links:** [Live demo](https://nextstep-9ppb.onrender.com) | [GitHub](https://github.com/RiddhimaSf/nextstep) | [Eval report](docs/EVAL_REPORT.md) | [Shadow analysis](shadow/ANALYSIS.md)

---

## Executive summary

NextStep is a trauma-informed AI guide for sexual assault survivors in NYC. The production system uses a deterministic crisis-detection layer (`is_crisis()`) as a mandatory first gate before any LLM call. A 55-case shadow run compared the agent's proposals against the baseline system with all writes disabled.

**Agreement rate:** ~78% on synthetic traffic (not yet validated against real production queries).
**Critical finding:** the agent missed 4 of 9 true crisis cases by responding warmly without surfacing the 988 hotline — making it unsafe as a replacement for the deterministic gate. On non-crisis traffic (62% of queries), the agent produced measurably better answers (4.8/5.0 LLM-judge preference, 10/10 cases).

**Go/no-go:** **Conditional go** — proceed to Stage 1 dogfood, with the deterministic layer remaining mandatory and the agent operating as an additive quality layer only. The "warm without resources" failure mode on crisis inputs must be resolved before any traffic reaches Stage 2.

---

## System under test

**Architecture:**
```
Survivor input
    ↓
is_crisis() — deterministic, mandatory, cannot be disabled
    ↓ crisis                    ↓ no crisis
show_crisis_resources()     AgentRuntime.run()
post_escalation_to_slack()      ↓
                            search_kb (RAG, 46 chunks)
                                ↓
                            grounded, cited answer
```

**Tools:** `search_kb` (read-only), `escalate_case` (write, side_effect=True)
**Model:** claude-sonnet-4-6
**RAG corpus:** 46 chunks — NYC hospital directory, legal rights, financial assistance, mental health resources
**Eval suite:** 44 golden cases (28 P0), CI gate via GitHub Actions, `make eval-p0`
**Shadow corpus:** 55 hand-crafted cases across 11 categories

---

## Shadow results (summary — see shadow/ANALYSIS.md for full detail)

| Metric | Value | Note |
|---|---|---|
| Agreement (escalation) | ~78% (43/55) | Synthetic traffic — directional only |
| agent_missed | 6/55 (11%) | 4 warm-without-hotline, 1 ambiguous, 1 correct non-escalation miscounted |
| agent_over | 6/55 (11%) | 2 clear over-trigger, 1 correct catch, 3 ambiguous |
| Answer quality (non-crisis, LLM judge) | 4.8/5.0 | 10/10 cases agent preferred; judge is another LLM |
| Unsafe write proposals | 0/55 | Three-layer verified |
| avg / p95 latency | 6.9s / 14.1s | vs ~0ms deterministic baseline |

**Key finding:** The "warm without resources" failure mode (agent responds compassionately to crisis inputs but omits the 988 hotline) is the blocker for Stage 2+. It occurred on 4/9 true crisis cases. Until resolved, the agent cannot handle crisis inputs without the deterministic layer as a mandatory backstop.

---

## Staged rollout

| Stage | Traffic | Entry criteria | Exit criteria | Rollback trigger | Rollback action |
|---|---|---|---|---|---|
| **0 Shadow** ✅ | 0% writes | Eval gates green, CI passing | N≥50, unsafe_writes=0, analysis complete | Any unsafe write | Disable runner |
| **1 Dogfood** | Internal users only, 1 week | Shadow complete, warm-without-resources failure mode documented and understood | 0 warm-without-resources incidents on ≥15 crisis-adjacent queries; 0 agent_missed; CSAT≥4.0/5.0. If internal volume doesn't reach 15 crisis-adjacent queries in one week, extend Stage 1 rather than advance — "0 incidents on n=2" is not a signal. | Any agent_missed or unauthorized write | `AGENT_ENABLED=false` |
| **2 Canary 5%** | 5% of non-crisis traffic only | Dogfood clean, warm-without-resources fix deployed and re-evaluated | error_rate < baseline+1%, faithfulness≥3.5, latency p95<15s, 0 unauthorized writes | error_rate>baseline+2% OR unauthorized_write>0 | Auto: `CANARY_PCT=0` |
| **3 Canary 25%** | 25% of non-crisis traffic | Canary 5% ran 2 weeks clean | Same metrics at 25% volume, cost/request<$0.01 | Same as Stage 2 | Auto: `CANARY_PCT=5` (revert to prior stage) |
| **4 Full rollout** | 100% non-crisis traffic | Canary 25% ran 2 weeks clean | — | Metric breach or P0 incident | Auto: `CANARY_PCT=0`, page DRI |

**Critical constraint, all stages:** the deterministic `is_crisis()` check is mandatory at every stage. It cannot be disabled, canary'd, or A/B tested. It runs before any agent call on 100% of traffic regardless of stage. This is not a configuration decision — it is an architectural requirement.

**When real traffic enters the loop:**
The 78% agreement figure comes from synthetic traffic written by the same person who built the system. The first real-world signal enters at Stage 1 dogfood (internal users). At the end of Stage 1, re-run the shadow analysis against internal session logs — not the synthetic set — and compare agreement rates. If the real-traffic rate differs from the synthetic rate by more than 5 points in either direction, treat that as a new finding requiring review before Stage 2 rather than assuming the synthetic number holds. Stage 2 entry criteria implicitly assumes the synthetic-traffic 78% is directionally correct; if the Stage 1 real-traffic number falsifies that assumption, Stage 2 does not proceed until the discrepancy is understood.

**What must be resolved before Stage 2:**
The "warm without resources" failure mode must be fixed and re-evaluated before any non-internal traffic sees the agent on crisis-adjacent inputs. Proposed fix: add an explicit post-processing check — if `is_crisis()` returns True on the input AND the agent's response does not contain crisis signal words (988, crisis text line, etc.), append the crisis resource block automatically before showing the response. This makes the safety property architectural again, not dependent on the model's judgment.

---

## Kill switches

Four independent kill switches, each operable without a code deploy:

### 1. Full agent disable
```
AGENT_ENABLED=false
```
Set in Render's environment variables. Takes effect on next request (no restart required if read at call time — confirmed in `agent/runtime.py` after Day 8 fix). Falls back to baseline system entirely.

### 2. Write tool disable
```
ALLOW_WRITES=false
```
Disables `escalate_case` and any future write tools independently of the agent itself. The agent continues to run for read queries; write proposals are blocked and logged. Equivalent to permanent `allow_side_effects=False`.

### 3. Model fallback
```
MODEL_FALLBACK=baseline
```
Routes all traffic to the deterministic baseline without disabling the agent infrastructure. Useful for model-version rollbacks without changing application code.

### 4. Automatic rollback on unauthorized write
Any `would_write=True` record in the shadow log, or any tool call with `side_effect=True` that reaches the handler when `ALLOW_WRITES=false`, triggers an immediate page to the DRI and sets `AGENT_ENABLED=false` automatically via a startup check in `crisis.py`.

**Kill switch owner:** Riddhima Saraf (DRI). In a real team deployment, this would be the on-call engineer with a defined escalation path to a clinical SME for crisis-related incidents.

---

## Monitoring & alerting

### Metrics to track per stage

| Metric | Source | Alert threshold | Owner |
|---|---|---|---|
| `agent_missed` rate | Shadow log / pairwise records | >0 on any true crisis case | DRI — immediate |
| `unauthorized_write` count | `would_write` field in ShadowRecord | >0 | DRI — immediate, auto-rollback |
| `faithfulness` (LLM judge sample) | Weekly eval run with `--llm-judge` | <3.5 mean | DRI — within 24h |
| p95 latency | Per-request trace timing | >15,000ms | DRI — within 24h |
| error_rate | runner_error count in eval results | >baseline+2% | DRI — within 24h |
| cost/request | Token count × Sonnet pricing | >$0.01 | DRI — weekly review |
| user thumbs-down (if UI exposes it) | Streamlit session feedback | >10% | DRI — weekly review |

**Judge reliability note:** the `faithfulness≥3.5` gate is enforced by an LLM judge (claude-sonnet-4-6 grading claude-sonnet-4-6 outputs). LLM judges have a known bias toward warmer, more elaborate responses — the same bias that produced the 4.8/5.0 quality score in the shadow analysis. To prevent the gate from becoming self-referential, the plan is to spot-check N=5 judge scores against a human rater per month and flag any systematic discrepancy. Until that inter-rater check is run at least once, the faithfulness gate should be treated as a directional signal, not a hard threshold.

### Review cadence
- **Daily (Stages 1-2):** scan shadow log for agent_missed and would_write
- **Weekly (all stages):** run `make eval-p0`, compare to baseline hash, run drift check (`python -m evals.drift`)
- **On any P0 incident:** immediate rollback, root cause within 24h, post-mortem before re-enabling

### Dashboard
Currently: manual review of `shadow/results.jsonl` and `evals/results/latest.json`. Production-ready monitoring would add: Render log alerts on `RUNNER_ERROR` prefix, a simple Streamlit admin page showing weekly eval pass rate and shadow agreement rate over time.

---

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Agent responds warmly to crisis input without surfacing 988 | **High** (4/9 in shadow) | **Critical** | Post-processing safety net: if `is_crisis()` True AND agent response lacks crisis signal words, append crisis resource block. Mandatory before Stage 2. |
| Agent over-triggers on resource/cost questions | **Medium** (2/55 in shadow) | **Medium** | Acceptable at Stage 1-2; monitor thumbs-down rate; add "is this a crisis?" classifier if rate rises above 5% |
| Hallucinated policy detail or invented resource | **Low** (0/55 in shadow) | **High** | Eval gate (`forbidden_regressions: hallucination, invented_resource`); citation-or-refuse enforcement in GROUNDING_PROMPT |
| Idempotency file wiped on Render restart | **Medium** (ephemeral disk) | **Medium** | Known gap from Day 5. Duplicate escalation possible on restart. Mitigate: add Redis or Postgres idempotency store before Stage 2. |
| Runaway cost | **Low** | **Medium** | ~$0.007/request at current volume. Add `MAX_DAILY_SPEND_USD` env var check before Stage 3. |
| p95 latency spike (>15s) | **Medium** (observed 17.9s max) | **Medium** | Automatic alert; consider reducing `max_turns` from 4 to 2 for latency-sensitive traffic |
| Model version change breaks eval comparability | **Low** | **Medium** | Record model ID in every result JSON (already done); drift check flags model change as a signal requiring human sign-off |
| PII exposure in logs | **Low** (mitigated) | **High** | User message hashed in traces (Day 8 Armando fix); shadow logs redact PII before write; Slack posts request ID only |

---

## Customer-facing risk memo

**Data handling:** User inputs are never stored in plaintext. The trace system logs a one-way SHA-256 hash of each message alongside the request ID. Slack escalation notifications contain only the request ID — the message content is never posted to the channel. Shadow run inputs are redacted (email, phone, SSN) before any file is written.

**Human in the loop for writes:** The `escalate_case` tool (Slack notification) is the only write action in the system. It fires only when `is_crisis()` returns True — a deterministic, auditable decision, not a model judgment. Every escalation is logged with a request ID that can be replayed via `print_trace(request_id)`.

**Audit log retention:** Request IDs and hashed message content are written to `logs/traces.jsonl` on the deployed instance. On Render's free tier, this file is ephemeral (lost on restart). Stdout trace logs (`TRACE_LOG:` prefix) are captured by Render's log viewer for approximately 7 days. For audit-grade retention, traces should be forwarded to an external sink (Postgres, Logtail) — not yet implemented, correctly scoped as a pre-Stage-3 requirement.

**Model behavior:** The agent never makes decisions autonomously about crisis resources. The deterministic `is_crisis()` check runs first on every input, before any model call. If it fires, crisis resources are shown and the model is never invoked for that message. The model's role is exclusively to answer factual questions about NYC survivor resources — grounded in a 46-chunk verified corpus, with citation-or-refuse enforcement.

---

## Ask for stakeholders

**Stage 1 approval request:**
Approve move to Stage 1 (internal dogfood) on the following conditions:
1. The "warm without resources" post-processing safety net is implemented and passes the P0 eval gate before any internal user sees the agent on crisis-adjacent inputs
2. The idempotency store is moved to a persistent layer (Redis/Postgres) before Stage 1 begins
3. DRI (Riddhima Saraf) reviews the shadow log daily for the first week of Stage 1
4. Stage 1 runs for a minimum of one week before any Stage 2 discussion

**What is not being asked:**
- To disable or reduce the deterministic `is_crisis()` check at any stage
- To route crisis inputs through the agent as the primary decision-maker at any stage
- To proceed to Stage 2 before the warm-without-resources failure mode is confirmed resolved

---

## What would stop the train

Any of the following triggers immediate rollback to baseline and a DRI page, regardless of stage:

1. **Any `agent_missed` case on a true crisis input** — baseline escalated, agent did not show resources
2. **Any unauthorized write** — `would_write=True` or a side-effect tool handler reached with writes nominally disabled
3. **Eval gate breach** — `make eval-p0` exits with code 1 on the weekly run
4. **P0 incident from a real user** — any report of a survivor receiving a non-crisis response to a crisis message
5. **New failure mode in drift check** — `python -m evals.drift` returns exit code 1 with a failure mode not in `known_gaps`

The DRI does not need approval to execute any of these rollbacks. The kill switch is unilateral.