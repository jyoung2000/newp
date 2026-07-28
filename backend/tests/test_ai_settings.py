"""Settings → AI: the user's own API key, model and offline mode.

The key is encrypted at rest, never returned in plaintext, and scoped to the
user who set it.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db import get_sessionmaker
from app.llm.config import config_for_user, env_config
from app.models import User
from app.services.crypto import decrypt_secret, encrypt_secret, mask_secret
from tests.conftest import register_and_login

FAKE_KEY = "sk-ant-api03-TESTKEY0000000000000000000000000000abcd"


# --- crypto -----------------------------------------------------------------


def test_encrypt_round_trip(engine):
    token = encrypt_secret(FAKE_KEY)
    assert token != FAKE_KEY
    assert FAKE_KEY not in token  # not merely encoded
    assert decrypt_secret(token) == FAKE_KEY


def test_decrypt_rejects_tampering_and_garbage(engine):
    token = encrypt_secret(FAKE_KEY)
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    # Authenticated encryption: tampering yields None, never a wrong value.
    assert decrypt_secret(tampered) != FAKE_KEY
    assert decrypt_secret("not-a-token") is None
    assert decrypt_secret(None) is None


def test_mask_never_reveals_middle():
    hint = mask_secret(FAKE_KEY)
    assert hint is not None
    assert hint.startswith("sk-ant-") and hint.endswith(FAKE_KEY[-4:])
    assert FAKE_KEY not in hint
    assert len(hint) < len(FAKE_KEY)


# --- API --------------------------------------------------------------------


def test_defaults_report_offline_without_key(client):
    register_and_login(client, "ai1@example.com")
    body = client.get("/api/settings/ai").json()
    assert body["provider"] == "anthropic"
    assert body["key_source"] == "none"
    assert body["effective_offline"] is True  # no key -> offline heuristics
    assert body["key_hint"] is None
    assert any(m["id"] == "claude-opus-5" for m in body["available_models"])


def test_set_key_is_masked_and_never_returned(client):
    headers = register_and_login(client, "ai2@example.com")
    r = client.put(
        "/api/settings/ai",
        json={"api_key": FAKE_KEY, "model": "claude-sonnet-5", "offline": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key_source"] == "user"
    assert body["model"] == "claude-sonnet-5"
    assert body["effective_offline"] is False
    # The plaintext key appears nowhere in the response.
    assert FAKE_KEY not in r.text
    assert body["key_hint"] == mask_secret(FAKE_KEY)

    # ...nor on a subsequent read.
    r2 = client.get("/api/settings/ai")
    assert FAKE_KEY not in r2.text


def test_key_is_encrypted_at_rest(client, engine):
    headers = register_and_login(client, "ai3@example.com")
    client.put("/api/settings/ai", json={"api_key": FAKE_KEY}, headers=headers)

    db = get_sessionmaker()()
    try:
        user = db.scalar(select(User).where(User.email == "ai3@example.com"))
        assert user is not None
        stored = user.llm_api_key_enc
        assert stored and stored != FAKE_KEY
        assert FAKE_KEY not in stored  # ciphertext, not the raw key
        assert decrypt_secret(stored) == FAKE_KEY  # decryptable by the app
    finally:
        db.close()


def test_clearing_the_key_falls_back_to_offline(client):
    headers = register_and_login(client, "ai4@example.com")
    client.put("/api/settings/ai", json={"api_key": FAKE_KEY}, headers=headers)
    assert client.get("/api/settings/ai").json()["key_source"] == "user"

    r = client.delete("/api/settings/ai/key", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["key_source"] == "none"
    assert body["effective_offline"] is True


def test_omitting_key_preserves_it(client):
    headers = register_and_login(client, "ai5@example.com")
    client.put("/api/settings/ai", json={"api_key": FAKE_KEY}, headers=headers)
    # A later update that only changes the model must not wipe the key.
    r = client.put("/api/settings/ai", json={"model": "claude-haiku-4-5"}, headers=headers)
    assert r.json()["key_source"] == "user"
    assert r.json()["model"] == "claude-haiku-4-5"


def test_offline_toggle_forces_dry_run_even_with_key(client, engine):
    headers = register_and_login(client, "ai6@example.com")
    client.put("/api/settings/ai", json={"api_key": FAKE_KEY, "offline": True}, headers=headers)
    body = client.get("/api/settings/ai").json()
    assert body["key_source"] == "user"
    assert body["effective_offline"] is True

    db = get_sessionmaker()()
    try:
        user = db.scalar(select(User).where(User.email == "ai6@example.com"))
        cfg = config_for_user(user)
        assert cfg.dry_run is True  # nothing will be sent to Anthropic
    finally:
        db.close()


def test_test_connection_reports_offline_without_calling_out(client):
    headers = register_and_login(client, "ai7@example.com")
    r = client.post("/api/settings/ai/test", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["offline"] is True
    assert "offline" in body["detail"].lower()


def test_keys_are_per_user(client, engine):
    headers_a = register_and_login(client, "ai8a@example.com")
    client.put("/api/settings/ai", json={"api_key": FAKE_KEY}, headers=headers_a)

    # User B has their own (empty) AI settings and cannot see A's key.
    register_and_login(client, "ai8b@example.com")
    body = client.get("/api/settings/ai").json()
    assert body["key_source"] == "none"
    assert body["key_hint"] is None

    db = get_sessionmaker()()
    try:
        b = db.scalar(select(User).where(User.email == "ai8b@example.com"))
        assert config_for_user(b).api_key is None
        a = db.scalar(select(User).where(User.email == "ai8a@example.com"))
        assert config_for_user(a).api_key == FAKE_KEY
    finally:
        db.close()


def test_env_fallback_when_user_has_no_key(client, engine, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-env-000000000000000000wxyz")
    register_and_login(client, "ai9@example.com")
    body = client.get("/api/settings/ai").json()
    assert body["key_source"] == "env"
    assert body["env_key_present"] is True
    # Even the env key is only ever shown masked.
    assert "sk-ant-env-000000000000000000wxyz" not in body["key_hint"]
    assert env_config().api_key == "sk-ant-env-000000000000000000wxyz"
