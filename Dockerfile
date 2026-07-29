# ---------------------------------------------------------------------------
# JobPilot app image: builds the frontend and the browser-extension bundles,
# then serves the FastAPI app (UI + REST + WS) on port 1456.
# ---------------------------------------------------------------------------

# --- Stage 1: build the React frontend into the backend's static dir --------
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# Generate the typed client from the committed OpenAPI schema, then build.
RUN npm run gen:types || true
RUN npm run build

# --- Stage 2: build the extension bundles -----------------------------------
FROM node:22-slim AS extension
WORKDIR /build/extension
COPY extension/package.json extension/package-lock.json* ./
# This layer exists to cache dependencies, so only the manifests are here yet.
# The package's own postinstall is `wxt prepare`, which reads the entrypoints
# under src/ and aborts when it can't find them — skip scripts now and run it
# below, once there is a source tree to prepare.
RUN npm install --ignore-scripts
COPY extension/ ./
RUN npm run postinstall
RUN npm run build && npm run build:firefox && npm run zip && npm run zip:firefox \
    && mkdir -p /out \
    && cp .output/*-chrome.zip /out/jobpilot-chrome.zip \
    && cp .output/*-firefox.zip /out/jobpilot-firefox.zip \
    # Unpacked builds too: Chrome's "Load unpacked" wants a folder, not a zip,
    # and this is what the `plugin` compose service copies out to the host.
    && cp -r .output/chrome-mv3 /out/chrome-unpacked \
    && cp -r .output/firefox-mv3 /out/firefox-unpacked \
    && node -e "console.log(require('./package.json').version)" > /out/VERSION

# --- Stage 3: the Python app ------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Noninteractive for the same reason as the worker image: a package that wants
# to ask a configuration question would hang the build rather than fail it.
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies come from the project's own metadata, resolved through its
# lock file. This used to be a hand-copied list of the same packages, which
# drifted: cryptography — imported by app/services/crypto.py, and so by the
# whole API — was never added, and the image crashed on import at every boot.
# A second copy of a dependency list is a copy that will go stale.
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --upgrade pip uv \
    && uv export --frozen --no-dev --no-emit-project --no-hashes \
         --format requirements-txt -o /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip uninstall -y uv \
    && rm -f /tmp/requirements.txt

COPY backend/ ./
# Built frontend assets (own the static dir) and extension bundles (kept in a
# separate dir so a frontend rebuild can never wipe them).
COPY --from=frontend /build/backend/app/static ./app/static
COPY --from=extension /out ./app/extension_dist

EXPOSE 1456
COPY docker/entrypoint-app.sh /entrypoint-app.sh
COPY docker/secret-key.sh /secret-key.sh
RUN chmod +x /entrypoint-app.sh /secret-key.sh
ENTRYPOINT ["/entrypoint-app.sh"]
