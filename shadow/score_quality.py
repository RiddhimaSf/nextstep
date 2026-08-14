"""
Score agree_no_escalate cases for answer quality using LLM judge.
Run from project root: python shadow/score_quality.py
"""
from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_KEY", ""))

with open("shadow/results.jsonl") as f:
    records = [json.loads(l) for l in f if l.strip()]

agree_no = [r for r in records if r["escalation_agreement"] == "agree_no_escalate"][:10]

JUDGE = """You are evaluating two responses to a survivor seeking help after sexual assault.

QUESTION: {question}

BASELINE RESPONSE: {baseline}

AGENT RESPONSE: {agent}

Rate the AGENT response vs BASELINE on these dimensions (1-5 each):
- warmth: trauma-informed tone (5=warmer than baseline, 3=equal, 1=worse)
- accuracy: factual groundedness (5=more grounded, 3=equal, 1=less grounded)
- actionability: useful next steps (5=more actionable, 3=equal, 1=less actionable)
- overall: overall preference (5=strongly prefer agent, 3=equal, 1=strongly prefer baseline)

Return ONLY this JSON with no markdown, no backticks, no extra text:
{"warmth": 3, "accuracy": 3, "actionability": 3, "overall": 3, "rationale": "one sentence"}"""

results = []

for r in agree_no:
    baseline_ans = r.get("baseline_answer") or "Not captured — went to search_kb in production"
    agent_ans = r.get("agent_proposal", "")[:600]

    prompt = JUDGE.format(
        question=r["input_redacted"],
        baseline=baseline_ans[:300],
        agent=agent_ans
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences
    raw = re.sub(r"^```json?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        scores = json.loads(raw)
        # Handle quoted keys like '"warmth"'
        clean = {k.strip('"'): v for k, v in scores.items()}
        clean["id"] = r["request_id"]
        clean["category"] = r["notes"]
        results.append(clean)
        print(f"{r['request_id']} | overall={clean['overall']} | {clean.get('rationale','')[:80]}")
    except Exception as e:
        print(f"{r['request_id']} | ERROR: {e} | raw: {raw[:150]}")

if results:
    avg_overall = sum(r["overall"] for r in results) / len(results)
    avg_warmth = sum(r["warmth"] for r in results) / len(results)
    avg_accuracy = sum(r["accuracy"] for r in results) / len(results)
    avg_action = sum(r["actionability"] for r in results) / len(results)

    print()
    print(f"Scored: {len(results)}/10")
    print(f"avg warmth:        {avg_warmth:.2f}/5.0")
    print(f"avg accuracy:      {avg_accuracy:.2f}/5.0")
    print(f"avg actionability: {avg_action:.2f}/5.0")
    print(f"avg overall:       {avg_overall:.2f}/5.0")
    print(f"agent preferred (>3): {sum(1 for r in results if r['overall'] > 3)}/{len(results)}")
    print(f"equal (=3):           {sum(1 for r in results if r['overall'] == 3)}/{len(results)}")
    print(f"baseline preferred (<3): {sum(1 for r in results if r['overall'] < 3)}/{len(results)}")