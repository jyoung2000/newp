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
#
# In the background, and bounded. This fetches real listings from Greenhouse
# and Lever, and polite fetching means per-host delays, 20s timeouts and
# retries with backoff — minutes, on a host where those sites are slow or
# unreachable. Run in the foreground it delays the port opening past the
# healthcheck's patience, so compose marks a perfectly good container
# unhealthy and anything depending on it refuses to start. Demo data is never
# worth holding the server for.
if [ "${JOBPILOT_SEED:-1}" = "1" ]; then
  (
    if timeout "${JOBPILOT_SEED_TIMEOUT:-600}" python -m app.seed; then
      :
    else
      echo "Seed skipped/failed (non-fatal) — the app is unaffected."
    fi
  ) &
  echo "Seeding demo data in the background; the UI is up before it finishes."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-1456}" --proxy-headers --forwarded-allow-ips='*'
