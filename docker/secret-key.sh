#!/usr/bin/env sh
# Sourced by both container entrypoints before anything reads settings.
#
# SECRET_KEY signs sessions and derives the key that encrypts each user's own
# API key, so two things must hold: it must not be the placeholder shipped in
# .env.example, and the app and worker must agree on it (or the worker cannot
# decrypt what the app stored). When the environment doesn't supply a real
# one, use a key generated once into the uploads volume — the one filesystem
# both containers mount. Setting SECRET_KEY in .env overrides all of this.

_key_file="${SECRET_KEY_FILE:-${UPLOAD_DIR:-/data/uploads}/.secret_key}"

case "${SECRET_KEY:-}" in
  "" | change-me | change-me-in-.env)
    mkdir -p "$(dirname "$_key_file")"
    if [ ! -s "$_key_file" ]; then
      # Write private, then move into place without clobbering: the app and
      # the worker can reach this at the same time and must not disagree.
      (umask 077; python -c 'import secrets; print(secrets.token_hex(32))' \
        > "$_key_file.tmp.$$")
      mv -n "$_key_file.tmp.$$" "$_key_file" 2>/dev/null || true
      rm -f "$_key_file.tmp.$$"
      echo "No SECRET_KEY set — generated one at $_key_file (kept in the uploads volume)."
      echo "Sessions and stored API keys are tied to it; deleting it logs everyone out."
    else
      echo "No SECRET_KEY set — using the generated key at $_key_file."
    fi
    SECRET_KEY="$(cat "$_key_file")"
    export SECRET_KEY
    ;;
esac
