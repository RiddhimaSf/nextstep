"""
Deterministic crisis escalation check.

This is a standalone version of the is_crisis() logic already running in
crisis.py, extracted into its own module so it can be tested independently
(see evals/golden.jsonl) and reused by the FastAPI agent layer.

Design principle: this check is a fixed, rule-based substring match — not
a model call, not a judgment made by Claude. It runs BEFORE any AI call,
as a hard gate: if it matches, the user sees crisis resources and Claude
is never invoked for that message. This is deliberate — the highest-risk
decision in the system does not depend on model inference.

Known limitation: substring matching only catches phrasings already in
this list. It cannot generalize to new phrasings the way a model could.
This list is expected to grow over time as real gaps are found (see
evals/golden.jsonl for the should-trigger / should-not-trigger test set
used to check coverage before any change to this file is deployed).
"""

CRISIS_TERMS = [
    # Original 22 terms from crisis.py
    "kill myself", "kill me", "end my life", "end it all", "want to die",
    "don't want to live", "dont want to live", "no reason to live",
    "no point in living", "suicidal", "suicide", "hurt myself",
    "harm myself", "self harm", "self-harm", "can't go on", "cant go on",
    "can't do this anymore", "cant do this anymore", "better off dead",
    "don't see the point", "dont see the point", "want to end",

    # Added from golden-set categories (AFSP: hopelessness, burden, unbearable pain)
    "never going to get better",
    "tired of dealing with my trauma",
    "can't take these emotions anymore",
    "cant take these emotions anymore",
]


def is_crisis(text: str) -> bool:
    """
    Returns True if any known crisis phrase is found in the input text.
    Case-insensitive substring match — same approach as the original
    crisis.py implementation, kept simple and auditable rather than
    replaced with a probabilistic model.
    """
    t = text.lower()
    return any(term in t for term in CRISIS_TERMS)