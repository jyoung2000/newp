#!/usr/bin/env sh
set -e

echo "JobPilot app starting…"

# Ensure a real SECRET_KEY exists and matches the worker's.
. /secret-key.sh

# Wait for Postgres, then apply migrations.
python - <<'PY'
import os, time
import psycopg
url = os.environ.get("DATABASE_URL", "").replace("+psycopg", "")
if url.startswith("postgresql"):
    for attempt in range(30):
        try:
            psycopg.connect(url, connect_timeout=3).close()
            print("Postgres is ready.")
            break
        except Exception as exc:
            print(f"Waiting for Postgres ({attempt+1}/30): {exc}")
            time.sleep(2)
PY

alembic upgrade head

# Seed the demo user + listings on first boot (idempotent; safe to re-run).
if [ "${JOBPILOT_SEED:-1}" = "1" ]; then
  python -m app.seed || echo "Seed skipped/failed (non-fatal)."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-1456}" --proxy-headers --forwarded-allow-ips='*'
