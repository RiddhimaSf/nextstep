"""
Slack integration for real escalation notifications, replacing the local
escalation_log.txt file write from Day 3 with a real, resilient call to
Slack's chat.postMessage API.
"""

import os
from tools.http_client import ResilientClient, idempotency_key
from agent.runtime import ToolResult

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")

# Idempotency keys are persisted to a local file, not just kept in memory.
# An in-memory set only survives for the lifetime of one Python process —
# real testing on Day 5 confirmed this the hard way: running the same
# escalation twice as two separate `python -c` commands produced two
# real Slack messages, because each command started a fresh process with
# an empty in-memory set. A file-based store survives across runs, which
# is what real idempotency requires. Still a simplified stand-in for a
# proper database in true production, but a real fix, not just documented
# as a known limitation, since this was directly testable and fixable
# today.
_SENT_KEYS_FILE = "sent_escalation_keys.txt"


def _load_sent_keys() -> set:
    if not os.path.exists(_SENT_KEYS_FILE):
        return set()
    with open(_SENT_KEYS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def _mark_key_sent(key: str) -> None:
    with open(_SENT_KEYS_FILE, "a") as f:
        f.write(key + "\n")


def post_escalation_to_slack(user_id: str, reason: str, dry_run: bool = False) -> ToolResult:
    payload = {"reason": reason}
    key = idempotency_key(user_id, "escalate_case", payload)

    if key in _load_sent_keys():
        return ToolResult(
            ok=True,
            data={"receipt": "Already escalated (duplicate call prevented)", "idempotency_key": key},
        )

    message_text = f":rotating_light: *Escalation* from user `{user_id}`\nReason: {reason}"

    if dry_run:
        return ToolResult(
            ok=True,
            data={
                "receipt": f"[DRY RUN] Would post to Slack: {message_text}",
                "idempotency_key": key,
                "dry_run": True,
            },
        )

    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        return ToolResult(
            ok=False,
            error_code="AUTH",
            data="SLACK_BOT_TOKEN or SLACK_CHANNEL_ID not set in environment",
        )

    # Deliberately smaller retry budget than ResilientClient's default,
    # found necessary via chaos testing (Day 5) — the default 4-attempt,
    # 15s-timeout budget could take 15-23+ seconds on a genuine network
    # failure, badly violating the Day 2 p95 latency SLO on the one tool
    # where speed matters most. An earlier attempt at this fix mistakenly
    # RAISED the timeout (3.0 -> 5.0) instead of lowering it, making the
    # problem worse (15.6s -> 23.6s) — caught by re-testing after the
    # "fix," not assumed correct. Corrected here with real arithmetic:
    # 2 attempts x 2s timeout + ~0.5s backoff between them = ~4.5s worst
    # case, safely under the 10s SLO, at the cost of fewer retries than
    # the general-purpose default — an explicit tradeoff, not an oversight.
    client = ResilientClient(base_url="https://slack.com/api", token=SLACK_BOT_TOKEN, timeout=2.0, max_attempts=2)
    result = client.request(
        "POST",
        "/chat.postMessage",
        json={"channel": SLACK_CHANNEL_ID, "text": message_text},
    )

    if not result.ok:
        return result

    # Slack's API returns HTTP 200 even for some logical failures (e.g.
    # invalid channel) — the real success/failure signal is inside the
    # JSON body's "ok" field, not just the HTTP status code. This is a
    # Slack-specific quirk worth checking explicitly rather than trusting
    # the HTTP layer alone.
    if not result.data or not result.data.get("ok"):
        error_detail = result.data.get("error") if result.data else "unknown"
        # Slack returns HTTP 200 even for logical failures, including auth
        # problems — the real error lives in the JSON body's "error" field,
        # not the HTTP status code, so http_client.py's status-code-based
        # AUTH check never sees it. Found via a real chaos test (Day 5):
        # an invalid token produced error_code=VALIDATION instead of AUTH,
        # which would mislead anyone debugging or building recovery logic
        # around error_code. Explicitly reclassifying Slack's known
        # auth-related error strings here, rather than leaving every
        # logical failure lumped under one generic code.
        SLACK_AUTH_ERRORS = {"invalid_auth", "not_authed", "account_inactive", "token_revoked", "token_expired"}
        if error_detail in SLACK_AUTH_ERRORS:
            return ToolResult(False, error_code="AUTH", data=f"Slack API error: {error_detail}")
        return ToolResult(False, error_code="VALIDATION", data=f"Slack API error: {error_detail}")

    _mark_key_sent(key)
    ts = result.data.get("ts", "unknown")
    return ToolResult(
        ok=True,
        data={"receipt": f"Posted to Slack (message ts: {ts})", "idempotency_key": key},
    )