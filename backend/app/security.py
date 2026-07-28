"""Password hashing, opaque tokens, CSRF and TOTP helpers."""
from __future__ import annotations

import hashlib
import hmac
import secrets

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# argon2id with the library's safe defaults (argon2-cffi uses type=ID).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, candidate: str) -> bool:
    try:
        return _hasher.verify(password_hash, candidate)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token(nbytes: int = 32) -> str:
    """Opaque URL-safe token. Only its hash is stored server-side."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_pairing_code() -> str:
    """6-digit numeric pairing code."""
    return f"{secrets.randbelow(1_000_000):06d}"


# --- TOTP -----------------------------------------------------------------

def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="JobPilot")


def verify_totp(secret: str, code: str) -> bool:
    try:
        return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)
    except Exception:
        return False
