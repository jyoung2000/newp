"""Job titles: what counts as a variation of the role someone asked for.

A user says they want a "Software Engineer". Boards will offer them "Software
Developer", "Sr. Software Engineer", "SWE II" and "Backend Engineer" — all the
same job — alongside "Engineering Manager" and "Sales Engineer", which are not.
Sources search their own way and some board connectors return an employer's
entire job list, so without a gate a saved role becomes a firehose.

The model is deliberately small and explainable, and it is *deterministic*:
scheduled discovery runs unattended every few minutes, so it cannot depend on a
model call, a network round-trip, or an API key.

A title is reduced to three things:

    "Sr. Backend Software Engineer II"
      level     = senior          (compared only when asked; a senior still
                                   wants to see the unprefixed role)
      head      = engineer        (the noun that decides what the job IS)
      modifiers = {backend, software}

Two titles match when their **heads** agree — an engineer is not a manager, no
matter how much else overlaps — and are scored on how far their modifiers
agree. That single rule is what keeps "Engineering Manager" out of a search for
"Software Engineer" while letting "Software Developer" in.

The synonym tables below are curated, not exhaustive, and they are not the last
word: expand() produces the variations for a role and the UI shows them for the
user to add to or remove, so a domain this file has never heard of is one edit
away rather than a dead end.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Titles below this score are not offered to the user for a given role.
TITLE_MATCH_THRESHOLD = 0.6

# --- Vocabulary --------------------------------------------------------------

# Expanded before anything else, longest first. Only unambiguous ones: "pm" is
# left alone precisely because it is both product and project manager, and
# guessing would quietly file the wrong jobs.
_ABBREVIATIONS: dict[str, str] = {
    "swe": "software engineer",
    "sde": "software engineer",
    "sdet": "software engineer in test",
    "sre": "site reliability engineer",
    "devops": "devops engineer",
    "qa": "quality assurance",
    "ba": "business analyst",
    "csr": "customer service representative",
    "cs": "customer support",
    "hr": "human resources",
    "rn": "registered nurse",
    "lpn": "licensed practical nurse",
    "cna": "certified nursing assistant",
    "cdl": "commercial driver",
    "sr": "senior",
    "snr": "senior",
    "jr": "junior",
    "eng": "engineer",
    "engr": "engineer",
    "dev": "developer",
    "mgr": "manager",
    "admin": "administrator",
    "asst": "assistant",
    "assoc": "associate",
    "rep": "representative",
    "tech": "technician",
    "acct": "accounting",
    "ops": "operations",
    "mktg": "marketing",
    "it": "information technology",
}

# Seniority, kept aside rather than dropped so it can be reported.
_LEVELS: dict[str, str] = {
    "senior": "senior", "staff": "staff", "principal": "principal", "lead": "lead",
    "head": "lead",
    "junior": "junior", "entry": "junior", "graduate": "junior", "trainee": "junior",
    "apprentice": "junior", "intern": "intern", "associate": "junior",
    "mid": "mid", "midlevel": "mid",
}

# Noise: employment shape, work model, and level numbering. None of it changes
# which job the title is.
_NOISE = {
    "remote", "hybrid", "onsite", "on", "site", "contract", "contractor", "temporary",
    "temp", "permanent", "perm", "fulltime", "full", "parttime", "part", "time",
    "freelance", "seasonal", "casual", "urgent", "hiring", "now", "immediate",
    "opening", "opportunity", "job", "role", "position", "career", "wanted", "needed",
    "new", "the", "a", "an", "and", "or", "of", "for", "in", "at", "with", "to",
    "i", "ii", "iii", "iv", "v", "1", "2", "3", "4", "5", "level",
}

# Head nouns that mean the same job. The key is the canonical family.
_HEAD_FAMILIES: dict[str, set[str]] = {
    "engineer": {"engineer", "developer", "programmer", "coder", "dev", "tester"},
    "manager": {"manager", "supervisor", "foreman"},
    "analyst": {"analyst"},
    "scientist": {"scientist"},
    "designer": {"designer"},
    "architect": {"architect"},
    "administrator": {"administrator", "admin"},
    "technician": {"technician", "tech", "mechanic"},
    "specialist": {"specialist", "generalist"},
    "coordinator": {"coordinator", "scheduler"},
    "representative": {"representative", "agent", "advisor", "adviser"},
    "assistant": {"assistant", "aide"},
    "consultant": {"consultant"},
    "accountant": {"accountant", "bookkeeper"},
    "nurse": {"nurse"},
    "teacher": {"teacher", "instructor", "tutor", "educator"},
    "writer": {"writer", "editor", "copywriter"},
    "recruiter": {"recruiter"},
    "driver": {"driver"},
    "clerk": {"clerk", "cashier"},
    "cook": {"cook", "chef"},
    "director": {"director"},
    "executive": {"chief", "vp", "president", "officer", "cto", "ceo", "cfo", "coo"},
    "operator": {"operator"},
    "planner": {"planner"},
    "auditor": {"auditor"},
    "paralegal": {"paralegal"},
    "pharmacist": {"pharmacist"},
    "therapist": {"therapist"},
    "welder": {"welder"},
    "electrician": {"electrician"},
    "plumber": {"plumber"},
    "carpenter": {"carpenter"},
}
_HEAD_LOOKUP: dict[str, str] = {
    word: family for family, words in _HEAD_FAMILIES.items() for word in words
}

# Modifier synonyms — the domain words in front of the head noun. Grouping
# these is what lets "Backend Engineer" match a search for "Software Engineer"
# without letting "Sales Engineer" in.
_MODIFIER_FAMILIES: dict[str, set[str]] = {
    "software": {
        "software", "engineering", "backend", "back", "frontend", "front", "fullstack", "full",
        "stack", "web", "application", "applications", "app", "platform", "systems",
        "system", "api", "server", "client", "mobile", "ios", "android",
    },
    "data": {"data", "analytics", "database", "bi", "warehouse", "etl"},
    "machinelearning": {"ml", "machine", "learning", "ai", "artificial", "intelligence", "nlp"},
    "infrastructure": {
        "infrastructure", "infra", "devops", "cloud", "reliability", "site",
        "kubernetes", "network", "networking",
    },
    "security": {"security", "cyber", "infosec", "appsec"},
    "product": {"product"},
    "project": {"project", "program", "programme", "delivery"},
    "sales": {"sales", "account", "business", "revenue"},
    "marketing": {"marketing", "brand", "growth", "seo", "content", "social"},
    "support": {"support", "service", "customer", "success", "help", "desk", "helpdesk"},
    "finance": {"finance", "financial", "accounting", "payroll", "tax", "treasury"},
    "people": {"people", "hr", "human", "resources", "talent", "recruiting", "recruitment"},
    "operations": {"operations", "ops", "logistics", "supply", "chain", "warehouse"},
    "quality": {"quality", "qa", "assurance", "test", "testing", "sdet"},
    "legal": {"legal", "compliance", "regulatory", "counsel"},
    "healthcare": {
        "clinical", "medical", "health", "healthcare", "patient", "nursing",
        "registered", "licensed", "practical", "certified",
    },
    "education": {"education", "teaching", "academic", "curriculum"},
    "design": {"design", "ux", "ui", "user", "experience", "interface", "graphic", "visual"},
    "research": {"research", "scientific"},
}
_MODIFIER_LOOKUP: dict[str, str] = {
    word: family for family, words in _MODIFIER_FAMILIES.items() for word in words
}

_SPLIT = re.compile(r"[^a-z0-9+#]+")
_PARENTHETICAL = re.compile(r"\([^)]*\)")


@dataclass(frozen=True)
class TitleShape:
    """A title reduced to the parts that decide whether two are the same job."""

    raw: str
    level: str | None
    head: str | None
    modifiers: frozenset[str]
    # Content words after normalisation, before family mapping. Used as a
    # tiebreaker and for titles with no recognisable head noun.
    words: tuple[str, ...]

    @property
    def recognised(self) -> bool:
        return self.head is not None


def _words(title: str) -> list[str]:
    text = _PARENTHETICAL.sub(" ", (title or "").lower())
    out: list[str] = []
    for token in _SPLIT.split(text):
        if not token:
            continue
        # Multi-word expansions ("swe" -> "software engineer") land as words.
        expanded = _ABBREVIATIONS.get(token, token)
        out.extend(expanded.split())
    return out


def shape(title: str) -> TitleShape:
    """Reduce a title to level + head + modifiers."""
    words = _words(title)
    level: str | None = None
    content: list[str] = []
    for word in words:
        if word in _LEVELS:
            # First seniority word wins: "Senior Staff Engineer" is senior.
            level = level or _LEVELS[word]
            continue
        if word in _NOISE:
            continue
        content.append(word)

    head: str | None = None
    head_at = -1
    # The head noun is the last recognised one: "engineering manager" is a
    # manager, "manager of engineering" is also a manager.
    for i in range(len(content) - 1, -1, -1):
        family = _HEAD_LOOKUP.get(content[i])
        if family is not None:
            head, head_at = family, i
            break

    modifiers: set[str] = set()
    for i, word in enumerate(content):
        if i == head_at:
            continue
        family = _MODIFIER_LOOKUP.get(word)
        # An unrecognised word is still a modifier — it just has no family, so
        # it only matches itself. Better than discarding the one word that
        # distinguishes two roles.
        modifiers.add(family or word)

    return TitleShape(
        raw=(title or "").strip(),
        level=level,
        head=head,
        modifiers=frozenset(modifiers),
        words=tuple(content),
    )


def score(wanted: str | TitleShape, candidate: str | TitleShape) -> float:
    """How well `candidate` matches the role `wanted`, from 0.0 to 1.0."""
    a = wanted if isinstance(wanted, TitleShape) else shape(wanted)
    b = candidate if isinstance(candidate, TitleShape) else shape(candidate)

    if not a.words or not b.words:
        return 0.0

    # Neither title has a head noun this module knows ("Roustabout", "Sommelier").
    # Fall back to word overlap so unknown domains still work, rather than
    # matching nothing at all.
    if a.head is None or b.head is None:
        sa, sb = set(a.words), set(b.words)
        if sa == sb:
            return 1.0
        overlap = len(sa & sb)
        if not overlap:
            return 0.0
        return round(0.6 * overlap / max(len(sa), len(sb)) + 0.3, 3)

    # Different job. An engineer is not a manager, however much else agrees.
    if a.head != b.head:
        return 0.0

    if a.modifiers == b.modifiers:
        return 1.0
    if not a.modifiers:
        # "Engineer" was asked for; "Software Engineer" is one.
        return 0.9
    if not b.modifiers:
        # "Software Engineer" was asked for; a bare "Engineer" posting is
        # plausible but vaguer.
        return 0.8
    if a.modifiers <= b.modifiers:
        return 0.9
    if b.modifiers <= a.modifiers:
        return 0.8
    shared = a.modifiers & b.modifiers
    if shared:
        return round(0.6 + 0.3 * len(shared) / len(a.modifiers | b.modifiers), 3)
    # Same head, unrelated domains: "Sales Engineer" for "Software Engineer".
    # Deliberately below the threshold — the user can add it as its own role.
    return 0.4


def best_match(wanted_titles: list[str], candidate: str) -> tuple[str | None, float]:
    """The wanted title this listing best answers, and the score."""
    best: tuple[str | None, float] = (None, 0.0)
    candidate_shape = shape(candidate)
    for title in wanted_titles:
        if not title or not title.strip():
            continue
        value = score(shape(title), candidate_shape)
        if value > best[1]:
            best = (title, value)
    return best


def matches(wanted_titles: list[str], candidate: str, threshold: float = TITLE_MATCH_THRESHOLD) -> bool:
    return best_match(wanted_titles, candidate)[1] >= threshold


def expand(title: str, limit: int = 6) -> list[str]:
    """Readable variations of a role, for the user to see and edit and for the
    sources to search on.

    Shown in the UI, so these are phrases a person would recognise as the same
    job — not the internal families.
    """
    base = shape(title)
    if not base.words:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(text: str) -> None:
        key = " ".join(_words(text))
        if not key or key in seen:
            return
        seen.add(key)
        out.append(text)

    # The title as given always comes first — it is what the user typed.
    add((title or "").strip())

    if base.head is not None:
        # The modifier words as the user wrote them, so the variation reads
        # naturally rather than as canonical families.
        head_word_at = None
        for i in range(len(base.words) - 1, -1, -1):
            if _HEAD_LOOKUP.get(base.words[i]) is not None:
                head_word_at = i
                break
        prefix = " ".join(base.words[:head_word_at]) if head_word_at else ""
        # Alternative head nouns from the same family, most common first.
        for synonym in sorted(_HEAD_FAMILIES[base.head], key=lambda w: (len(w), w)):
            if synonym in ("dev", "admin", "tech"):  # abbreviations, not titles
                continue
            add(f"{prefix} {synonym}".strip())

    return out[:limit]
