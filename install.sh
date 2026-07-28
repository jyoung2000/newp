#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# JobPilot installer.
#
#   curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/main/install.sh | bash
#
# Prefer to read before you run (recommended for any curl|bash):
#   curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/main/install.sh -o install.sh
#   less install.sh && bash install.sh
#
# What it does: checks Docker, clones the repo into ./jobpilot, writes a .env
# with a freshly generated SECRET_KEY, and starts the stack. It never asks for
# your API key — set that in the UI at Settings → AI once it's running.
#
# Environment overrides:
#   JOBPILOT_DIR=~/apps/jobpilot   install location (default: ./jobpilot)
#   JOBPILOT_REPO=owner/name       source repo   (default: jyoung2000/newp)
#   JOBPILOT_REF=main              branch or tag (default: main)
#   JOBPILOT_PORT=1456             host port     (default: 1456)
#   JOBPILOT_NO_START=1            set up but don't run docker compose up
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="${JOBPILOT_REPO:-jyoung2000/newp}"
REF="${JOBPILOT_REF:-main}"
DIR="${JOBPILOT_DIR:-$(pwd)/jobpilot}"
PORT="${JOBPILOT_PORT:-1456}"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  \033[36m•\033[0m %s\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()   { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

bold ""
bold "JobPilot — self-hosted job-search assistant"
bold "==========================================="
echo

# --- 1. Prerequisites ------------------------------------------------------
info "Checking prerequisites…"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop / the docker service and re-run."

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "Docker Compose not found. Install Docker Compose v2 (bundled with recent Docker)."
fi
ok "Docker and Compose are available"

command -v git >/dev/null 2>&1 || die "git is not installed."

# --- 2. Fetch the source ---------------------------------------------------
# JOBPILOT_REF may name a branch that doesn't exist yet (e.g. before the first
# release lands on main); fall back to the repository's default branch and say
# so rather than failing or pretending we got the requested ref.
REMOTE="https://github.com/$REPO.git"

if [ -d "$DIR/.git" ]; then
  info "Existing install found at $DIR — updating…"
  if git -C "$DIR" fetch --depth 1 origin "$REF" 2>/dev/null; then
    git -C "$DIR" checkout -q FETCH_HEAD
    ok "Updated to the latest $REF"
  else
    git -C "$DIR" fetch --depth 1 origin HEAD || die "Could not fetch updates from $REMOTE"
    git -C "$DIR" checkout -q FETCH_HEAD
    warn "Branch '$REF' not found — updated to the repository's default branch instead"
  fi
elif [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  die "$DIR already exists and is not empty. Set JOBPILOT_DIR to another path."
else
  info "Creating $DIR and fetching $REPO…"
  mkdir -p "$DIR"
  if git clone --quiet --depth 1 --branch "$REF" "$REMOTE" "$DIR" 2>/dev/null; then
    ok "Source downloaded ($REF)"
  elif git clone --quiet --depth 1 "$REMOTE" "$DIR"; then
    ACTUAL="$(git -C "$DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'default branch')"
    warn "Branch '$REF' not found — using the repository's default branch ($ACTUAL)"
  else
    die "Could not clone $REMOTE — check the repository name and your network."
  fi
fi

[ -f "$DIR/docker-compose.yml" ] || die "$DIR doesn't look like a JobPilot checkout (no docker-compose.yml)."

cd "$DIR"

# --- 3. Configure ----------------------------------------------------------
if [ -f .env ]; then
  ok "Keeping your existing .env"
else
  info "Writing .env with a generated SECRET_KEY…"
  cp .env.example .env

  if command -v openssl >/dev/null 2>&1; then
    SECRET="$(openssl rand -hex 32)"
  else
    SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  fi
  # Portable in-place edit (GNU and BSD sed differ on -i).
  sed "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env > .env.tmp && mv .env.tmp .env

  # Random database password so the default isn't shipped into production.
  if command -v openssl >/dev/null 2>&1; then
    DBPASS="$(openssl rand -hex 16)"
    sed "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$DBPASS|" .env > .env.tmp && mv .env.tmp .env
  fi

  if [ "$PORT" != "1456" ]; then
    sed "s|^PORT=.*|PORT=$PORT|" .env > .env.tmp && mv .env.tmp .env
  fi
  ok "Configuration written to $DIR/.env"
fi

if [ "${JOBPILOT_NO_START:-0}" = "1" ]; then
  echo
  ok "Set up at $DIR (not started, JOBPILOT_NO_START=1)"
  echo "  Start it with:  cd $DIR && $COMPOSE up -d"
  exit 0
fi

# --- 4. Build and start ----------------------------------------------------
echo
info "Building and starting (first run compiles the UI and extension — a few minutes)…"
$COMPOSE up -d --build

echo
info "Waiting for JobPilot to come up…"
URL="http://localhost:$PORT"
for _ in $(seq 1 90); do
  if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

echo
if [ "${READY:-0}" = "1" ]; then
  bold "JobPilot is running → $URL"
else
  warn "Started, but $URL/api/health didn't respond yet."
  warn "It may still be migrating. Check logs:  cd $DIR && $COMPOSE logs -f app"
fi

cat <<EOF

Next steps
  1. Open $URL and create your account.
  2. Settings → AI — paste your Anthropic API key (stored encrypted).
     Skip this to run fully offline with local heuristics.
  3. Settings → Extension — download and pair the browser extension.
  4. Profile — add your details and confirm your résumé parse.
  5. Search — find real openings, then start a run.

A demo account is seeded for a quick look:  demo@jobpilot.local / demo-password-1234

Useful commands (from $DIR)
  $COMPOSE logs -f app      # follow the app log
  $COMPOSE restart app      # restart after changing .env
  $COMPOSE down             # stop
  $COMPOSE down -v          # stop and DELETE all data
  $COMPOSE --profile plugin run --rm plugin
                            # copy the browser extension to ./plugin, unpacked

JobPilot applies to jobs you actually want, with information you actually
provided — and every CAPTCHA is completed by you, never by the software.
EOF
