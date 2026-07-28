from __future__ import annotations

import datetime as dt
import html as html_module

from bs4 import BeautifulSoup


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    unescaped = html_module.unescape(value)
    if "<" not in unescaped:
        return unescaped.strip() or None
    soup = BeautifulSoup(unescaped, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line) or None


def parse_iso(value: str | int | float | None) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Epoch seconds or milliseconds.
        seconds = value / 1000 if value > 1e12 else value
        try:
            return dt.datetime.fromtimestamp(seconds, tz=dt.UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.UTC)
            return parsed
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text[:10], fmt).replace(tzinfo=dt.UTC)
        except ValueError:
            continue
    return None
