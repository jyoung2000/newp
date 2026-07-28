"""Question normalization: turns raw form-field labels into stable keys so a
question answered once is recognized forever, across ATSes and wording
variants."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_BOILERPLATE = re.compile(
    r"\b(please|kindly|note|required|optional|if applicable|if any|select one|"
    r"choose one|check all that apply|e\.?g\.?|i\.?e\.?)\b",
    re.IGNORECASE,
)
_LEADING_NUMBERING = re.compile(r"^\s*(?:q(?:uestion)?\s*)?\d+[\).:\-]\s*", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9{}\s]")
_WS = re.compile(r"\s+")


def normalize_question(
    text: str, company: str | None = None, location: str | None = None
) -> str:
    """Produce the canonical key for a question.

    Company and location names are replaced with placeholders so
    "Have you worked for Acme before?" and "Have you worked for Globex
    before?" normalize to the same key.
    """
    s = text.strip()
    s = _LEADING_NUMBERING.sub("", s)
    if company:
        s = re.sub(re.escape(company), "{company}", s, flags=re.IGNORECASE)
    if location:
        s = re.sub(re.escape(location), "{location}", s, flags=re.IGNORECASE)
    s = s.lower()
    s = _BOILERPLATE.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s[:400]


def similarity(a: str, b: str) -> float:
    """Similarity between two normalized keys: sequence ratio blended with
    token-set overlap, so word-order changes don't defeat the match."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    token = len(ta & tb) / max(len(ta | tb), 1)
    return max(seq, 0.4 * seq + 0.6 * token)


def label_similarity(question: str, short_label: str) -> float:
    """Similarity tuned for short user-defined labels ("T-shirt size")
    matched against full question sentences ("What is your t-shirt size?").
    A multi-token label fully contained in the question is a strong match."""
    base = similarity(question, short_label)
    tokens = short_label.split()
    if len(tokens) >= 2 and set(tokens) <= set(question.split()):
        return max(base, 0.95)
    return base


FUZZY_MATCH_THRESHOLD = 0.87
