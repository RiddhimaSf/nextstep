"""
Deterministic guard tests.

These tests mock AgentRuntime._call_model so we can FORCE specific model
behaviors — a tool call with missing args, or a tool that keeps failing
forever — rather than hoping Claude happens to misbehave in the exact way
needed to exercise a guard. This is a standard, honest testing technique:
it tests OUR guard logic in isolation, not the LLM's judgment. The live
scenarios in manual_scenarios.md (checking real Claude behavior, like the
refusal case) are a separate, complementary kind of test — this file
proves the code-level guards fire correctly, deterministically, every
time, regardless of what the model would naturally choose to do.

Run with: python -m agent.test_guards
"""

from unittest.mock import patch
from agent.runtime import AgentRuntime, Tool, ToolResult


# --- Scenario 3 (real this time): force echo to be called with no args ---

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


def test_invalid_args_guard():
    print("\n=== Scenario 3: forced invalid_args ===")

    # Fake a Claude response that calls echo with NO "message" field —
    # something the real model tends to avoid by asking a clarifying
    # question first, so we force it here instead of hoping it happens.
    fake_tool_call_response = {
        "type": "tool_call",
        "tool_name": "echo",
        "tool_args": {},  # missing required "message"
        "tool_use_id": "fake_id_1",
        "raw_content": [{"type": "tool_use", "id": "fake_id_1", "name": "echo", "input": {}}],
        "input_tokens": 42,
        "output_tokens": 8,
    }
    fake_final_response = {
        "type": "final_answer",
        "content": "I couldn't complete that — the message field was missing.",
        "input_tokens": 55,
        "output_tokens": 12,
    }

    agent = AgentRuntime(
        model="claude-sonnet-4-6",
        tools={"echo": echo_tool},
        system="test",
        max_turns=3,
    )

    # First call returns the bad tool call, second call (after the guard
    # rejects it and Claude "sees" the error) returns a final answer.
    with patch.object(AgentRuntime, "_call_model", side_effect=[fake_tool_call_response, fake_final_response]):
        result = agent.run("echo something")

    print(result)

    invalid_args_events = [e for e in result["trace"] if e.get("error") == "invalid_args"]
    assert len(invalid_args_events) == 1, "Expected exactly one invalid_args event"
    assert invalid_args_events[0]["detail"] == "missing required field 'message'"
    print(">>> PASS: invalid_args guard fired correctly, with real trace event:")
    print(invalid_args_events[0])


# --- Scenario 6: a tool that always fails, proving max_turns terminates cleanly ---

def flaky_handler(args: dict) -> ToolResult:
    return ToolResult(ok=False, data=None, error_code="upstream_unavailable")


flaky_tool = Tool(
    name="flaky_tool",
    description="A tool that always fails, used only to test max_turns behavior.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=flaky_handler,
    side_effect=False,
)


def test_max_turns_terminates():
    print("\n=== Scenario 6: forced infinite retry, proving max_turns stops it ===")

    # Force the model to request flaky_tool on every single turn, no matter
    # what — simulating a model stuck retrying a failing tool forever.
    always_retry_response = {
        "type": "tool_call",
        "tool_name": "flaky_tool",
        "tool_args": {},
        "tool_use_id": "fake_id_retry",
        "raw_content": [{"type": "tool_use", "id": "fake_id_retry", "name": "flaky_tool", "input": {}}],
        "input_tokens": 30,
        "output_tokens": 5,
    }

    agent = AgentRuntime(
        model="claude-sonnet-4-6",
        tools={"flaky_tool": flaky_tool},
        system="test",
        max_turns=4,  # deliberately small so the test runs fast
    )

    # Every single call to _call_model returns the same retry request —
    # this is the actual infinite-retry failure mode named in the Day 3 brief.
    with patch.object(AgentRuntime, "_call_model", return_value=always_retry_response):
        result = agent.run("do the flaky thing")

    print(result)

    assert result.get("error") == "max_turns_exceeded", "Expected the loop to terminate via max_turns, not hang or crash"
    tool_result_events = [e for e in result["trace"] if e.get("event") == "tool_result"]
    assert len(tool_result_events) == 4, f"Expected exactly 4 tool attempts (max_turns), got {len(tool_result_events)}"
    print(f">>> PASS: loop attempted the failing tool exactly {len(tool_result_events)} times, then stopped cleanly via max_turns — it did not loop forever.")


if __name__ == "__main__":
    test_invalid_args_guard()
    test_max_turns_terminates()
    print("\nAll guard tests passed.")