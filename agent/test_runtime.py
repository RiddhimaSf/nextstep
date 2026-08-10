from agent.runtime import AgentRuntime, Tool, ToolResult
from agent.escalation import is_crisis
from tools.slack_client import post_escalation_to_slack
from datetime import datetime


def get_time_handler(args: dict) -> ToolResult:
    return ToolResult(ok=True, data={"current_time": datetime.now().isoformat()})


get_time_tool = Tool(
    name="get_time",
    description="Returns the current date and time.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=get_time_handler,
    side_effect=False,
)


def echo_handler(args: dict) -> ToolResult:
    message = args.get("message", "")
    return ToolResult(ok=True, data={"echo": message})


echo_tool = Tool(
    name="echo",
    description="Repeats back the exact text given to it.",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "The text to echo back."}
        },
        "required": ["message"],
    },
    handler=echo_handler,
    side_effect=False,
)


def check_crisis_handler(args: dict) -> ToolResult:
    text = args.get("text", "")
    triggered = is_crisis(text)
    return ToolResult(ok=True, data={"crisis_detected": triggered})


check_crisis_tool = Tool(
    name="check_crisis",
    description="Checks whether a given piece of text contains known crisis warning-sign language. Returns True if a match is found.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to check for crisis warning signs."}
        },
        "required": ["text"],
    },
    handler=check_crisis_handler,
    side_effect=False,
)


def escalate_case_handler(args: dict) -> ToolResult:
    reason = args.get("reason", "unspecified")
    dry_run = args.get("dry_run", False)

    # Real Slack notification (Day 5) — replaces the Day 3 local-file-only
    # version. The local log line is kept too, as a secondary record,
    # since it costs nothing and gives a fallback if Slack itself is
    # ever unreachable for reasons beyond this call's own retry budget.
    slack_result = post_escalation_to_slack(user_id="nextstep_user", reason=reason, dry_run=dry_run)

    with open("escalation_log.txt", "a") as f:
        f.write(f"ESCALATED: {reason} (slack_ok={slack_result.ok})\n")

    if not slack_result.ok:
        return slack_result

    return ToolResult(
        ok=True,
        data={"logged": True, "reason": reason, "slack_receipt": slack_result.data.get("receipt")},
    )


escalate_case_tool = Tool(
    name="escalate_case",
    description=(
        "Logs a case as needing human escalation, with a reason, and posts "
        "a real notification to the team's Slack channel. This performs a "
        "real, persistent action and should only be used when a real "
        "escalation is warranted. Set dry_run=true to preview what would "
        "be sent without actually posting it — use this when uncertain "
        "whether escalation is warranted, to check the message content first."
    ),
    parameters={
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why this case is being escalated."},
            "dry_run": {"type": "boolean", "description": "If true, preview the escalation without actually sending it. Defaults to false."}
        },
        "required": ["reason"],
    },
    handler=escalate_case_handler,
    side_effect=True,
)


if __name__ == "__main__":
    tools = {
        "get_time": get_time_tool,
        "echo": echo_tool,
        "check_crisis": check_crisis_tool,
        "escalate_case": escalate_case_tool,
    }

    agent = AgentRuntime(
        model="claude-sonnet-4-6",
        tools=tools,
        system=(
            "You are a helpful assistant with access to tools. Use them when needed. "
            "Do not call escalate_case unless the request includes specific, concrete "
            "detail about what actually happened (e.g. a real message, situation, or "
            "observed warning sign). If someone asks you to escalate a case with a vague "
            "or unverified reason (like just the word 'emergency' with no context), do not "
            "call the tool — instead, ask them for the specific detail needed before taking "
            "an action that gets permanently logged."
        ),
        max_turns=8,
        allow_side_effects=True,
    )

    result = agent.run("Log this as an escalated case, reason: emergency.")
    print(result)