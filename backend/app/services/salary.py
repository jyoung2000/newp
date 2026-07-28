"""Salary parsing: turns the wild variety of salary strings on job listings
into (min, max, currency, period) or an honest 'not listed'."""
from __future__ import annotations

import re
from dataclasses import dataclass

CURRENCY_SYMBOLS = {
    "$": "USD", "us$": "USD", "usd": "USD",
    "£": "GBP", "gbp": "GBP",
    "€": "EUR", "eur": "EUR",
    "c$": "CAD", "cad": "CAD", "ca$": "CAD",
    "a$": "AUD", "aud": "AUD", "au$": "AUD",
    "chf": "CHF", "sek": "SEK", "nok": "NOK", "dkk": "DKK",
    "inr": "INR", "₹": "INR", "jpy": "JPY", "¥": "JPY", "pln": "PLN", "zł": "PLN",
}

_PERIOD_PATTERNS = [
    (r"(?:per\s+|/\s*|an?\s+)h(?:ou)?r", "hour"),
    (r"hourly", "hour"),
    (r"(?:per\s+|/\s*|a\s+)day", "day"),
    (r"(?:per\s+|/\s*|a\s+)week", "week"),
    (r"(?:per\s+|/\s*|a\s+)month", "month"),
    (r"monthly", "month"),
    (r"(?:per\s+|/\s*|an?\s+)(?:year|annum|yr)", "year"),
    (r"annual|yearly|p\.?a\.?\b", "year"),
]

# Separator-grouped numbers first ("120,000" / "120.000"), then plain digits
# ("100000" / "18.50") — the order prevents "100000" splitting into 100 + 000.
_AMOUNT = re.compile(
    r"(?P<currency>[$£€¥₹]|us\$|c\$|a\$|ca\$|au\$|usd|gbp|eur|cad|aud|chf|inr|sek|nok|dkk|jpy|pln)?\s*"
    r"(?P<number>\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<suffix>k|K)?",
    re.IGNORECASE,
)


@dataclass
class ParsedSalary:
    minimum: int | None = None
    maximum: int | None = None
    currency: str | None = None
    period: str | None = None
    raw: str | None = None

    @property
    def listed(self) -> bool:
        return self.minimum is not None or self.maximum is not None


def _to_amount(number: str, suffix: str | None) -> float:
    # "120,000" / "120.000" (eu thousands) / "120 000" / "120.5"
    cleaned = number.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", cleaned):
        cleaned = cleaned.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(",", "")
    value = float(cleaned)
    if suffix and suffix.lower() == "k":
        value *= 1000
    return value


def parse_salary(text: str | None) -> ParsedSalary:
    if not text or not text.strip():
        return ParsedSalary()
    raw = re.sub(r"\s+", " ", text.strip())[:300]
    lowered = raw.lower()
    if any(marker in lowered for marker in ("not listed", "not specified", "undisclosed", "competitive salary")):
        return ParsedSalary(raw=raw)

    period = None
    for pattern, name in _PERIOD_PATTERNS:
        if re.search(pattern, lowered):
            period = name
            break

    amounts: list[tuple[float, str | None]] = []
    for m in _AMOUNT.finditer(raw):
        number = m.group("number")
        if not number:
            continue
        # Skip fragments that are clearly years ("2019") or tiny counts,
        # unless hourly (e.g. "$18/hr").
        value = _to_amount(number, m.group("suffix"))
        currency_token = (m.group("currency") or "").lower().strip() or None
        amounts.append((value, currency_token))

    currency = None
    for _, token in amounts:
        if token and token in CURRENCY_SYMBOLS:
            currency = CURRENCY_SYMBOLS[token]
            break

    plausible = []
    for value, _token in amounts:
        if period == "hour":
            if 5 <= value <= 1000:
                plausible.append(value)
        elif value >= 1000:
            plausible.append(value)
    if not plausible:
        return ParsedSalary(raw=raw, currency=currency, period=period)

    if period is None:
        # Infer: five-plus figure amounts are annual; two-digit are hourly.
        period = "hour" if max(plausible) < 1000 else "year"

    minimum = int(min(plausible))
    maximum = int(max(plausible))
    if "up to" in lowered and len(plausible) == 1:
        minimum = None  # type: ignore[assignment]
    return ParsedSalary(
        minimum=minimum, maximum=maximum, currency=currency, period=period, raw=raw
    )
