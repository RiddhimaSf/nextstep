"""
evals/test_runtime_guards.py — unit tests for AgentRuntime policy guards.

These tests mock the LLM call entirely — no API calls, no credits consumed.
Same technique as Day 3's test_guards.py, now formalized as a proper test
module with pytest so they can run in CI alongside the eval gate.

Run:
    pytest evals/test_runtime_guards.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch
import pytest
from agent.runtime import AgentRuntime, Tool, ToolResult


# ── Shared fixtures ───────────────────────────────────────────────────────────

def make_agent(tools=None, allow_side_effects=False, max_turns=4):
    return AgentRuntime(
        model="claude-sonnet-4-6",
        tools=tools or {},
        system="test",
        max_turns=max_turns,
        allow_side_effects=allow_side_effects,
    )


def fake_tool_call(tool_name: str, args: dict, tool_use_id: str = "fake_id") -> dict:
    """Simulates a model response that calls a specific tool."""
    return {
        "type": "tool_call",
        "tool_name": tool_name,
        "tool_args": args,
        "tool_use_id": tool_use_id,
        "raw_content": [{"type": "tool_use", "id": tool_use_id,
                          "name": tool_name, "input": args}],
        "input_tokens": 10,
        "output_tokens": 5,
        "capped_extra_calls": 0,
    }


def fake_final(content: str = "done") -> dict:
    """Simulates a model response that produces a final answer."""
    return {
        "type": "final_answer",
        "content": content,
        "input_tokens": 10,
        "output_tokens": 5,
    }


echo_tool = Tool(
    name="echo",
    description="Echoes the input",
    parameters={
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
    handler=lambda args: ToolResult(ok=True, data=args.get("message")),
    side_effect=False,
)

write_tool = Tool(
    name="write_record",
    description="Writes a record (has side effects)",
    parameters={
        "type": "object",
        "properties": {"data": {"type": "string"}},
        "required": ["data"],
    },
    handler=lambda args: ToolResult(ok=True, data="written"),
    side_effect=True,
)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_unknown_tool_blocked():
    """Calling a tool not in the registry should not crash — it should
    return an error to the model and continue the loop."""
    agent = make_agent(tools={"echo": echo_tool})
    responses = [
        fake_tool_call("nonexistent_tool", {}),
        fake_final("recovered"),
    ]
    with patch.object(AgentRuntime, "_call_model", side_effect=responses):
        result = agent.run("call unknown tool")
    assert result["answer"] == "recovered"
    events = [e["event"] for e in result["trace"]]
    assert "tool_call" in events
    # Confirm the error was logged in the trace
    tool_events = [e for e in result["trace"] if e.get("event") == "tool_call"]
    assert any(e.get("error") == "unknown_tool" for e in tool_events)


def test_missing_required_args_blocked():
    """Calling a tool without its required args should return an error,
    not crash or call the handler with missing data."""
    agent = make_agent(tools={"echo": echo_tool})
    responses = [
        fake_tool_call("echo", {}),  # missing required 'message' field
        fake_final("recovered after bad args"),
    ]
    with patch.object(AgentRuntime, "_call_model", side_effect=responses):
        result = agent.run("call echo with no args")
    assert result["answer"] == "recovered after bad args"
    tool_events = [e for e in result["trace"] if e.get("event") == "tool_call"]
    assert any(e.get("error") == "invalid_args" for e in tool_events)


def test_side_effects_blocked_when_disabled():
    """A tool with side_effect=True must be blocked when
    allow_side_effects=False — the handler must never be called."""
    called = {"n": 0}
    def handler(args):
        called["n"] += 1
        return ToolResult(ok=True, data="written")

    blocked_write = Tool(
        name="write_record",
        description="write",
        parameters={"type": "object", "properties": {"data": {"type": "string"}},
                    "required": ["data"]},
        handler=handler,
        side_effect=True,
    )
    agent = make_agent(tools={"write_record": blocked_write}, allow_side_effects=False)
    responses = [
        fake_tool_call("write_record", {"data": "test"}),
        fake_final("blocked"),
    ]
    with patch.object(AgentRuntime, "_call_model", side_effect=responses):
        result = agent.run("write something")
    assert called["n"] == 0, "Handler must never be called when side effects are blocked"
    tool_events = [e for e in result["trace"] if e.get("event") == "tool_call"]
    assert any(e.get("error") == "side_effect_blocked" for e in tool_events)


def test_side_effects_allowed_when_enabled():
    """A tool with side_effect=True must be called when
    allow_side_effects=True."""
    called = {"n": 0}
    def handler(args):
        called["n"] += 1
        return ToolResult(ok=True, data="written")

    write = Tool(
        name="write_record",
        description="write",
        parameters={"type": "object", "properties": {"data": {"type": "string"}},
                    "required": ["data"]},
        handler=handler,
        side_effect=True,
    )
    agent = make_agent(tools={"write_record": write}, allow_side_effects=True)
    responses = [
        fake_tool_call("write_record", {"data": "test"}),
        fake_final("written successfully"),
    ]
    with patch.object(AgentRuntime, "_call_model", side_effect=responses):
        result = agent.run("write something")
    assert called["n"] == 1, "Handler must be called when side effects are allowed"
    assert result["answer"] == "written successfully"


def test_max_turns_exceeded():
    """When the loop hits max_turns without a final answer, it must
    return max_turns_exceeded — not hang or crash."""
    agent = make_agent(tools={"echo": echo_tool}, max_turns=3)
    # Always return a tool call — never a final answer
    always_tool = fake_tool_call("echo", {"message": "hello"})
    with patch.object(AgentRuntime, "_call_model", return_value=always_tool):
        result = agent.run("keep calling tools forever")
    assert "error" in result
    assert result["error"] == "max_turns_exceeded"
    events = [e["event"] for e in result["trace"]]
    assert "max_turns_exceeded" in events