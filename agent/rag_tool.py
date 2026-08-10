"""
Wraps rag.retrieve.search_kb as a Tool for AgentRuntime (agent/runtime.py),
following the same pattern as Day 3's get_time/echo/check_crisis/escalate_case.
"""

from agent.runtime import Tool, ToolResult
from rag.retrieve import search_kb, best_score_below_threshold


def search_kb_handler(args: dict) -> ToolResult:
    query = args.get("query", "")
    k = args.get("k", 6)
    filters = args.get("filters", None)

    results = search_kb(query, k=k, filters=filters)

    # Code-enforced check (not left to Claude's judgment) — the
    # deterministic half of the INSUFFICIENT_CONTEXT rule from Day 4
    # design phase. The score threshold is checked here, in code, before
    # Claude ever sees the results, rather than hoping the model notices
    # a low score on its own.
    if best_score_below_threshold(results):
        return ToolResult(
            ok=True,
            data={
                "results": results,
                "insufficient_context": True,
                "reason": "Best retrieval score is below the confidence threshold.",
            },
        )

    return ToolResult(
        ok=True,
        data={"results": results, "insufficient_context": False},
    )


search_kb_tool = Tool(
    name="search_kb",
    description=(
        "Searches NextStep's knowledge base (hospitals, legal resources, "
        "financial assistance, mental health resources, safe places) for "
        "information relevant to a survivor's question. Returns ranked "
        "results with citation IDs. Use optional filters like "
        "{\"borough\": \"Brooklyn\"} or {\"category\": \"financial\"} to "
        "narrow results when the question specifies a location or topic."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up in the knowledge base."
            },
            "k": {
                "type": "integer",
                "description": "How many results to return. Defaults to 6 if not specified."
            },
            "filters": {
                "type": "object",
                "description": "Optional metadata filters, e.g. {\"borough\": \"Brooklyn\"} or {\"category\": \"financial\"}."
            }
        },
        "required": ["query"]
    },
    handler=search_kb_handler,
    side_effect=False,
)


# System prompt fragment — citation-or-refuse rule, per Day 4 brief.
# Note: this is the MODEL-LEVEL half of the rule (citations, and
# recognizing conflicting chunks). The score-threshold half is already
# code-enforced above (insufficient_context flag), not left to the model.
GROUNDING_PROMPT = """
You have access to search_kb, which searches NextStep's real knowledge base.

Rules for using retrieved information:
- Answer ONLY using information returned by search_kb. Never answer factual
  questions about hospitals, legal processes, financial assistance, or
  resources from your own general knowledge.
- For every factual claim you make from a retrieved chunk, cite it inline
  using the exact citation format returned by the tool, like
  [hospital_directory#bellevue_hospital_center].
- If search_kb returns insufficient_context: true, do not attempt to answer
  from memory. Respond with exactly: INSUFFICIENT_CONTEXT: <a brief
  description of what information is missing>, then suggest the survivor
  contact Safe Horizon's hotline (1-800-621-4673) for help a search
  couldn't answer. Do NOT name any other specific organization, hotline
  number, or resource in this situation unless it came from a search_kb
  result — even if you believe you know a correct one. Safe Horizon's
  hotline is the only fallback you are permitted to name from memory,
  because it is verified NextStep content, not because you are otherwise
  free to supplement with general knowledge. If the question is outside
  NextStep's scope entirely (e.g. a different city, a different type of
  crime), say so plainly instead of offering an out-of-scope resource by
  name.
- NextStep currently only supports English. This is not a stylistic
  choice — the crisis-escalation safety check only recognizes English
  warning-sign phrases, so responding in another language could mean a
  real crisis message goes undetected by that check. If asked to respond
  in a different language, do not comply. Explain, in English, that
  NextStep currently only supports English, and that this is a safety
  limitation, not just a missing feature, so it is not something you can
  make an exception for even if asked directly.
- If two or more retrieved chunks genuinely conflict on the same specific
  fact (not just different topics — an actual contradiction about the same
  thing), do not pick one arbitrarily. Respond with
  INSUFFICIENT_CONTEXT: conflicting information found, and note what
  the conflict is about.
- Never invent a citation, a phone number, an address, or a policy detail
  that did not come from a search_kb result.
"""