#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Update a running JobPilot install, in place.
#
#   cd /root/jobpilot && ./update.sh
#
# Keeps your .env, your database and your uploads. Pulls the latest code,
# rebuilds the images, and restarts — the web UI first, then the executor, so a
# slow or failing worker build can never take the UI down with it. Migrations
# apply themselves on boot.
#
# Flags:
#   --check    say whether an update is available, change nothing
#   --prune    delete the images this update orphaned, after it succeeds
#   --worker   also rebuild the executor (default: yes; --no-worker to skip)
#   --no-worker
#
# Run it from the install directory, or point JOBPILOT_DIR at one.
# ---------------------------------------------------------------------------
set -euo pipefail

DIR="${JOBPILOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

CHECK_ONLY=0
PRUNE=0
DO_WORKER=1
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --prune) PRUNE=1 ;;
    --worker) DO_WORKER=1 ;;
    --no-worker) DO_WORKER=0 ;;
    -h|--help) sed -n '3,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'Unknown option: %s (try --help)\n' "$arg" >&2; exit 2 ;;
  esac
done

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  \033[36m•\033[0m %s\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()   { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

cd "$DIR" || die "Can't enter $DIR"
[ -f docker-compose.yml ] || die "$DIR doesn't look like a JobPilot install (no docker-compose.yml).
    Run this from the install directory, or set JOBPILOT_DIR."

echo
bold "JobPilot — update"
bold "================"
echo

# --- Prerequisites ---------------------------------------------------------
# --check only reads git, so don't make it depend on a running Docker daemon:
# "is there an update?" should be answerable while the stack is stopped.
COMPOSE=""
if [ "$CHECK_ONLY" != "1" ]; then
  command -v docker >/dev/null 2>&1 || die "Docker is not installed."
  docker info >/dev/null 2>&1 || die "Docker is installed but not running."
  if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
  else
    die "Docker Compose not found."
  fi
fi

# --- Fetch the new code ----------------------------------------------------
if [ ! -d .git ]; then
  # A tarball install has no history to pull; the installer knows how to
  # replace the tree in place without touching .env.
  die "This install has no git checkout (it came from a source archive).
    Re-run the installer to update it — it keeps your .env:
      curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/refs/heads/claude/jobpilot-assistant-canrub/install.sh | bash"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
if [ "$BRANCH" = "HEAD" ]; then
  # Older installs were left on a detached FETCH_HEAD, where `git pull`
  # refuses outright. Recover onto a real branch instead of failing.
  BRANCH="$(git config --get jobpilot.branch || true)"
  [ -n "$BRANCH" ] || BRANCH="$(basename "$(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null || echo main)")"
  warn "This checkout was detached; moving it onto '$BRANCH'"
fi

BEFORE="$(git rev-parse HEAD)"
info "Fetching $BRANCH…"
attempt=1
# Depth 50, not 1: a depth-1 fetch leaves the new tip unconnected to the commit
# you are on, so `git log BEFORE..AFTER` can only see the tip and silently
# under-reports what the update contains. 50 is still small and covers any
# realistic gap for an appliance that updates in place.
until git fetch --depth 50 origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" 2>/dev/null; do
  [ "$attempt" -ge 4 ] && die "Could not fetch from origin after $attempt attempts. Network?"
  delay=$((2 ** attempt))
  warn "Fetch failed; retrying in ${delay}s"
  sleep "$delay"
  attempt=$((attempt + 1))
done
AFTER="$(git rev-parse "refs/remotes/origin/$BRANCH")"

if [ "$BEFORE" = "$AFTER" ]; then
  ok "Already up to date ($(git log -1 --format='%h %s' | cut -c1-72))"
  [ "$CHECK_ONLY" = "1" ] && exit 0
  info "Rebuilding anyway, in case a previous run was interrupted."
else
  echo
  bold "New commits"
  # Only claim to list the range when the local history actually connects the
  # two ends. On a shallow clone that is deeper than the fetch, it won't — and
  # a partial list read as a complete one is worse than an honest note.
  if git merge-base --is-ancestor "$BEFORE" "$AFTER" 2>/dev/null; then
    git --no-pager log --no-merges --oneline "$BEFORE..$AFTER" | sed 's/^/    /'
  else
    git --no-pager log --no-merges --oneline -1 "$AFTER" | sed 's/^/    /'
    info "(this install is more than 50 commits behind; showing the newest only)"
  fi
  echo
  if [ "$CHECK_ONLY" = "1" ]; then
    info "An update is available. Run without --check to apply it."
    exit 0
  fi
fi

# Local edits to tracked files would be silently discarded by a hard reset, so
# say what will be lost and stop. .env is untracked and never at risk.
if ! git diff --quiet HEAD -- 2>/dev/null; then
  echo
  warn "You have local changes to tracked files:"
  git --no-pager diff --name-only HEAD -- | sed 's/^/      /'
  die "Updating would overwrite them. Commit, stash, or discard them first:
      git -C $DIR stash          # keep them for later
      git -C $DIR checkout -- .  # throw them away"
fi

git checkout -q -B "$BRANCH" "refs/remotes/origin/$BRANCH"
git branch -q --set-upstream-to="origin/$BRANCH" "$BRANCH" 2>/dev/null || true
git config jobpilot.branch "$BRANCH"
ok "Updated to $(git log -1 --format='%h %s' | cut -c1-72)"

# --- Rebuild and restart ---------------------------------------------------
# The UI first and on its own. `up --build` with nothing named builds every
# image before starting a single container, so a slow or broken executor build
# would leave nothing listening on the port at all.
echo
info "Rebuilding the web app…"
$COMPOSE up -d --build db redis app || die "The web app failed to build or start — see the output above.
    Your data is untouched. Previous images are still on disk:
      cd $DIR && $COMPOSE up -d app"

# `|| true` matters: a .env without a PORT line — or no .env at all, which
# compose treats as valid — makes grep exit 1, and under `set -o pipefail` that
# would kill the update here, after the rebuild and with nothing said about
# why. Default and carry on instead.
PORT="$(grep -E '^PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true)"
PORT="${PORT:-1456}"
URL="http://localhost:$PORT"

info "Waiting for it to answer…"
READY=0
for _ in $(seq 1 60); do
  if curl -fsS "$URL/api/health" >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
if [ "$READY" = "1" ]; then
  ok "Web app healthy"
else
  warn "$URL/api/health hasn't answered yet — migrations may still be running."
  warn "Watch it:  cd $DIR && $COMPOSE logs -f app"
fi

if [ "$DO_WORKER" = "1" ]; then
  echo
  info "Rebuilding the executor (large image — it ships a real browser)…"
  if $COMPOSE up -d --build worker; then
    ok "Executor running"
  else
    warn "The executor didn't start — either its image failed to build, or the"
    warn "app isn't healthy yet, which compose reports as"
    warn "  'dependency failed to start: container ... is unhealthy'."
    warn "The web UI above is unaffected; only server-side runs are, and they queue."
    warn "Retry:  cd $DIR && $COMPOSE up -d --build worker"
  fi
fi

if [ "$PRUNE" = "1" ]; then
  echo
  info "Removing images this update orphaned…"
  # Dangling only: never touches an image some container still references.
  docker image prune -f >/dev/null 2>&1 || true
  ok "Reclaimed $(docker system df --format '{{.Reclaimable}}' 2>/dev/null | head -1 || echo 'some space')"
fi

LAN_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' \
  | grep -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' | head -1 || true)"
echo
if [ -n "$LAN_IP" ]; then
  bold "JobPilot is up at  http://$LAN_IP:$PORT"
else
  bold "JobPilot is up at  $URL"
fi

# The extension is built into the image, so a new image can mean a new build.
# Nothing forces it on the user, but they should know it's there.
if [ "$BEFORE" != "$AFTER" ] && ! git diff --quiet "$BEFORE" "$AFTER" -- extension 2>/dev/null; then
  echo
  warn "The browser extension changed in this update."
  warn "Refresh your copy:  cd $DIR && $COMPOSE --profile plugin run --rm plugin"
  warn "then reload it in your browser (chrome://extensions → Reload)."
fi
