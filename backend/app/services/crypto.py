"""Encryption for secrets stored at rest (currently: the user's LLM API key).

The key is derived from `SECRET_KEY` with HKDF, so rotating `SECRET_KEY`
invalidates stored secrets (they decrypt to None and the user is asked to
re-enter — never a silent wrong value). AES-GCM gives authenticated
encryption, so tampering is detected rather than yielding garbage.

Secrets encrypted here are never logged and never returned to a client in
plaintext — the API only ever exposes a masked hint (see api/settings.py).
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

_NONCE_BYTES = 12
_INFO = b"jobpilot:secret-box:v1"


def _aead() -> AESGCM:
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_INFO,
    ).derive(get_settings().secret_key.encode())
    return AESGCM(key)


def encrypt_secret(plaintext: str) -> str:
    """Return a base64 token holding nonce + ciphertext."""
    nonce = os.urandom(_NONCE_BYTES)
    blob = _aead().encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + blob).decode()


def decrypt_secret(token: str | None) -> str | None:
    """Decrypt a token. Returns None if it is absent, malformed, or was
    encrypted under a different SECRET_KEY — never a partial/incorrect value."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        nonce, blob = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return _aead().decrypt(nonce, blob, None).decode()
    except Exception:
        return None


def mask_secret(value: str | None) -> str | None:
    """A hint the UI can show without revealing the secret: first 7 and last
    4 characters, e.g. 'sk-ant-…4f2a'."""
    if not value:
        return None
    if len(value) <= 12:
        return "…" + value[-2:]
    return f"{value[:7]}…{value[-4:]}"
