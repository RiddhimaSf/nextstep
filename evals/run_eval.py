from agent.escalation import is_crisis
import json

def load_golden_set(path):
    cases = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    return cases

print("DEBUG: file is running")

def run_eval(path):
    cases = load_golden_set(path)
    print(f"DEBUG: loaded {len(cases)} cases")
    passed = 0
    failed = []
    skipped = 0

    for case in cases:
        if case["type"] == "escalation":
            result = is_crisis(case["message"])
            expected = case["should_trigger"]
            if result == expected:
                passed += 1
            else:
                failed.append(case)
        elif case["type"] == "qa":
            skipped += 1

    print(f"Escalation cases passed: {passed}")
    print(f"Escalation cases failed: {len(failed)}")
    for case in failed:
        print(f"  FAILED: {case['message']} (expected should_trigger={case['should_trigger']})")
    print(f"QA cases skipped (not yet testable — RAG not built): {skipped}")

if __name__ == "__main__":
    run_eval("evals/golden.jsonl")