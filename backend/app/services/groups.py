"""Repeating groups on an application form: employment history and references.

The flat field library answers questions about *the applicant*: your email, your
phone, your years of experience. An application form's employment-history and
reference sections ask the same questions about *other people and other jobs*,
several times over:

    Employer 2 — Company ▸ Supervisor ▸ Phone ▸ Dates ▸ Reason for leaving
    Reference 1 — Name ▸ Relationship ▸ Company ▸ Email ▸ Phone

Two things go wrong without a layer like this one. The obvious one is that all
of it stops and asks the user, on every application, for facts they already
entered. The quieter one is worse: `Reference 1 email` matches the flat
library's `e-?mail` pattern, so the applicant's own address would be typed into
someone else's box. Group detection therefore runs *before* the flat library,
and a field it claims is never offered to the flat patterns.

Two rules keep it honest:

1. **Evidence, not guesswork.** A field is only treated as belonging to a group
   when its own label or name says so, or when its surrounding block does. If
   the attribute inside the group can't be identified, the field falls through
   to the human rather than being filled with something adjacent.
2. **Index by evidence, then by order.** `employer[1][company]` and
   "Reference #3" carry their own index. Unnumbered repeats (three identical
   reference blocks) are numbered by the order they appear in the form, which
   is why assign_indices() takes the whole batch of fields at once.

"Employer 1" is the top of the user's list in Profile → Work, which the UI
tells them is their most recent role.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models import Recommendation, WorkExperience
from app.services.field_library import BuiltinAnswer

EMPLOYER = "employer"
REFERENCE = "reference"

# --- Which group does this field belong to? ---------------------------------
# "referral"/"referred by" is how-did-you-hear, NOT a reference — the \b and
# the explicit exclusion below keep them apart.
_EMPLOYER_MARKERS = re.compile(
    r"employ(?:er|ment)|work\s*history|job\s*history|previous\s+(?:job|position|employer)"
    r"|prior\s+employ|position\s+held|work\s+experience",
    re.IGNORECASE,
)
_REFERENCE_MARKERS = re.compile(
    r"\breference(?:s)?\b(?!\s*(?:number|no\b|id\b|code))|\breferee\b",
    re.IGNORECASE,
)
# Says the field is about the applicant themselves. Only consulted for
# attributes that could plausibly be either (see _AMBIGUOUS_WITH_APPLICANT):
# "your duties" and "your supervisor" are group fields, "your email" is not.
_SELF_MARKERS = re.compile(
    r"\byour\b|\bapplicant\b|\bcandidate\b|\bmy\b", re.IGNORECASE
)

# Attributes whose flat-library counterpart is about the applicant, so a
# mis-detection here writes one person's details into another's box.
_AMBIGUOUS_WITH_APPLICANT: dict[str, set[str]] = {
    EMPLOYER: {"location"},
    REFERENCE: {"name", "email", "phone", "title", "company"},
}
# A contact field inside an employment block belongs to the supervisor — but
# only if it says so. Unattributed, it is the user's to fill rather than ours
# to guess, and it must not fall through to the "address" branch of `location`.
_BARE_CONTACT = re.compile(r"e-?mail|\bphone\b|\btel\b|\bmobile\b|\bcell\b", re.IGNORECASE)
_MANAGER_MARKER = re.compile(r"supervisor|manager|\bboss\b", re.IGNORECASE)


def _norm(text: str | None) -> str:
    """Separators that HTML name attributes use, flattened to spaces.

    `work_history[1][company]` and `reference_3_phone` have no word boundary
    before an underscore and no whitespace between words, so the markers below
    never match them raw. Bracketed indices are read from the raw text first,
    because normalising them away loses the 0-based convention."""
    return re.sub(r"[_\-./\[\]]+", " ", text or "").strip()

# --- Which attribute within the group? --------------------------------------
# Order matters: the supervisor patterns must be tried before the bare
# name/phone/email ones, or "Supervisor email" resolves to the company's.
_EMPLOYER_ATTRS: list[tuple[str, re.Pattern[str]]] = [
    ("manager_email", re.compile(r"(?:supervisor|manager|boss).{0,20}e-?mail|e-?mail.{0,20}(?:supervisor|manager)", re.I)),
    ("manager_phone", re.compile(r"(?:supervisor|manager|boss).{0,20}(?:phone|tel|number|contact)|(?:phone|tel).{0,20}(?:supervisor|manager)", re.I)),
    ("manager_title", re.compile(r"(?:supervisor|manager).{0,20}(?:title|position|job title)", re.I)),
    ("manager_name", re.compile(r"supervisor|manager|\bboss\b|reported to|report(?:ed)?\s+to\s+whom", re.I)),
    ("may_contact_employer", re.compile(r"(?:may|can|ok(?:ay)?|permission)\s+(?:we\s+)?contact|contact\s+this\s+employer|contact\s+(?:your|the)\s+(?:current\s+)?employer", re.I)),
    ("reason_for_leaving", re.compile(r"reason\s+for\s+(?:leaving|leave|separation)|why\s+(?:did|are)\s+you\s+leav|reason\s+for\s+departure|cause\s+of\s+leaving", re.I)),
    ("is_current", re.compile(r"current(?:ly)?\s+(?:employed|work)|present\s+employer|still\s+(?:employed|work)", re.I)),
    ("start_date", re.compile(r"\b(?:start|from|began|commenc|hired?|employed\s+from|date\s+started)\b", re.I)),
    ("end_date", re.compile(r"\b(?:end(?:ed|ing)?|to|until|through|left|last\s+day|date\s+ended|separation\s+date)\b", re.I)),
    ("summary", re.compile(r"(?:duties|responsibilit|describe|description|summary|what\s+did\s+you\s+do|accomplish|job\s+duties)", re.I)),
    ("title", re.compile(r"(?:job\s*title|position(?:\s+title)?|\btitle\b|\brole\b)", re.I)),
    ("location", re.compile(r"\b(?:city|town|location|address|state)\b", re.I)),
    ("company", re.compile(r"(?:company|employer|organi[sz]ation|firm|business)(?:\s*name)?|\bname\s+of\s+(?:company|employer)", re.I)),
]

_REFERENCE_ATTRS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"e-?mail", re.I)),
    ("phone", re.compile(r"phone|\btel\b|mobile|cell|contact\s*number", re.I)),
    ("years_known", re.compile(r"(?:how\s+long|years?)\s+(?:have\s+you\s+)?known|length\s+of\s+acquaintance|years\s+acquainted", re.I)),
    ("may_contact", re.compile(r"(?:may|can|ok(?:ay)?|permission)\s+(?:we\s+)?contact", re.I)),
    ("relationship_to_user", re.compile(r"relationship|how\s+do\s+you\s+know|association|capacity", re.I)),
    ("company", re.compile(r"company|employer|organi[sz]ation|where\s+(?:do|does)\s+(?:they|he|she)\s+work", re.I)),
    ("title", re.compile(r"(?:job\s*)?title|position|occupation", re.I)),
    ("name", re.compile(r"\bname\b", re.I)),
]

# --- Index markers ----------------------------------------------------------
# Bracketed indices are 0-based (`employer[0]`, the array the form posts);
# everything a human reads is 1-based ("Employer 1", `employer_1_company`).
_BRACKET_INDEX = re.compile(r"\[\s*(\d{1,2})\s*\]")
_SUFFIX_INDEX = re.compile(r"(?:^|[^a-z0-9])(\d{1,2})(?:[^a-z0-9]|$)", re.IGNORECASE)
_WORD_ORDINALS = {
    "first": 0, "1st": 0, "most recent": 0, "current": 0, "latest": 0,
    "second": 1, "2nd": 1, "next": 1,
    "third": 2, "3rd": 2,
    "fourth": 3, "4th": 3,
    "fifth": 4, "5th": 4,
}
_ORDINAL_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in _WORD_ORDINALS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@dataclass
class GroupField:
    """A field identified as belonging to a repeating group."""

    kind: str  # EMPLOYER | REFERENCE
    attribute: str
    # None when nothing in the field said which one — filled in by
    # assign_indices() from the order the fields appear in the form.
    index: int | None = None


def _index_from(text: str) -> int | None:
    if not text:
        return None
    # Brackets are read before normalisation: `employer[0]` is the array the
    # form posts, so it is 0-based, while anything a person typed is 1-based.
    bracket = _BRACKET_INDEX.search(text)
    if bracket:
        return int(bracket.group(1))
    flat = _norm(text)
    ordinal = _ORDINAL_RE.search(flat)
    if ordinal:
        return _WORD_ORDINALS[ordinal.group(1).lower()]
    digits = _SUFFIX_INDEX.search(flat)
    if digits:
        value = int(digits.group(1))
        return value - 1 if value >= 1 else 0
    return None


def _attribute(kind: str, label: str, name: str) -> str | None:
    table = _EMPLOYER_ATTRS if kind == EMPLOYER else _REFERENCE_ATTRS
    if kind == EMPLOYER and _BARE_CONTACT.search(label) and not _MANAGER_MARKER.search(
        f"{label} {name}"
    ):
        return None
    # The label is what a person reads, so it decides first; the name attribute
    # is the fallback for fields whose label is an icon or is missing.
    for haystack in (label, _norm(name)):
        if not haystack:
            continue
        for attribute, pattern in table:
            if pattern.search(haystack):
                return attribute
    return None


def detect(label: str, name: str | None, surrounding_text: str = "") -> GroupField | None:
    """Identify a repeating-group field, or return None to let the flat field
    library have it."""
    label = (label or "").strip()
    name = (name or "").strip()
    own_text = f"{label} {name}"
    own_flat = _norm(own_text)

    kind: str | None = None
    index: int | None = None
    weak = False

    # Strongest evidence: the field's own label or name.
    if _REFERENCE_MARKERS.search(own_flat):
        kind = REFERENCE
    elif _EMPLOYER_MARKERS.search(own_flat):
        kind = EMPLOYER
    if kind:
        index = _index_from(own_text)

    # Weaker but common: the block around it says so. A form does not put the
    # applicant's own details inside a fieldset headed "References", and the
    # attribute still has to be identifiable for this to resolve.
    if kind is None and surrounding_text:
        if _REFERENCE_MARKERS.search(surrounding_text):
            kind = REFERENCE
        elif _EMPLOYER_MARKERS.search(surrounding_text):
            kind = EMPLOYER
        if kind:
            weak = True
            # Take an index from the block heading if it has one ("Reference 2"),
            # but not from the field's own text, which has none.
            index = _index_from(surrounding_text)

    if kind is None:
        return None
    attribute = _attribute(kind, label, name)
    if attribute is None:
        return None
    # Only the block said this was a group, and the attribute is one the
    # applicant also has — so a label naming the applicant settles it. This is
    # the "Your email address" in a compact employment form case; "your duties"
    # and "your supervisor" are unaffected, being unambiguous either way.
    if weak and attribute in _AMBIGUOUS_WITH_APPLICANT[kind] and _SELF_MARKERS.search(label):
        return None
    return GroupField(kind=kind, attribute=attribute, index=index)


def assign_indices(detected: list[GroupField | None]) -> None:
    """Number the groups that didn't say which one they were, in place.

    A form with three identical reference blocks gives every field the same
    label and no index. Their order on the page is the only thing that
    distinguishes them, so the Nth occurrence of a given (kind, attribute) is
    the Nth entry. Pass the whole form's fields in document order.
    """
    seen: dict[tuple[str, str], int] = {}
    for item in detected:
        if item is None:
            continue
        key = (item.kind, item.attribute)
        if item.index is None:
            item.index = seen.get(key, 0)
        # Track the highest index used for this attribute so a later unnumbered
        # field lands after an explicitly numbered one rather than on top of it.
        seen[key] = max(seen.get(key, 0), item.index + 1)


# --- Turning a group field into an answer ------------------------------------


def _text(value: Any) -> BuiltinAnswer | None:
    if value is None or value == "":
        return None
    return BuiltinAnswer(value=str(value))


def _bool(value: bool | None) -> BuiltinAnswer | None:
    # None means the user has not answered. A "may we contact this employer?"
    # question is not something to default.
    if value is None:
        return None
    return BuiltinAnswer(value=value, kind="boolean")


def _date(value: Any) -> BuiltinAnswer | None:
    if value is None:
        return None
    return BuiltinAnswer(
        value=value.isoformat(), kind="date", formatted=value.strftime("%m/%d/%Y")
    )


def _employer_answer(job: WorkExperience, attribute: str) -> BuiltinAnswer | None:
    if attribute == "company":
        return _text(job.company)
    if attribute == "title":
        return _text(job.title)
    if attribute == "location":
        return _text(job.location)
    if attribute == "start_date":
        return _date(job.start_date)
    if attribute == "end_date":
        # A job the user still holds has no end date, and "Present" is what the
        # form wants rather than a blank or an invented date.
        if job.is_current:
            return BuiltinAnswer(value="Present", formatted="Present")
        return _date(job.end_date)
    if attribute == "is_current":
        return _bool(job.is_current)
    if attribute == "manager_name":
        return _text(job.manager_name)
    if attribute == "manager_title":
        return _text(job.manager_title)
    if attribute == "manager_email":
        return _text(job.manager_email)
    if attribute == "manager_phone":
        return _text(job.manager_phone)
    if attribute == "may_contact_employer":
        return _bool(job.may_contact_employer)
    if attribute == "reason_for_leaving":
        return _text(job.reason_for_leaving)
    if attribute == "summary":
        # Prose if the user wrote it; otherwise the bullets read as sentences,
        # which is better than leaving a required box empty.
        if job.summary:
            return _text(job.summary)
        if job.bullets:
            return _text(". ".join(b.rstrip(".") for b in job.bullets if b) + ".")
        return None
    return None


def _reference_answer(ref: Recommendation, attribute: str) -> BuiltinAnswer | None:
    if attribute == "name":
        return _text(ref.name)
    if attribute == "title":
        return _text(ref.title)
    if attribute == "company":
        return _text(ref.company)
    if attribute == "relationship_to_user":
        return _text(ref.relationship_to_user)
    if attribute == "email":
        # `contact` was the old combined box; fall back to it so references
        # entered before the split still answer an email field.
        if ref.email:
            return _text(ref.email)
        if ref.contact and "@" in ref.contact:
            return _text(ref.contact)
        return None
    if attribute == "phone":
        if ref.phone:
            return _text(ref.phone)
        if ref.contact and "@" not in ref.contact:
            return _text(ref.contact)
        return None
    if attribute == "years_known":
        if ref.years_known is None:
            return None
        return BuiltinAnswer(value=ref.years_known, kind="number")
    if attribute == "may_contact":
        return _bool(ref.may_contact)
    return None


def resolve(
    group: GroupField,
    work_experiences: list[WorkExperience],
    references: list[Recommendation],
) -> BuiltinAnswer | None:
    """The answer for this group field, or None when there is nothing to say —
    the entry doesn't exist, or the user hasn't filled that part in. None sends
    the field to the human, which is the right outcome either way."""
    index = group.index or 0
    if group.kind == EMPLOYER:
        if index >= len(work_experiences):
            return None
        return _employer_answer(work_experiences[index], group.attribute)
    if group.kind == REFERENCE:
        if index >= len(references):
            return None
        return _reference_answer(references[index], group.attribute)
    return None


def describe(group: GroupField) -> str:
    """For the resolution's `reason`, so a user reviewing a fill can see which
    entry a value came from."""
    which = (group.index or 0) + 1
    noun = "employer" if group.kind == EMPLOYER else "reference"
    return f"From {noun} {which} in your profile ({group.attribute.replace('_', ' ')})"
