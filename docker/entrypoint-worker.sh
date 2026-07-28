#!/usr/bin/env sh
set -e

echo "JobPilot worker starting…"

GEOM="${SCREEN_GEOMETRY:-1280x900x24}"

# Headful Chromium needs a display. Xvfb provides it; x11vnc shares it;
# websockify/noVNC serves it to the authenticated JobPilot UI so a human can
# personally solve any CAPTCHA in the real page. The relay carries the human's
# input; software never solves the challenge.
Xvfb :99 -screen 0 "$GEOM" -nolisten tcp &
sleep 2
x11vnc -display :99 -forever -shared -nopw -quiet -rfbport 5900 &
sleep 1
websockify --web=/usr/share/novnc 6080 localhost:5900 &

# Wait for the app to have applied migrations (shared DB).
python - <<'PY'
import os, time
import psycopg
url = os.environ.get("DATABASE_URL", "").replace("+psycopg", "")
if url.startswith("postgresql"):
    for _ in range(30):
        try:
            psycopg.connect(url, connect_timeout=3).close()
            break
        except Exception:
            time.sleep(2)
PY

exec arq app.workers.main.WorkerSettings
