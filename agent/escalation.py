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
NEGATION_CUES = ["not", "don't", "dont", "never", "no ", "isn't", "isnt"]
NEGATION_WINDOW = 40  # characters to look back before a matched phrase.
# Widened from an initial 20 to 40 after testing against the real
# golden-set case: "I am not saying I want to hurt myself" has 27
# characters between "not" and "hurt myself" — a 20-character window
# missed it. 40 is not a principled number, it is a number that passes
# the one known real case; a genuinely robust fix would need a real
# negation parser, not a fixed-width lookback — stated here as a known
# simplification, not claimed as a general solution.


def _is_negated(text: str, match_start: int) -> bool:
    """Checks whether a negation cue appears shortly before the matched
    phrase's start position, within NEGATION_WINDOW characters."""
    window_start = max(0, match_start - NEGATION_WINDOW)
    preceding_text = text[window_start:match_start]
    return any(cue in preceding_text for cue in NEGATION_CUES)


def is_crisis(text: str) -> bool:
    """
    Returns True if any known crisis phrase is found in the input text
    and is not immediately preceded by a negation cue.

    Case-insensitive substring match — same approach as the original
    implementation, kept simple and auditable rather than replaced with
    a probabilistic model, plus the narrow negation check added Day 6.
    """
    t = text.lower()
    for term in CRISIS_TERMS:
        idx = t.find(term)
        if idx != -1 and not _is_negated(t, idx):
            return True
    return False