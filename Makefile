.PHONY: help dev test lint typecheck front-build front-dev ext-build ext-zip openapi-types seed migrate sign-firefox up plugin down logs

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

# --- Backend ---------------------------------------------------------------
dev: ## Run the API locally (port 1456) against DATABASE_URL
	cd backend && uv run uvicorn app.main:app --reload --port 1456

test: ## Run the backend test suite
	cd backend && uv run pytest -q

lint: ## Ruff lint (backend)
	cd backend && uv run ruff check app tests

typecheck: ## mypy (backend)
	cd backend && uv run mypy app

migrate: ## Apply database migrations
	cd backend && uv run alembic upgrade head

seed: ## Create the demo user and pull seed listings (live boards, fixture fallback)
	cd backend && uv run python -m app.seed

# --- Frontend --------------------------------------------------------------
openapi-types: ## Regenerate frontend/src/lib/types.gen.ts from the OpenAPI schema
	cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > ../frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/lib/types.gen.ts

front-build: ## Build the frontend into backend/app/static
	cd frontend && npm run build

front-dev: ## Vite dev server proxying /api to :1456
	cd frontend && npm run dev

# --- Extension -------------------------------------------------------------
ext-build: ## Build the extension for Chrome and Firefox
	cd extension && npm run build && npm run build:firefox

ext-zip: ## Produce distributable zips served at Settings → Extension
	cd extension && npm run zip && npm run zip:firefox
	mkdir -p backend/app/extension_dist
	cp extension/.output/*-chrome.zip backend/app/extension_dist/jobpilot-chrome.zip
	cp extension/.output/*-firefox.zip backend/app/extension_dist/jobpilot-firefox.zip
	node -e "console.log(require('./extension/package.json').version)" > backend/app/extension_dist/VERSION

sign-firefox: ## Sign the Firefox build with your own AMO credentials (WEB_EXT_API_KEY / WEB_EXT_API_SECRET)
	@test -n "$$WEB_EXT_API_KEY" || (echo "Set WEB_EXT_API_KEY and WEB_EXT_API_SECRET (from https://addons.mozilla.org/developers/addon/api/key/)"; exit 1)
	cd extension && npx web-ext sign --source-dir .output/firefox-mv3 --channel unlisted \
		--api-key "$$WEB_EXT_API_KEY" --api-secret "$$WEB_EXT_API_SECRET"

# --- Docker ----------------------------------------------------------------
up: ## docker compose up (app on http://localhost:1456)
	docker compose up -d --build

plugin: ## Copy the built browser extension out of the image into ./plugin
	docker compose --profile plugin run --rm plugin

down: ## docker compose down
	docker compose down

logs: ## Tail compose logs
	docker compose logs -f --tail=100
