# docs/SPEC.md
## NextStep — Engineering Specification and Build Log

This document is a living engineering record, not a polished writeup. It tracks what was actually built vs. planned, real bugs found and fixed, and honest open items at each stage. Updated as the system evolves.

---

## Problem

Sexual assault survivors need immediate guidance on what to do next — without figuring it out alone in the immediate aftermath of trauma. The current workaround is calling a hotline or going straight to a hospital, often without knowing whether that hospital has SANE (Sexual Assault Nurse Examiner) nurses on staff. A search box can't solve this — it requires the user to already know the right terms. An agent can ask follow-up questions, surface things a survivor wouldn't think to ask, and recognize signs of crisis to escalate appropriately.

---

## Architecture

**Users & surfaces:**
- Primary user: survivors, via Streamlit web UI
- Auth model: service account — backend authenticates to external APIs (Claude, Google Maps) using its own credentials. No per-user login, consistent with the anonymity design principle (no storage of survivor contact or identifying details)

**Happy path:**
1. User provides location → validated for NYC scope
2. Safety-check dropdown establishes current situation (assaulter nearby / at home / in public) → routes to 911, Safe Horizon, or a precinct as needed
3. Nearest SANE-certified hospital calculated via Google Maps API
4. Uniform instructions explain what to expect at the hospital
5. Resource menu presents next-step options (reporting, financial assistance, mental health support)
6. Before any Claude call: `is_crisis()` runs as a hard gate. If matched → safety resources shown, Claude never called. Not parallel — sequential, deterministic.
7. If no crisis match → Claude-powered Q&A, grounded in verified sources

**Tools:**

| Tool | Input | Side effects | Failure modes |
|---|---|---|---|
| Google Maps distance lookup | Validated NYC location | None (read-only) | API timeout; non-NYC location silently accepted |
| `search_kb` (RAG) | Survivor's question | None (read-only) | Hallucination if grounding fails; low-score refusal |
| `is_crisis()` | User input | Triggers Slack escalation if matched | Coverage gaps; negation false-positives |
| `escalate_case` | User ID, reason | Posts to Slack (write tool) | Slack API failure; duplicate escalation |

---

## SLOs

| Metric | Target | Current status |
|---|---|---|
| p95 latency | ≤ 10s | Measured per-turn; full multi-turn interactions may exceed |
| escalation recall | 100% on golden set should-trigger cases | See Day 2 status |
| grounded rate | Correct source in top-3 retrieval, 100% | See Day 4 status |
| citation accuracy | Zero fabricated citations | See Day 4 status |
| tool failure handling | 100% graceful (never bare error) | Implemented |

---

## Out of scope

- Expanding to other cities (NYC-only by design)
- Per-user auth/accounts (anonymity is a hard constraint)
- Multi-language support (escalation phrase list is English-only; full multi-language would require separate safety layer work)

---

## Day 2: Repo scaffold, escalation layer, eval foundation

**Built and tested:**
- `agent/escalation.py` — real deterministic crisis check. 26 phrases (22 original + 4 added from golden-set categories). Not ~10 as originally estimated.
- `agent/scope_check.py` — real fix for confirmed NYC-scope bug (see below)
- `evals/golden.jsonl` — 18 cases: 15 escalation (9 should-trigger, 6 should-not-trigger, covering paraphrase/negation/third-person/minimizing), 3 Q&A pairs
- `evals/run_eval.py` — real runnable script. Q&A cases correctly reported as skipped ("not yet testable — RAG not built"), not silently passed

**Eval results (both runs kept — honest history matters more than a single passing snapshot):**
- Run 1 (8 cases): 4/5 escalation passed. 1 coverage-gap miss.
- Run 2 (18 cases, after deliberately adding harder cases): **8/15 (53%).**
  - 6 coverage-gap misses — paraphrased hopelessness, burden, "no reason to keep going," "trapped." Substring matching cannot generalize to new phrasing by design.
  - 1 false-positive bug — "I am not saying I want to hurt myself, I just feel really low today" incorrectly triggered because "hurt myself" matches as a bare substring regardless of negation. "I will hurt myself" and "I will NOT hurt myself" are identical to a substring check. This is a structural limitation, not a missing phrase — adding more phrases cannot fix it.

**Interim mitigation for false-positive:** the crisis-response screen is worded to acknowledge uncertainty ("it sounds like things are really hard right now") rather than asserting crisis, and includes a visible path to continue to the original Q&A answer. This limits damage without fixing the structural issue.

**Honest SLO note:** "100% recall required" describes the deploy gate target, not current state. Growing the golden set surfaced real gaps faster than the phrase list can be patched — which is the expected, useful outcome of having a golden set.

**Real bug found and fixed:**
- NYC-scope check: `gmaps.geocode(location + ", New York City")` biases the search, it does not filter results. "London" was silently accepted as a valid location. Fixed by checking the geocode result's actual address components (state = NY, locality/sublocality in one of the five boroughs) before accepting. Tested against both the broken case ("London" now shows an out-of-scope message) and a real NYC location (still resolves normally).

**Correction to earlier design:**
- The escalation check does NOT run in parallel with Claude's Q&A response. Looking at the real code: `is_crisis()` runs first, as a hard gate — if it matches, Claude is never called. Stronger than "parallel" implied.

**Still open:**
- RAG / retrieval not yet built
- Escalation coverage gaps and negation false-positive — not fixed deliberately. Patching phrases reactively was explicitly rejected in favor of keeping the golden set an honest coverage measure. Real fix requires moving beyond pure substring matching.
- Deploy-gate enforcement is currently a manual discipline, not automated

---

## Day 3: Real multi-step agent loop

**Built and tested:**
- `agent/runtime.py` — real `AgentRuntime` implementing plan → call tool → observe → answer. Uses Claude's actual `tool_use`/`tool_result` content-block pattern.
- 4 real tools with JSON Schema `parameters` definitions and typed `ToolResult(ok, data, error_code)` returns: `get_time`, `echo`, `check_crisis`, `escalate_case`
- Three policy guards, all proven with real evidence: unknown-tool rejection, args validation, side-effect blocking (`allow_side_effects` flag)
- Fourth guard added mid-day after a real bug: cap parallel tool calls at 1 per turn
- Structured logging: every turn logs `turn_start`, `llm_call` (model, latency_ms, tokens), `tool_call`, `tool_result`, `final` or `max_turns_exceeded`
- `agent/test_guards.py` — deterministic tests mocking `_call_model` to force scenarios real Claude traffic wouldn't reliably reproduce (missing args, always-failing tool). Standard technique for isolating guard logic from model behavior.
- `docs/manual_scenarios.md` — 6 scenarios with real evidence: 4 from live API calls, 2 from deterministic mocked tests

**Real bugs found and fixed:**
1. **System prompt placement** — Claude's API rejects a `system` role inside `messages`. Must be a top-level parameter. Found via live `400 BadRequestError`.
2. **Tool result message role** — Claude has no `"tool"` role. Tool calls and results are content blocks inside normal `assistant`/`user` turns, threaded via `tool_use_id`. Found via second live `400` error.
3. **Parallel tool call bug** — Claude can request multiple tools in one response. Original code executed only the first but sent Claude's entire response (including un-executed second tool request) back as context, causing a mismatched-`tool_use_id` rejection. Fixed by keeping only the first `tool_use` block per turn and logging `parallel_calls_capped` when extras are dropped.
4. **Refusal-case gap** — agent immediately called `escalate_case` with "reason: emergency" on a vague request, with no pushback. None of the three tool-level guards evaluate substantive justification. Fixed by adding an explicit system-prompt instruction requiring concrete detail before the escalation tool is used.

**Still open:**
- `check_crisis` and `escalate_case` exist only in the test harness, not yet wired into the live `crisis.py` app
- Scenario 3's guard proven deterministically but never exercised by a real, unscripted Claude response

---

## Day 4: RAG pipeline — ingest, retrieval, citation-or-refuse

**Built and tested:**
- `rag/ingest.py` — real ingest pipeline. One chunk per self-contained unit (one hospital entry = one chunk). No fixed-size chunking — NextStep's content is naturally short and self-contained. Extended `Chunk` model with `borough` and `category` fields.
- **46 real chunks ingested**: 20 hospitals, 15 safe-places orgs, 11 hand-written legal/financial/mental-health chunks. No synthetic content.
- `rag/retrieve.py` — `search_kb(query, k, filters)`, dense-only vector search via local Chroma. No hybrid/BM25 — same reasoning as everywhere else: match infrastructure to actual scale.
- `agent/rag_tool.py` — wraps `search_kb` as a real `Tool` for `AgentRuntime`
- `GROUNDING_PROMPT` — every factual claim cited as `[source#chunk_id]`; `INSUFFICIENT_CONTEXT` when retrieval score is low OR chunks conflict; no invented citations, phone numbers, or policy details
- **INSUFFICIENT_CONTEXT has two triggers**: low-score is code-enforced (checked before Claude sees results). Conflicting-chunks is left to model judgment — unlike crisis escalation, an information-accuracy failure here is a lower risk category. This was a deliberate design decision, contingent on also measuring it (see conflict test below).
- **10-question smoke set, all run**: 5 answerable, 3 unanswerable, 2 multi-hop
  - Hit@k: 10/10
  - Citation accuracy: 9/10 fully clean, 1 accepted exception (generic "contact local police" on stolen-car case — common-sense guidance, not a specific falsifiable claim)
- **Conflict test**: deliberately contradictory chunk about Bellevue's SANE status inserted, queried, and removed. Claude correctly detected the contradiction, cited both conflicting chunks, refused to guess, redirected to Safe Horizon's hotline. Conflict-detection design decision now backed by a real test.

**Real bugs found and fixed:**
1. **Distance metric misunderstanding** — `score = 1 - distance` assumed Chroma defaults to a 0-1 similarity score. It doesn't — Chroma defaults to squared L2, ranging roughly 0-4 for normalized vectors. An exact, correct Bellevue match scored `0.164`, below the `0.3` threshold, causing a false INSUFFICIENT_CONTEXT on a question the system could answer. Fixed by explicitly configuring cosine distance (`metadata={"hnsw:space": "cosine"}`). Same query now scores `0.582`.
2. **Invented out-of-scope resource** — Connecticut unanswerable test triggered correct INSUFFICIENT_CONTEXT for hospital data, but then invented "Connecticut Alliance to End Sexual Violence" with a fabricated phone number — a grounding violation even though the refusal itself was correct. Fixed by restricting the model to naming only Safe Horizon's hotline as a fallback in any INSUFFICIENT_CONTEXT response.
3. **Language-switching safety gap** — asked to switch to Spanish, the system complied immediately. The crisis check only recognizes English phrases, so a real crisis message in Spanish would go undetected. Fixed by adding an explicit instruction to decline language switches and explain the safety reason.

**Still open:**
- p95 latency SLO ambiguity: spec says ≤ 10s, but doesn't specify per-turn vs. per full interaction. Multi-hop test surfaced this — individual turns were within budget, total interaction would exceed it.
- Bonus false-premise smoke case ("is the exam free, and if not what insurance") designed but not run
- `search_kb` not yet wired into live `crisis.py` app

---

## Repo structure

```
agent/          # orchestration, runtime, escalation, scope check
tools/          # Claude API calls, Google Maps, Slack, HTTP client
rag/            # ingest pipeline, retrieval, RAG tool
evals/          # golden sets, eval runner, drift detection, CI gate
shadow/         # shadow runner, traffic set, analysis
docs/           # SPEC.md, EVAL_REPORT.md, SHADOW_ROLLOUT.md, sprint_story.md
.github/        # CI workflows (eval gate, keep-alive)
```

---

## Shadow / rollout

Full staged rollout plan: [`docs/SHADOW_ROLLOUT.md`](SHADOW_ROLLOUT.md)

Shadow run results and disagreement analysis: [`shadow/ANALYSIS.md`](../shadow/ANALYSIS.md)

**Deploy gate (current):** `make eval-p0` must pass before any push touching escalation, RAG, or Q&A generation. CI gate runs automatically on every push to main via GitHub Actions.