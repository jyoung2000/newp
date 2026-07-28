"""High-level LLM tasks. Each function builds the prompt, calls the client
(or the deterministic fake in dry-run mode) and returns a validated object."""
from __future__ import annotations

from app.llm import fakes, prompts
from app.llm.client import get_llm
from app.llm.schemas import (
    DraftAnswer,
    FieldMapping,
    KnockoutClassification,
    ListingEnrichment,
    ParsedResume,
)


def parse_resume(resume_text: str) -> ParsedResume:
    llm = get_llm()
    if llm.dry_run:
        return fakes.fake_parse_resume(resume_text)
    return llm.parse(
        system=prompts.RESUME_PARSE_SYSTEM,
        prompt=prompts.resume_parse_prompt(resume_text),
        output_type=ParsedResume,
        max_tokens=16000,
    )


def enrich_listing(listing_text: str, profile_context: str) -> ListingEnrichment:
    llm = get_llm()
    if llm.dry_run:
        return fakes.fake_enrich(listing_text, profile_context)
    return llm.parse(
        system=prompts.ENRICH_SYSTEM,
        prompt=prompts.enrich_prompt(listing_text, profile_context),
        output_type=ListingEnrichment,
        max_tokens=2048,
    )


def map_field(
    label: str,
    field_type: str,
    options: list[str],
    surrounding_text: str,
    context: str,
) -> FieldMapping:
    llm = get_llm()
    if llm.dry_run:
        return fakes.fake_map_field(label, options, context)
    field_meta = (
        f"Label: {label}\nType: {field_type}\n"
        f"Options: {options if options else 'n/a'}\n"
        f"Surrounding text: {surrounding_text[:500]}"
    )
    return llm.parse(
        system=prompts.MAP_FIELD_SYSTEM,
        prompt=prompts.map_field_prompt(field_meta, context),
        output_type=FieldMapping,
        max_tokens=1024,
    )


def classify_knockout(question: str, options: list[str] | None = None) -> KnockoutClassification:
    # Heuristics run first everywhere (cheap, deterministic); the LLM is a
    # second opinion for questions the patterns don't catch.
    heuristic = fakes.classify_knockout_heuristic(question)
    if heuristic.is_knockout:
        return heuristic
    llm = get_llm()
    if llm.dry_run:
        return heuristic
    return llm.parse(
        system=prompts.KNOCKOUT_SYSTEM,
        prompt=prompts.knockout_prompt(question, options),
        output_type=KnockoutClassification,
        max_tokens=512,
    )


def draft_answer(question: str, context: str, listing_context: str) -> DraftAnswer:
    llm = get_llm()
    if llm.dry_run:
        return fakes.fake_draft(question, context)
    return llm.parse(
        system=prompts.DRAFT_SYSTEM,
        prompt=prompts.draft_prompt(question, context, listing_context),
        output_type=DraftAnswer,
        max_tokens=2048,
    )
