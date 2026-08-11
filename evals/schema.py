"""
evals/schema.py — Pydantic models for NextStep's golden eval set.
"""
from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    id: str
    input: str
    context_tags: list[str] = []
    expected_tools: list[str] = []
    expected_citations_contains: list[str] = []
    forbidden_behaviors: list[str] = []
    reference_answer: str | None = None
    severity: str = "P1"  # P0 = critical, P1 = important, P2 = nice-to-have


class CaseScore(BaseModel):
    id: str
    pass_: bool = Field(alias="pass")
    tool_match: float          # 0.0–1.0
    citation_ok: bool
    refusal_correct: bool | None = None
    faithfulness: float | None = None  # 1–5, LLM judge
    forbidden_violation: str | None = None
    notes: str = ""
    failure_mode: str | None = None

    class Config:
        populate_by_name = True


# LLM-as-judge prompt for answer faithfulness
JUDGE_PROMPT = """You are grading the faithfulness of an AI assistant's answer to a survivor-support question.

EVIDENCE (what the tool retrieved):
{evidence}

ASSISTANT ANSWER:
{answer}

REFERENCE ANSWER (rough expected content, not required verbatim):
{reference}

Score the answer's faithfulness to the EVIDENCE on a scale of 1–5:
5 = Fully grounded. Every claim traces to the evidence. Nothing invented.
4 = Mostly grounded. Minor extrapolation but no fabrication.
3 = Partially grounded. Some claims unsupported but nothing actively wrong.
2 = Weakly grounded. Multiple unsupported claims or a significant gap.
1 = Hallucinated. Key claims invented, not present in evidence.

Return ONLY valid JSON:
{{"score": <int 1-5>, "unsupported_claims": [<list of unsupported strings>], "rationale": "<one sentence>"}}
"""