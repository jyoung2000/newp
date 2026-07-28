# Running JobPilot on Unraid (Compose Manager)

Two facts collide on Unraid, and both produce confusing errors:

1. The **Compose Manager** plugin keeps each stack in
   `/boot/config/plugins/compose.manager/projects/<stack>/` — on the USB flash
   drive. That folder holds a compose file and (optionally) a `.env`, nothing
   else.
2. JobPilot has **no published image**; the compose file builds it from
   source. A build needs the repository, and the repository is not on the
   flash drive.

So a stack pasted straight into Compose Manager fails — first on the missing
`.env`, then on the missing `Dockerfile`. Neither is worth fighting: put the
source on the array, and point the stack at it with absolute paths.

## 1. Put the source on the array

Over SSH or the Unraid web terminal. `git` isn't installed by default, so
fetch the tarball (adjust the branch if you're tracking a different one):

```bash
mkdir -p /mnt/user/appdata/jobpilot && cd /mnt/user/appdata/jobpilot
wget -qO- https://github.com/jyoung2000/newp/archive/refs/heads/main.tar.gz \
  | tar xz --strip-components=1
ls Dockerfile docker-compose.yml   # sanity check
```

Do **not** put this on `/boot`. It is a small vfat flash device: builds are
slow, permissions and symlinks don't survive, and you'd be writing tens of
thousands of files to the stick your server boots from.

### Doing all of it in one command, with the terminal closed

The first build takes several minutes, and closing an SSH session or the
Unraid web terminal normally kills whatever it was running. `JOBPILOT_DETACH=1`
re-launches the installer in its own session, so it survives:

```bash
curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/main/install.sh \
  -o /tmp/jobpilot-install.sh
JOBPILOT_DETACH=1 JOBPILOT_DIR=/mnt/user/appdata/jobpilot \
  bash /tmp/jobpilot-install.sh
```

It prints a pid and a log path and returns immediately — close the terminal
whenever you like. The installer downloads the source (no `git` needed),
writes a `.env` with a generated `SECRET_KEY` and database password, and
builds and starts the stack.

```bash
tail -f /mnt/user/appdata/jobpilot.install.log   # watch progress
```

It's done when the log says `JobPilot is running`, or when
`curl -fsS http://localhost:1456/api/health` answers. If you prefer a session
you can reattach to, Unraid ships `screen`:

```bash
screen -dmS jobpilot bash /tmp/jobpilot-install.sh   # start detached
screen -r jobpilot                                   # look in later
```

Detaching has to be asked for explicitly, and it needs the script on disk —
`curl … | bash` has no file to re-run, so download it first as above. Steps 2
and 3 below are then already done for you; skip to
[getting the extension](#4-getting-the-browser-extension), or read on if you
would rather drive Compose Manager yourself.

## 2. Configuration (optional)

`.env` is optional — every value has a working default, and `SECRET_KEY` is
generated once into the uploads volume on first boot if you don't set one. If
you want to set anything (an Anthropic key, the throughput ceilings, a
`PUBLIC_URL`), copy the template and edit it:

```bash
cd /mnt/user/appdata/jobpilot && cp -n .env.example .env
```

You can skip this entirely and set the AI key in the UI later, under
**Settings → AI** (stored encrypted).

## 3. The stack

In Compose Manager: **Add New Stack** → name it → **Edit Stack** → paste this.
It is the repository's `docker-compose.yml` with the paths made absolute, so
it works no matter which directory Compose Manager runs it from.

```yaml
services:
  app:
    build:
      context: /mnt/user/appdata/jobpilot
      dockerfile: Dockerfile
    image: jobpilot-app:local
    ports:
      - "1456:1456"
    env_file:
      - path: /mnt/user/appdata/jobpilot/.env
        required: false
    environment:
      DATABASE_URL: postgresql+psycopg://jobpilot:jobpilot@db:5432/jobpilot
      REDIS_URL: redis://redis:6379/0
      UPLOAD_DIR: /data/uploads
      PORT: "1456"
    volumes:
      - uploads:/data/uploads
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:1456/api/health"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 90s
    restart: unless-stopped

  worker:
    build:
      context: /mnt/user/appdata/jobpilot
      dockerfile: Dockerfile.worker
    env_file:
      - path: /mnt/user/appdata/jobpilot/.env
        required: false
    environment:
      DATABASE_URL: postgresql+psycopg://jobpilot:jobpilot@db:5432/jobpilot
      REDIS_URL: redis://redis:6379/0
      UPLOAD_DIR: /data/uploads
      PLAYWRIGHT_HEADFUL: "true"
    ports:
      - "127.0.0.1:6080:6080"
    volumes:
      - uploads:/data/uploads
      - pw-browsers:/ms-playwright
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
      app: { condition: service_healthy }
    shm_size: "1gb"
    stop_grace_period: 60s
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: jobpilot
      POSTGRES_PASSWORD: jobpilot
      POSTGRES_DB: jobpilot
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U jobpilot -d jobpilot"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 30s
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
  uploads:
  pw-browsers:
```

Change `POSTGRES_PASSWORD` (and the matching `DATABASE_URL`) if this host is
shared. The database is only reachable from the stack's own network — it
publishes no port — so the default is not exposed to your LAN.

Then **Compose Up**. The first build takes a few minutes (it compiles the
frontend and both extension bundles, and pulls a Playwright image for the
worker). Open `http://<tower>:1456`.

## 4. Getting the browser extension

The extension is built into the image and downloadable from **Settings →
Extension** in the UI — on Unraid that is the easy route, since the browser
you install it in isn't the server anyway.

To pull the files onto the array instead:

```bash
cd /mnt/user/appdata/jobpilot
mkdir -p plugin && docker compose cp app:/app/app/extension_dist/. ./plugin
```

(The repo's `plugin` compose service does the same thing with a relative bind
mount, which is why the `docker compose cp` form is the one to use here — it
doesn't care what directory Compose Manager runs from.)

## Notes specific to Unraid

- **noVNC (port 6080) is deliberately bound to `127.0.0.1`.** It is a raw view
  of the worker's browser with no authentication of its own. Reach it through
  the JobPilot UI, which requires your login — do not publish 6080 to the LAN.
- **Remote access:** put JobPilot behind a reverse proxy with TLS (SWAG,
  Nginx Proxy Manager) or on a tailnet, and set `PUBLIC_URL` in `.env` so
  Secure cookies and HSTS turn on. Don't port-forward 1456 directly.
- **Backups:** everything lives in Docker named volumes (`pgdata`, `uploads`),
  not in appdata. `docker run --rm -v jobpilot_pgdata:/v -v /mnt/user/backups:/b
  alpine tar czf /b/jobpilot-pgdata.tgz -C /v .` captures the database; the
  UI's **Settings → Export** writes a portable JSON of your own data.
- **Updates:** re-download the tarball over `/mnt/user/appdata/jobpilot`, then
  **Compose Up** with *Force Recreate* (or `docker compose up -d --build`).
