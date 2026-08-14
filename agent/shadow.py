"""
agent/shadow.py — shadow mode infrastructure for NextStep.

Shadow mode runs the agent on real or realistic traffic with ALL write
tools disabled (allow_side_effects=False), logging what the agent WOULD
have done alongside what the baseline system actually does.

Zero side effects: no Slack messages are posted, no escalation keys are
written, no external state is modified. Reads (search_kb, is_crisis check)
stay live.

Key design decision: in NextStep's architecture, the crisis check runs
BEFORE the agent is ever called. Shadow mode intentionally routes crisis
inputs THROUGH the agent anyway — this measures what Claude would have said
if the deterministic layer hadn't intercepted it first. That comparison is
the core finding: it validates (or challenges) the decision to keep the
deterministic check rather than trusting the model's judgment.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.runtime import ToolResult

# ── PII redaction ─────────────────────────────────────────────────────────────

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

def redact(text: str) -> str:
    """
    Redact PII from text before logging or committing.
    Covers: email addresses, US phone numbers, SSNs.
    This is a best-effort redaction for a demo deployment —
    not a certified PII scrubber. Real production would use
    a dedicated service (AWS Comprehend, Google DLP, etc.).
    """
    if not isinstance(text, str):
        return text
    text = _EMAIL.sub("[EMAIL]", text)
    text = _PHONE.sub("[PHONE]", text)
    text = _SSN.sub("[SSN]", text)
    return text


def redact_record(record: dict) -> dict:
    """Recursively redact all string values in a dict."""
    result = {}
    for k, v in record.items():
        if isinstance(v, str):
            result[k] = redact(v)
        elif isinstance(v, dict):
            result[k] = redact_record(v)
        elif isinstance(v, list):
            result[k] = [
                redact_record(item) if isinstance(item, dict)
                else redact(item) if isinstance(item, str)
                else item
                for item in v
            ]
        else:
            result[k] = v
    return result


# ── Shadow record ─────────────────────────────────────────────────────────────

@dataclass
class ShadowRecord:
    request_id: str
    input_redacted: str           # redacted user input
    input_hash: str               # SHA-256 hash of original input
    baseline_action: str          # what the production system did
    baseline_answer: str          # what the production system showed the user
    agent_proposal: str           # what the shadow agent would have answered
    agent_would_escalate: bool    # would the agent have escalated?
    baseline_escalated: bool      # did the production system escalate?
    escalation_agreement: str     # "agree", "agent_missed", "agent_over"
    agent_trace: list             # full structured trace from shadow run
    would_write: bool             # did the agent attempt any write tools?
    latency_ms: float
    cost_usd: float | None = None
    notes: str = ""


# ── Write tool wrapper ────────────────────────────────────────────────────────

def wrap_write_tool(handler):
    """
    Wraps a write tool handler so it returns a shadow receipt
    instead of executing. The intended payload is logged so the
    diff is visible, but nothing actually fires.
    """
    def shadowed(args: dict) -> ToolResult:
        return ToolResult(
            ok=True,
            data={
                "shadow": True,
                "intended_args": args,
                "note": "write not executed in shadow mode",
            }
        )
    return shadowed


# ── Baseline function ─────────────────────────────────────────────────────────

def baseline_response(input_text: str) -> dict:
    """
    Simulates what the production system (crisis.py) actually does:
    1. Run is_crisis() deterministically
    2. If crisis: show crisis resources, post to Slack (silently)
    3. If not: run AgentRuntime.run() with search_kb

    In shadow mode we don't actually call the Slack API or show
    UI — we just record what the production system WOULD have done.
    """
    from agent.escalation import is_crisis

    if is_crisis(input_text):
        return {
            "action": "crisis_escalation",
            "answer": "crisis_resources_shown",
            "escalated": True,
        }
    else:
        return {
            "action": "rag_query",
            "answer": None,  # would be filled by AgentRuntime.run()
            "escalated": False,
        }
