"""The single string that links a browser to this server.

Pairing needs two facts: which server, and proof you are allowed to pair with
it. Presenting those as separate fields — a 6-digit code plus a URL to retype —
puts the harder half on the person least able to answer it. The URL that works
is whichever origin their browser is already using; "localhost" is right only
when the browser and the server are the same machine, which on a NAS they
almost never are.

So both travel together, in one blob that is obviously a single thing to copy:

    JP1-<base64url of {"u": "<app url>", "c": "<code>"}>

This is not encryption and is not meant to be. The pairing code inside is
already short-lived, single-use and server-verified; base64url exists to make
the string one selectable token with no spaces, slashes or dots to break on,
not to hide anything. Treat a link code exactly as carefully as the pairing
code it carries.
"""
from __future__ import annotations

import base64
import json

PREFIX = "JP1-"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    # base64url without padding: restore it before decoding.
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def build_link_code(app_url: str, code: str) -> str:
    payload = json.dumps({"u": app_url.rstrip("/"), "c": code}, separators=(",", ":"))
    return PREFIX + _b64url_encode(payload.encode("utf-8"))


def parse_link_code(link_code: str) -> tuple[str, str] | None:
    """(app_url, code), or None if this isn't a link code we understand.

    Kept here alongside build_link_code so the two can't drift, and so the
    format has one test to hold it still. The extension has its own parser in
    TypeScript; tests/test_link_code.py pins the shape both must agree on.
    """
    text = link_code.strip()
    if not text.startswith(PREFIX):
        return None
    try:
        data = json.loads(_b64url_decode(text[len(PREFIX) :]))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    url, code = data.get("u"), data.get("c")
    if not isinstance(url, str) or not isinstance(code, str) or not url or not code:
        return None
    return url.rstrip("/"), code
