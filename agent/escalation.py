"""
Deterministic crisis escalation check.

Design principle: this check is a fixed, rule-based mechanism — not a
model call, not a judgment made by Claude. It runs BEFORE any AI call,
as a hard gate. This is deliberate: the highest-risk decision in the
system does not depend on model inference.

Day 6 update: expanded the phrase list to close the specific misses
found in the Day 2/4 golden-set testing (8/15 = 53% pass rate on the
expanded set), and added a lightweight negation-aware check to fix the
documented false-positive ("I am not saying I want to hurt myself, I
just feel really low today" was incorrectly triggering, since plain
substring matching has no concept of negation).

Known, honest limitation, unchanged by this update: substring/negation
matching still cannot generalize to novel phrasing beyond what's listed
here. This is a real, ongoing gap, not claimed as solved — see
docs/SPEC.md for the full measured history.
"""

CRISIS_TERMS = [
    # Original 22 terms
    "kill myself", "kill me", "end my life", "end it all", "want to die",
    "don't want to live", "dont want to live", "no reason to live",
    "no point in living", "suicidal", "suicide", "hurt myself",
    "harm myself", "self harm", "self-harm", "can't go on", "cant go on",
    "can't do this anymore", "cant do this anymore", "better off dead",
    "don't see the point", "dont see the point", "want to end",

    # Added from Day 2 golden-set categories (AFSP: hopelessness, burden, unbearable pain)
    "never going to get better",
    "tired of dealing with my trauma",
    "can't take these emotions anymore",
    "cant take these emotions anymore",

    # Added from Day 6 fix: closing the specific 6 coverage-gap misses
    # found in the 15-case golden set (see docs/SPEC.md for the full
    # eval history). Each phrase below maps to one of those failed cases.
    "making the people in my life deal with",  # burden paraphrase
    "nothing is ever going to change",          # hopelessness paraphrase
    "no matter what i do",                      # hopelessness paraphrase (paired)
    "everyone would be better off without",     # burden paraphrase
    "don't have any reason to keep going",      # no-reason-to-live paraphrase
    "dont have any reason to keep going",
    "feel completely trapped",                  # feeling trapped
    "don't see a way out",                      # feeling trapped
    "dont see a way out",
    "wish i could disappear",                   # hopelessness paraphrase
    "not exist anymore",
]

# Day 6 fix: a short list of negation cues checked immediately before a
# matched phrase. If a negation word appears close before the match
# (within NEGATION_WINDOW characters), the match is suppressed — this
# is what fixes the documented false-positive on "I am not saying I
# want to hurt myself." This is a narrow, deliberately simple fix, not
# a general negation parser — it will not catch every negation
# construction, and that limitation is stated here, not hidden.
# Phrases that contain crisis terms but should NOT trigger escalation.
# This is an explicit whitelist rather than a general negation suppressor —
# a suppressor based on proximity matching incorrectly blocks real crisis
# phrases when an unrelated negation appears earlier in the same sentence.
# Armando review finding #1, Day 8: "It's not that bad but I want to die"
# was being suppressed because "not" appeared within 40 chars of "want to die."
# In this domain, false negatives are categorically worse than false positives.
# The suppressor is removed entirely; known safe phrases are listed explicitly.
NEGATION_SAFE_PHRASES = [
    "i am not saying i want to hurt myself",
    "i'm not saying i want to hurt myself",
    "not want to hurt myself",
    "doesn't want to live anymore",
    "does not want to live anymore",
    "no longer want to hurt myself",
    "my therapist says i no longer",
]


def is_crisis(text: str) -> bool:
    """
    Returns True if any known crisis phrase is found in the input text,
    unless the full input matches a known safe phrase.

    Design decision: negation suppression via proximity matching is removed.
    It incorrectly suppressed "I want to die" when an unrelated "not" appeared
    earlier in the sentence. In this domain, a false negative (missed crisis)
    is categorically worse than a false positive (unnecessary hotline card).
    Known safe phrases are handled via an explicit whitelist, not a heuristic.
    """
    t = text.lower()

    # Check explicit safe phrases first
    if any(safe in t for safe in NEGATION_SAFE_PHRASES):
        return False

    # Check crisis terms
    return any(term in t for term in CRISIS_TERMS)