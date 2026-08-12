from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
import json
import os
import time
import uuid
import anthropic


TRACE_LOG_PATH = "logs/traces.jsonl"


def persist_trace(request_id: str, user_msg: str, result: dict) -> None:
    """
    Standalone trace persistence, usable both by AgentRuntime.run() (the
    RAG/Q&A path, real tool-calling orchestration) and by deterministic
    paths outside the agent loop (e.g. crisis.py's crisis-escalation
    branch) that intentionally do NOT go through run(), since that
    decision must stay deterministic, not model-judgment-based — see
    Day 1 design principle. Both paths still get a real request ID and
    a real, replayable trace, closing the observability gap without
    forcing the deterministic safety path into the LLM loop it was
    deliberately built to avoid.

    Writes to logs/traces.jsonl AND prints to stdout with a "TRACE_LOG:"
    prefix — see the docstring history: the stdout copy exists because
    Render's free-tier filesystem is ephemeral, so the file alone does
    not survive a restart on the deployed instance, but Render's log
    viewer captures stdout regardless.
    """
    os.makedirs(os.path.dirname(TRACE_LOG_PATH), exist_ok=True)
    log_entry = {
        "request_id": request_id,
        "timestamp": time.time(),
        "user_msg": user_msg,
        "result": result,
    }
    log_line = json.dumps(log_entry)

    with open(TRACE_LOG_PATH, "a") as f:
        f.write(log_line + "\n")

    print(f"TRACE_LOG: {log_line}")


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error_code: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[[dict], ToolResult]
    side_effect: bool = False


@dataclass
class AgentRuntime:
    model: str
    tools: dict[str, Tool]
    system: str
    max_turns: int = 8
    allow_side_effects: bool = False

    def run(self, user_msg: str, request_id: str | None = None) -> dict:
        # Day 6: every run gets a unique, stable ID — generated here if the
        # caller didn't supply one, so ANY caller (crisis.py, test scripts,
        # a future FastAPI endpoint) automatically gets trace-replay
        # support without needing to duplicate ID-generation logic
        # themselves. A caller that already has an ID (e.g. an upstream
        # system tracing a request end-to-end) can pass it in instead.
        if request_id is None:
            request_id = str(uuid.uuid4())

        messages = [
            {"role": "user", "content": user_msg},
        ]
        trace = []
        tool_failure_counts = {}  # tracks consecutive failures per tool name

        for turn in range(self.max_turns):
            trace.append({"event": "turn_start", "turn": turn})

            t0 = time.time()
            response = self._call_model(messages)
            latency_ms = round((time.time() - t0) * 1000, 1)

            trace.append({
                "event": "llm_call",
                "turn": turn,
                "model": self.model,
                "latency_ms": latency_ms,
                "input_tokens": response.get("input_tokens"),
                "output_tokens": response.get("output_tokens"),
            })

            if response["type"] == "final_answer":
                trace.append({"event": "final", "turn": turn, "content": response["content"]})
                result = {"answer": response["content"], "trace": trace, "request_id": request_id}
                persist_trace(request_id, user_msg, result)
                return result

            elif response["type"] == "tool_call":
                tool_name = response["tool_name"]
                tool_args = response["tool_args"]
                tool_use_id = response["tool_use_id"]

                if response.get("capped_extra_calls", 0) > 0:
                    trace.append({
                        "event": "parallel_calls_capped",
                        "turn": turn,
                        "extra_calls_dropped": response["capped_extra_calls"],
                    })

                messages.append({"role": "assistant", "content": response["raw_content"]})

                if tool_name not in self.tools:
                    trace.append({"event": "tool_call", "turn": turn, "tool": tool_name, "args": tool_args, "error": "unknown_tool"})
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"Error: unknown tool '{tool_name}'",
                            "is_error": True,
                        }]
                    })
                    continue

                tool = self.tools[tool_name]

                validation_error = self._validate_args(tool, tool_args)
                if validation_error:
                    trace.append({"event": "tool_call", "turn": turn, "tool": tool_name, "args": tool_args, "error": "invalid_args", "detail": validation_error})
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"Error calling '{tool_name}': {validation_error}",
                            "is_error": True,
                        }]
                    })
                    continue

                if tool.side_effect and not self.allow_side_effects:
                    trace.append({"event": "tool_call", "turn": turn, "tool": tool_name, "args": tool_args, "error": "side_effect_blocked"})
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"Error: '{tool_name}' has side effects and is not currently allowed",
                            "is_error": True,
                        }]
                    })
                    continue

                t1 = time.time()
                result = tool.handler(tool_args)
                tool_latency_ms = round((time.time() - t1) * 1000, 1)

                trace.append({"event": "tool_call", "turn": turn, "tool": tool_name, "args": tool_args})
                trace.append({
                    "event": "tool_result",
                    "turn": turn,
                    "tool": tool_name,
                    "ok": result.ok,
                    "latency_ms": tool_latency_ms,
                    "error_code": result.error_code,
                })
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"ok": result.ok, "data": result.data, "error_code": result.error_code}),
                    }]
                })

                # Conversation-level recovery, code-enforced rather than
                # left to the model's judgment.
                if not result.ok:
                    tool_failure_counts[tool_name] = tool_failure_counts.get(tool_name, 0) + 1
                    if tool_failure_counts[tool_name] >= 2:
                        summary = (
                            f"The '{tool_name}' tool failed twice in a row "
                            f"(error: {result.error_code}). Rather than continue "
                            f"retrying, here's what's known and what to do next:\n\n"
                            f"- Failure reason: {result.error_code}"
                            + (f" — {result.data}" if result.data else "") + "\n"
                            f"- This may be a temporary issue (try again shortly) or "
                            f"may need a human to check the '{tool_name}' integration directly.\n"
                            f"- If this was an escalation attempt, please contact Safe Horizon's "
                            f"hotline directly at 1-800-621-4673 rather than waiting on this system."
                        )
                        trace.append({
                            "event": "conversation_recovery",
                            "turn": turn,
                            "tool": tool_name,
                            "consecutive_failures": tool_failure_counts[tool_name],
                            "reason": result.error_code,
                        })
                        result = {"answer": summary, "trace": trace, "recovered_from_failure": True, "request_id": request_id}
                        persist_trace(request_id, user_msg, result)
                        return result
                else:
                    tool_failure_counts[tool_name] = 0

        trace.append({"event": "max_turns_exceeded", "max_turns": self.max_turns})
        result = {"error": "max_turns_exceeded", "trace": trace, "request_id": request_id}
        persist_trace(request_id, user_msg, result)
        return result


    def _validate_args(self, tool: Tool, args: dict) -> str | None:
        required = tool.parameters.get("required", [])
        for field_name in required:
            if field_name not in args:
                return f"missing required field '{field_name}'"
        return None

    def _format_tools(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in self.tools.values()
        ]

    def _call_model(self, messages: list[dict]) -> dict:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_KEY", ""))
        response = client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=self.system,
            messages=messages,
            tools=self._format_tools(),
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        if response.stop_reason == "tool_use":
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_block = tool_blocks[0]
            kept_content = [b for b in response.content if b.type == "text"] + [tool_block]

            return {
                "type": "tool_call",
                "tool_name": tool_block.name,
                "tool_args": tool_block.input,
                "tool_use_id": tool_block.id,
                "raw_content": kept_content,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "capped_extra_calls": len(tool_blocks) - 1,
            }
        else:
            text_block = next(b for b in response.content if b.type == "text")
            return {
                "type": "final_answer",
                "content": text_block.text,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }


def get_trace(request_id: str) -> dict | None:
    """
    Day 6: the replay side of trace-replay. Given a request ID, scan the
    log file and return the matching entry, or None if it isn't found.
    A simple linear scan is fine at this scale — no index needed for a
    file that's realistically hundreds to low thousands of lines for a
    demo/portfolio project, matching the same right-sized reasoning as
    everything else in this file.
    """
    if not os.path.exists(TRACE_LOG_PATH):
        return None
    with open(TRACE_LOG_PATH, "r") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("request_id") == request_id:
                return entry
    return None


def print_trace(request_id: str) -> None:
    """Human-readable replay for interview use: paste an ID, see the
    full session printed back out."""
    entry = get_trace(request_id)
    if entry is None:
        print(f"No trace found for request_id: {request_id}")
        return

    print(f"=== Trace for request_id: {request_id} ===")
    print(f"Timestamp: {entry['timestamp']}")
    print(f"User message: {entry['user_msg']}\n")
    for event in entry["result"].get("trace", []):
        print(event)
    print(f"\nFinal result: {entry['result'].get('answer') or entry['result'].get('error')}")