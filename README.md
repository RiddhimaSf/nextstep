# NextStep

**Live demo:** https://nextstep-9ppb.onrender.com
*(Free-tier hosting — the app spins down after 15 minutes of inactivity. First load after idle time can take 30-60 seconds. A GitHub Actions workflow pings it every 10 minutes to reduce this, but it is not guaranteed.)*

**90-second demo video:** https://www.loom.com/share/e24d6fbf0ca644b5913c544f6f53eb12
*(Happy path with real tool-calling orchestration, a deliberate refusal, and proof of live deployment via request-ID trace lookup — see "Day 6: real findings" below for the honest story behind what the video shows.)*

## Problem

Sexual assault survivors in New York City need immediate, trustworthy guidance on what to do next — without figuring it out alone in the immediate aftermath of trauma. The current default is calling a hotline or going straight to a hospital or police station, often without knowing whether that hospital has SANE (Sexual Assault Nurse Examiner) staff on hand, or what to expect once there.

NextStep is a trauma-informed guide that walks a survivor through immediate safety, medical care, and next steps — grounded entirely in verified NYC resources, never inventing information, and with a deterministic safety layer that never depends on a language model's judgment for the moment that matters most.

## Architecture

```mermaid
flowchart TD
    U[Survivor] --> UI[Streamlit UI - crisis.py]
    UI --> LOC[Location step]
    LOC --> SCOPE{In NYC scope?}
    SCOPE -->|No| OUT[Outside-NYC message]
    SCOPE -->|Yes| SAFETY[Safety-check dropdown]
    SAFETY --> HOSP[SANE hospital lookup - Google Maps API]
    HOSP --> INFO[What-to-expect + resource menu]
    INFO --> Q[Open question box]

    Q --> CRISIS{is_crisis check\ndeterministic, English phrase list}
    CRISIS -->|Match| SLACK[Silent Slack escalation\nvia ResilientClient]
    CRISIS -->|Match| CARDS[show_crisis_resources\nsurvivor-facing]
    SLACK --> LOG1[(logs/traces.jsonl)]

    CRISIS -->|No match| RAG[search_kb tool]
    RAG --> CHROMA[(Chroma vector store\nlocal, 46 chunks)]
    CHROMA --> SCORE{Score >= threshold?}
    SCORE -->|No| INSUFF[INSUFFICIENT_CONTEXT]
    SCORE -->|Yes| CLAUDE[Claude: grounded, cited answer]
    CLAUDE --> LOG2[(logs/traces.jsonl)]

    subgraph Agent Loop [agent/runtime.py - AgentRuntime]
        RAG
        CRISIS
    end

    style SLACK fill:#f9d5d3
    style CARDS fill:#f9d5d3
    style CHROMA fill:#d3e5f9
```

**Key design decisions, made deliberately, not defaulted into:**
- **Crisis detection is deterministic** (`agent/escalation.py`, substring match against a maintained phrase list), never left to the model — the same reasoning applied throughout: a missed safety signal is a categorically worse failure than a missed retrieval.
- **RAG is dense-only**, no hybrid/BM25 — the knowledge base is ~46 well-defined chunks, a scale where hybrid search solves a problem that doesn't exist here.
- **The live app's RAG path runs through a real `AgentRuntime.run()` tool-calling loop**, not direct function calls — verified with a live trace showing an actual `search_kb` tool call and result, not just a final chat bubble. This was a real gap found and fixed on Day 6, not the original implementation — see "Day 6: real findings" below.
- **Escalation notifications are silent** — the survivor only ever sees `show_crisis_resources()`; the Slack post to the team happens invisibly in the background, wrapped in try/except so a Slack failure never blocks or delays the survivor's actual experience.
- **Vector store is local Chroma**, not a managed service — no separate server to orchestrate, consistent with the actual scale of a ~46-chunk corpus.

## How to run

**Locally (Docker):**
```
docker build -t nextstep .
docker run -p 8501:8501 --env-file .env nextstep
```
Open http://localhost:8501

**Locally (without Docker):**
```
pip install -r requirements.txt
python -m streamlit run crisis.py
```

**Required environment variables** (`.env`, gitignored, never committed):
```
ANTHROPIC_KEY=
GOOGLE_MAPS_KEY=
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

## Demo script

Three prompts that reliably demonstrate the three real capabilities built this sprint. Reach the open question box via: location → safety check → hospital step → "Continue" through to the resource screen.

**1. Grounded, cited answer** — "Does Bellevue Hospital have a SANE nurse?"
Expected: a specific, factual answer citing `[hospital_directory#bellevue_hospital_center]`, sourced from the real hospital directory, not the model's general knowledge.

**2. Refusal — out of scope** — "I'm in Connecticut, what SANE hospitals are near me?"
Expected: `INSUFFICIENT_CONTEXT`, explicitly stating NextStep only covers NYC, with no invented out-of-scope organization named.

**3. Crisis escalation (safety layer)** — "This is never going to get better"
Expected: the survivor sees only warm crisis resources (988, Safe Horizon, RAINN) — no visible sign of escalation. Behind the scenes, a real message posts to the team's Slack channel with a request ID. If something looks wrong afterward, the request ID printed in `logs/traces.jsonl` can be pasted into `print_trace(request_id)` to replay the exact session — this is the actual answer to "what happens if the demo gives a wrong answer": pull the trace, not apologize.

## Trace replay (for debugging live, including in an interview)

Every agent run gets a unique request ID and a full structured trace persisted to `logs/traces.jsonl`. To replay any session:
```python
from agent.runtime import print_trace
print_trace("the-request-id")
```

### Trace persistence: local vs. deployed

Structured JSON logs (`logs/traces.jsonl`) are written per-request but do not survive Render free-tier restarts (ephemeral filesystem). Fix is either a paid persistent disk or an external sink (Postgres/Logtail/etc.) — not implemented, matching infra spend to a demo deployment, not a production one.

**Trace replay works fully in local Docker** (`docker run -p 8501:8501 --env-file .env nextstep`), where `print_trace(request_id)` reads the persisted file directly.

**On the live deployed instance**, every trace is *also* printed to stdout with a `TRACE_LOG:` prefix, in the same JSON shape as the file. Render's log viewer captures stdout regardless of disk persistence, so a specific request's trace can be found by searching Render's dashboard logs for its request ID — a free, no-infra-change way to recover a trace on the deployed app, short of full local-style replay. Citation tags in each answer (e.g. `[hospital_directory#bellevue_hospital_center]`) are the additional, always-visible evidence that a given deployed response is genuinely grounded, independent of log access.

## Limitations, named honestly

- **Escalation coverage, updated with a real re-test.** The deterministic phrase list originally scored 8/15 (53%) on the expanded golden set, including a negation false-positive ("I am not saying I want to hurt myself" incorrectly triggered). Both were addressed directly: the phrase list was expanded to close the 6 specific coverage-gap misses, and a narrow negation-aware check (a fixed-width lookback for negation cues before a match) was added to fix the false-positive. **Re-tested against the same 15-case golden set: 15/15 (100%).** This is not claimed as a general solution — the negation check is a simple, fixed-width heuristic (stated explicitly in `agent/escalation.py`'s comments as a known simplification, not a real negation parser), and the phrase list still cannot generalize to phrasing beyond what's listed. It closes the specific, measured gaps found so far; new paraphrasing not yet tested could still be missed. See `docs/SPEC.md` for the full eval history, not just the latest number.
- **Startup guard added for the empty-vector-store bug class.** The Day 6 finding (production database silently empty) shipped with no operator-visible alarm. `crisis.py` now asserts the vector store returns at least one result for a basic query at startup, failing loud on boot rather than failing silent on every request — this catches the *class* of bug (a Docker build that skips ingestion, a wiped volume, etc.), not just the one instance already found and fixed.
- **Pre-commit secret scanning added** (`.pre-commit-config.yaml`, using `detect-secrets`) after a real incident where two hardcoded API keys were committed before being caught — one by GitHub's push protection, one already public before that. Disclosure and rotation after the fact were necessary but not sufficient; this is the forward-looking preventive control, run locally before a commit ever reaches GitHub, not relying solely on GitHub's own scanning as the last line of defense.
- **English only.** This is a stated safety limitation, not just a missing feature: the crisis-detection layer only recognizes English phrases, so responding in another language could mean a real crisis message goes undetected.
- **NYC only.** By design — the corpus (hospitals, legal process, financial assistance) is NYC-specific. Confirmed working: a non-NYC location correctly triggers an explicit out-of-scope message rather than silently returning irrelevant results.
- **Idempotency store has a real, untested-for race condition.** The file-based idempotency check (`sent_escalation_keys.txt`) is not atomic — under concurrent calls, two near-simultaneous requests could theoretically both pass the "already sent" check before either writes. Not hit in testing, but not mitigated.
- **Free-tier hosting cold starts.** See the note at the top of this file.
- **`search_kb` is wired into the live app; the full multi-tool `AgentRuntime` (Slack, `check_crisis`, `escalate_case` as a formal tool) is currently only exercised through the test harness (`agent/test_runtime.py`), not the live conversational flow** — the live app calls `search_kb` and Slack directly rather than through the full agent loop.

## Cost notes

- **Claude (Sonnet)**: cost per request is not yet instrumented — a named, open item since Day 2. Expected mid-range cost tier given the model choice; real measurement is the next step, not a number claimed here without evidence.
- **Google Maps API**: pay-per-call beyond a free monthly credit; low-volume demo usage stays within Google's free tier in practice.
- **Slack**: free for this usage pattern (a single bot posting to one channel).
- **Hosting (Render)**: $0/month, free tier, no credit card required. Tradeoff: cold starts after 15 minutes idle (mitigated, not eliminated, by the GitHub Actions keep-alive workflow).
- **Chroma**: local, embedded, no cost — no managed vector database service in use.

## Day 6: real findings (production readiness)

Day 6's actual goal — Docker, deployment, observability — surfaced real bugs that only exist at the "shipped, not just working locally" level. Documented here in full rather than only in `docs/SPEC.md`, since these are the specific findings a "walk me through what broke" conversation would reference.

**1. The deployed instance's vector store was silently empty.** `.dockerignore` correctly excludes `chroma_db/` as regeneratable local data — but nothing in the original Dockerfile ever regenerated it inside the built image. The deployed app ran for a period with zero chunks in its knowledge base, meaning every real question returned `INSUFFICIENT_CONTEXT` regardless of whether the answer existed. Found by adding a temporary diagnostic (`collection.count()`) and confirming it printed `0` on the live instance, despite the identical code working correctly locally. **Fixed** by running `RUN python -m rag.ingest` as an explicit Docker build step, so every deployed image now bakes in a freshly populated database — not a file that was assumed to travel with the code but never actually did.

**2. `crisis.py`'s live RAG path did not originally call the real agent loop.** Initially, the live app called `search_kb_handler()` and `client.messages.create()` directly — two functions in sequence, not real tool-calling orchestration through `AgentRuntime.run()`. This meant the trace-replay system built earlier in Day 6 never actually captured live user sessions; it only worked through the standalone test harness. **Fixed** by rewiring `crisis.py`'s RAG path to build a real `AgentRuntime` with `search_kb` registered as a tool and call `.run()` — genuine plan → call tool → observe → answer orchestration, verified live with a real trace showing an actual `tool_call`/`tool_result` pair, not just a chat bubble. The crisis-escalation path deliberately still does not go through this loop — that decision must stay deterministic, not model-judgment-based (Day 1 principle) — but now calls the same `persist_trace()` function directly, so it also gets a real, replayable trace.

**3. A stale shell environment variable silently overrode a correct `.env` file.** During local debugging, an old `export ANTHROPIC_KEY=...` command from a much earlier session (Day 3) was still active in a long-lived terminal session. Since `load_dotenv()` does not override variables that already exist in the environment, every local test kept using an old, invalid key, despite `.env` itself being completely correct — producing a `401 AuthenticationError` that looked like a code or credential problem but was actually a shell-session artifact. Root-caused by systematically ruling out file location, save state, hidden characters, and key validity (confirmed valid via a direct `curl` call) before finding the real cause via `echo $ANTHROPIC_KEY` showing a stale value outside of Python entirely. Fixed with `unset ANTHROPIC_KEY` in the affected session; the underlying `.env` file was correct the whole time.

**4. Render's free-tier log dashboard does not display new lines in real time.** A request's `TRACE_LOG:` line was confirmed present and complete in the underlying log stream but did not appear in the dashboard's live view for roughly 30 minutes, only becoming visible after a later request triggered a flush. This means "watch a trace appear the instant a request completes" is not reliably demonstrable on the live dashboard, even though the trace-logging system itself is fully correct — every request is genuinely logged and searchable by ID, just not necessarily visible immediately. This is a platform log-delivery characteristic, not a bug in the trace code; the demo video accounts for this explicitly rather than implying real-time causality that can't actually be shown on camera.

**5. Real security incident, fully resolved.** While committing Day 2-6's work for the first time, GitHub's push protection blocked a commit containing a hardcoded Anthropic API key in an unrelated, unused file (`app.py`, leftover from earlier coursework, not part of NextStep). A second leftover file (`geocode.py`) had already been pushed with a hardcoded Google Maps key before this was caught. Both keys were treated as compromised regardless of public exposure status and rotated immediately; both leftover files were removed from the repository. `.gitignore` was audited and corrected in the same pass — it was missing `.env`, `.venv/`, and several runtime-data files entirely, a real gap that predated this incident and could have caused a worse one.

## Built during a 14-day FDE portfolio sprint

Each day's real decisions, bugs found and fixed (including at least one wrong fix caught by re-testing, and one real security incident — an exposed API key found by GitHub's push protection, fully resolved), and honest open items are documented in full in `docs/SPEC.md`, alongside `docs/resilience.md` for the Day 5 chaos-testing results.