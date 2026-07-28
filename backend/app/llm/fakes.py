"""Deterministic offline implementations of every LLM task.

Used when LLM_DRY_RUN=1 (tests, demos without an API key). These are honest
heuristics, not mocks-of-convenience: they follow the same contract as the
real prompts — never invent data, never answer knockouts without evidence.
"""
from __future__ import annotations

import re

from app.llm.schemas import (
    DraftAnswer,
    FieldMapping,
    KnockoutClassification,
    ListingEnrichment,
    ParsedContact,
    ParsedEducation,
    ParsedExperience,
    ParsedResume,
    ParsedSkill,
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?:\+?\d{1,2}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}")
_URL = re.compile(r"https?://[^\s)>\]]+")

KNOCKOUT_PATTERNS: list[tuple[str, str]] = [
    (r"authoriz|legally.*work|right to work|work permit", "authorization"),
    (r"sponsor", "sponsorship"),
    (r"certif|licen[cs]e", "certification"),
    (r"clearance", "clearance"),
    (r"(\d+)\+?\s*(?:or more\s*)?years", "years_threshold"),
    (r"shift|weekend|night|on.?call|availab", "shift"),
    (r"18|age of|minimum age|at least .* old", "age"),
]

EEO_PATTERNS = [
    r"\bgender\b",
    r"race|ethnicit",
    r"veteran",
    r"disabilit",
    r"self.?identif",
]


def fake_parse_resume(resume_text: str) -> ParsedResume:
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    email = _EMAIL.search(resume_text)
    phone = _PHONE.search(resume_text)
    urls = _URL.findall(resume_text)
    first = last = None
    if lines:
        head = lines[0].split()
        if 1 < len(head) <= 4 and not _EMAIL.search(lines[0]):
            first, last = head[0], head[-1]
    linkedin = next((u for u in urls if "linkedin.com" in u), None)
    github = next((u for u in urls if "github.com" in u), None)

    experiences: list[ParsedExperience] = []
    for m in re.finditer(
        r"^(?P<title>[^\n@]{3,80})\s+(?:@|at)\s+(?P<company>[^\n(]{2,60})"
        r"(?:\s*\((?P<start>\d{4}(?:-\d{2})?)\s*[-–]\s*(?P<end>\d{4}(?:-\d{2})?|present)\))?",
        resume_text,
        re.MULTILINE | re.IGNORECASE,
    ):
        end = m.group("end")
        experiences.append(
            ParsedExperience(
                title=m.group("title").strip(),
                company=m.group("company").strip(),
                start_date=m.group("start"),
                end_date=None if (end or "").lower() == "present" else end,
                is_current=(end or "").lower() == "present",
            )
        )

    educations: list[ParsedEducation] = []
    for m in re.finditer(
        r"(?P<degree>B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|MBA|Ph\.?D\.?|Bachelor[^,\n]*|Master[^,\n]*)"
        r"[^,\n]*,\s*(?P<school>[^\n,]{3,80})",
        resume_text,
    ):
        educations.append(
            ParsedEducation(degree=m.group("degree").strip(), school=m.group("school").strip())
        )

    skills: list[ParsedSkill] = []
    skills_match = re.search(r"skills?\s*[:\n]\s*(.{3,300})", resume_text, re.IGNORECASE)
    if skills_match:
        for token in re.split(r"[,;•|]", skills_match.group(1)):
            token = token.strip()
            if 1 < len(token) <= 40:
                years_m = re.search(r"\((\d+(?:\.\d+)?)\s*(?:yrs?|years?)\)", token)
                name = re.sub(r"\(.*?\)", "", token).strip()
                if name:
                    skills.append(
                        ParsedSkill(
                            name=name, years=float(years_m.group(1)) if years_m else None
                        )
                    )

    return ParsedResume(
        contact=ParsedContact(
            first_name=first,
            last_name=last,
            email=email.group(0) if email else None,
            phone=phone.group(0) if phone else None,
            linkedin_url=linkedin,
            github_url=github,
        ),
        work_experiences=experiences,
        educations=educations,
        skills=skills,
    )


def _keywords(text: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "you", "our", "are", "will", "have", "this",
        "that", "your", "from", "not", "all", "can", "who", "what", "their",
    }
    return {
        w for w in re.findall(r"[a-zA-Z+#.]{3,}", text.lower()) if w not in stop
    }


def fake_enrich(listing_text: str, profile_context: str) -> ListingEnrichment:
    listing_kw = _keywords(listing_text)
    profile_kw = _keywords(profile_context)
    overlap = listing_kw & profile_kw
    score = 0
    if listing_kw:
        score = min(100, int(140 * len(overlap) / max(len(listing_kw), 1)))
    requirements = []
    for m in re.finditer(
        r"^[\s•*-]*((?:\d+\+?\s*years?|experience|proficien|degree|knowledge of|familiarity)[^\n]{0,120})",
        listing_text,
        re.IGNORECASE | re.MULTILINE,
    ):
        requirements.append(m.group(1).strip())
    education = None
    lowered = listing_text.lower()
    for needle, level in [
        ("phd", "doctorate"), ("doctorate", "doctorate"), ("master", "master"),
        ("bachelor", "bachelor"), ("associate", "associate"), ("high school", "high_school"),
    ]:
        if needle in lowered:
            education = level
            break
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", listing_text).strip())
    summary = " ".join(sentences[:3])[:400] or "No description provided."
    shared = ", ".join(sorted(overlap)[:4]) or "no overlapping skills found"
    return ListingEnrichment(
        summary=summary,
        requirements=requirements[:8],
        education_level=education,
        match_score=score,
        match_rationale=f"Profile overlap on: {shared}.",
    )


def classify_knockout_heuristic(question: str) -> KnockoutClassification:
    lowered = question.lower()
    for pattern, category in KNOCKOUT_PATTERNS:
        if re.search(pattern, lowered):
            return KnockoutClassification(
                is_knockout=True, category=category, rationale=f"Matched {category} pattern"
            )
    return KnockoutClassification(is_knockout=False, category=None, rationale="No knockout pattern")


def is_eeo_heuristic(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(p, lowered) for p in EEO_PATTERNS)


def fake_map_field(label: str, options: list[str], context: str) -> FieldMapping:
    """Conservative fake mapper: exact key:value lookups from the context
    block only. The context is 'key: value' lines built by the resolver."""
    knockout = classify_knockout_heuristic(label)
    eeo = is_eeo_heuristic(label)
    if eeo:
        return FieldMapping(
            matched_key=None, value=None, option_match=None, confidence=0.0,
            is_knockout=knockout.is_knockout, is_eeo=True,
            rationale="EEO fields are filled only from explicit profile choices",
        )
    label_kw = _keywords(label)
    best_key, best_value, best_score = None, None, 0.0
    for line in context.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not value or value.lower() in ("none", "null", ""):
            continue
        kw = _keywords(key.replace("_", " "))
        if not kw:
            continue
        score = len(label_kw & kw) / max(len(kw), 1)
        if score > best_score:
            best_key, best_value, best_score = key, value, score
    if best_key is None or best_score < 0.5:
        return FieldMapping(
            matched_key=None, value=None, option_match=None, confidence=0.2,
            is_knockout=knockout.is_knockout, is_eeo=False,
            rationale="No stored data matches this field",
        )
    option_match = None
    if options:
        for opt in options:
            if opt.strip().lower() == str(best_value).strip().lower():
                option_match = opt
                break
        if option_match is None and isinstance(best_value, str) and best_value.lower() in ("yes", "no", "true", "false"):
            truthy = best_value.lower() in ("yes", "true")
            for opt in options:
                if (truthy and opt.strip().lower().startswith("yes")) or (
                    not truthy and opt.strip().lower().startswith("no")
                ):
                    option_match = opt
                    break
        if option_match is None:
            return FieldMapping(
                matched_key=best_key, value=None, option_match=None, confidence=0.3,
                is_knockout=knockout.is_knockout, is_eeo=False,
                rationale="Stored value does not correspond to any offered option",
            )
    return FieldMapping(
        matched_key=best_key,
        value=str(best_value),
        option_match=option_match,
        confidence=min(0.95, 0.6 + 0.35 * best_score),
        is_knockout=knockout.is_knockout,
        is_eeo=False,
        rationale=f"Matched stored field '{best_key}'",
    )


def fake_draft(question: str, context: str) -> DraftAnswer:
    facts = [
        line.strip() for line in context.splitlines() if ":" in line and line.split(":", 1)[1].strip()
    ][:5]
    body = (
        "Drawing on my background — "
        + "; ".join(f.split(":", 1)[1].strip() for f in facts[:3])
        + f" — here is my answer to '{question[:80]}'. "
        "[Dry-run draft: review and edit before use.]"
    )
    return DraftAnswer(text=body, facts_used=facts)
