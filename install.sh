#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# JobPilot installer.
#
#   curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/refs/heads/claude/jobpilot-assistant-canrub/install.sh | bash
#
# Prefer to read before you run (recommended for any curl|bash):
#   curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/refs/heads/claude/jobpilot-assistant-canrub/install.sh -o install.sh
#   less install.sh && bash install.sh
#
# The URL names a branch, and the branch has to exist — raw.githubusercontent
# returns 404, not a redirect, for one that doesn't. Swap in whatever branch
# you are tracking. What the installer *downloads* needs no such care: it asks
# GitHub for the repository's default branch.
#
# What it does: checks Docker, clones the repo into ./jobpilot, writes a .env
# with a freshly generated SECRET_KEY, and starts the stack. It never asks for
# your API key — set that in the UI at Settings → AI once it's running.
#
# Environment overrides:
#   JOBPILOT_DIR=~/apps/jobpilot   install location (default: ./jobpilot)
#   JOBPILOT_REPO=owner/name       source repo   (default: jyoung2000/newp)
#   JOBPILOT_REF=some-branch       branch or tag (default: the repo's own
#                                  default branch, whatever it is named)
#   JOBPILOT_PORT=1456             host port     (default: 1456)
#   JOBPILOT_NO_START=1            set up but don't run docker compose up
#   JOBPILOT_DETACH=1              keep running after you close the terminal
#
# The first build takes several minutes. Closing an SSH session normally kills
# it; JOBPILOT_DETACH=1 re-launches this script detached from the terminal and
# returns immediately, logging to $JOBPILOT_DIR.install.log (override with
# JOBPILOT_LOG). Watch it with: tail -f <that file>
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="${JOBPILOT_REPO:-jyoung2000/newp}"
# Empty means "whatever this repository calls its default branch" — resolved
# from the GitHub API below. Assuming `main` breaks on any repo that doesn't
# have one, and the failure looks like a broken installer rather than a
# missing branch.
REF="${JOBPILOT_REF:-}"
DIR="${JOBPILOT_DIR:-$(pwd)/jobpilot}"
PORT="${JOBPILOT_PORT:-1456}"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  \033[36m•\033[0m %s\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()   { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. Detach, if asked ---------------------------------------------------
# Re-exec ourselves without a controlling terminal so an SSH disconnect (or a
# closed Unraid web terminal) can't SIGHUP the build half-way through.
LOG="${JOBPILOT_LOG:-$DIR.install.log}"
if [ "${JOBPILOT_DETACH:-0}" = "1" ] && [ "${JOBPILOT_DETACHED:-0}" != "1" ]; then
  SOURCE_PATH="${BASH_SOURCE[0]:-}"
  [ -f "$SOURCE_PATH" ] || die "JOBPILOT_DETACH needs this script on disk (a pipe can't be re-run):
    curl -fsSL https://raw.githubusercontent.com/$REPO/$REF/install.sh -o install.sh
    JOBPILOT_DETACH=1 bash install.sh"
  # Keep a copy, so editing or deleting the original mid-build can't matter.
  SELF="$(mktemp "${TMPDIR:-/tmp}/jobpilot-install-XXXXXX")"
  cat "$SOURCE_PATH" > "$SELF"
  mkdir -p "$(dirname "$LOG")"
  : > "$LOG"
  # Pass the resolved settings explicitly: the child gets the same install
  # even if these were set as shell variables rather than exported.
  JOBPILOT_DETACHED=1 JOBPILOT_SELF="$SELF" JOBPILOT_DIR="$DIR" JOBPILOT_PORT="$PORT" \
  JOBPILOT_REPO="$REPO" JOBPILOT_REF="$REF" JOBPILOT_LOG="$LOG" \
  JOBPILOT_NO_START="${JOBPILOT_NO_START:-0}" \
    setsid nohup bash "$SELF" >>"$LOG" 2>&1 </dev/null &
  child=$!
  bold ""
  bold "JobPilot is installing in the background (pid $child)."
  echo "  You can close this terminal now."
  echo
  echo "  Watch it:   tail -f $LOG"
  echo "  When done:  http://localhost:$PORT"
  exit 0
fi

# The detached run works from a copy in /tmp; don't leave it behind.
if [ -n "${JOBPILOT_SELF:-}" ]; then
  trap 'rm -f "$JOBPILOT_SELF"' EXIT
fi

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

# git is preferred but optional — NAS distributions (Unraid, several
# Synology setups) ship without it, and a source tarball is enough to build.
if command -v git >/dev/null 2>&1; then
  FETCH=git
elif command -v curl >/dev/null 2>&1; then
  FETCH=curl
elif command -v wget >/dev/null 2>&1; then
  FETCH=wget
else
  die "Need git, curl or wget to download the source."
fi
[ "$FETCH" = "git" ] || command -v tar >/dev/null 2>&1 || die "Need tar to unpack the source."

# --- 2. Fetch the source ---------------------------------------------------
# JOBPILOT_REF may be unset, or may name a branch that doesn't exist. Ask the
# repository what its default branch is rather than assuming `main` — and say
# which ref was actually used rather than pretending we got the requested one.
REMOTE="https://github.com/$REPO.git"

# Print a URL's body on stdout, or nothing. Never fatal: every caller has a
# fallback, and no network is a normal condition to handle, not to crash on.
read_url() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --max-time 20 "$1" 2>/dev/null || true
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- --timeout=20 "$1" 2>/dev/null || true
  fi
}

# The repository's own default branch, per the GitHub API. Empty if that
# can't be determined (offline, rate-limited, private repo).
default_branch() {
  read_url "https://api.github.com/repos/$REPO" \
    | grep -o '"default_branch"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 \
    | sed 's/.*"\([^"]*\)"$/\1/'
}

# Stream a branch/tag tarball into $DIR. Returns non-zero if that ref has no
# archive, so the caller can try the next candidate.
download_tarball() {
  ref="$1"
  [ -n "$ref" ] || return 1
  for kind in heads tags; do
    url="https://codeload.github.com/$REPO/tar.gz/refs/$kind/$ref"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$url" 2>/dev/null | tar xz --strip-components=1 -C "$DIR" 2>/dev/null && return 0
    else
      wget -qO- "$url" 2>/dev/null | tar xz --strip-components=1 -C "$DIR" 2>/dev/null && return 0
    fi
  done
  return 1
}

fetch_source() {
  mkdir -p "$DIR"
  if [ -n "$REF" ] && download_tarball "$REF"; then
    ok "Source downloaded ($REF)"
    return 0
  fi
  [ -n "$REF" ] && warn "Ref '$REF' not found in $REPO — looking for the default branch"

  DEFAULT="$(default_branch)"
  if [ -n "$DEFAULT" ] && download_tarball "$DEFAULT"; then
    ok "Source downloaded ($DEFAULT — the repository's default branch)"
    REF="$DEFAULT"
    return 0
  fi

  # No API answer (offline, rate-limited): try the conventional names.
  for fallback in main master; do
    if download_tarball "$fallback"; then
      ok "Source downloaded ($fallback)"
      REF="$fallback"
      return 0
    fi
  done
  die "Could not download $REPO — check the repository name and your network.
    Tried: ${REF:-none given}${DEFAULT:+, $DEFAULT}, main, master"
}

if [ -d "$DIR/.git" ]; then
  info "Existing install found at $DIR — updating…"
  if [ -n "$REF" ] && git -C "$DIR" fetch --depth 1 origin "$REF" 2>/dev/null; then
    git -C "$DIR" checkout -q FETCH_HEAD
    ok "Updated to the latest $REF"
  else
    [ -n "$REF" ] && warn "Ref '$REF' not found — updating from the default branch instead"
    git -C "$DIR" fetch --depth 1 origin HEAD || die "Could not fetch updates from $REMOTE"
    git -C "$DIR" checkout -q FETCH_HEAD
    ok "Updated to the latest default branch"
  fi
elif [ -f "$DIR/docker-compose.yml" ]; then
  # A tarball install (no .git). Unpack over it: the archive carries no .env,
  # so configuration survives, but local edits to tracked files do not.
  info "Existing install found at $DIR — updating from the source archive…"
  warn "Any local edits to tracked files will be overwritten (.env is kept)"
  fetch_source
elif [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  die "$DIR already exists and is not empty. Set JOBPILOT_DIR to another path."
elif [ "$FETCH" = "git" ]; then
  info "Creating $DIR and fetching $REPO…"
  mkdir -p "$DIR"
  # No ref asked for: a plain clone already lands on the default branch, so
  # don't ask git for a branch named "".
  if [ -n "$REF" ] && git clone --quiet --depth 1 --branch "$REF" "$REMOTE" "$DIR" 2>/dev/null; then
    ok "Source downloaded ($REF)"
  elif git clone --quiet --depth 1 "$REMOTE" "$DIR"; then
    ACTUAL="$(git -C "$DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'default branch')"
    [ -n "$REF" ] && warn "Ref '$REF' not found in $REPO — using the default branch instead"
    ok "Source downloaded ($ACTUAL — the repository's default branch)"
  else
    die "Could not clone $REMOTE — check the repository name and your network."
  fi
else
  info "Creating $DIR and downloading $REPO (no git — using the source archive)…"
  fetch_source
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
