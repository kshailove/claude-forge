# =============================================================================
# engg-intelligence — Developer Makefile
#
# Usage:
#   make up           Start all services
#   make down         Stop all services
#   make logs         Follow API logs
#   make migrate      Apply Alembic migrations
#   make test         Run the test suite
#   make load-test    Run Locust load test (headless, 50 users, 5 min)
#   make build        Rebuild Docker images
#   make compile-mjml Compile MJML email templates to HTML
# =============================================================================

.PHONY: up down logs migrate test load-test build compile-mjml \
        shell-api shell-db psql create-admin rotate-key help

# ---------------------------------------------------------------------------
# Primary targets
# ---------------------------------------------------------------------------

## Start all services in the background
up:
	docker compose up -d

## Stop all services (data volumes are preserved)
down:
	docker compose down

## Follow API container logs
logs:
	docker compose logs -f api

## Apply all pending Alembic migrations
migrate:
	docker compose exec api alembic upgrade head

## Run the full test suite inside the API container
test:
	docker compose exec api pytest tests/ -v --tb=short

## Run Locust load test (headless, 50 users, ramp 10/s, 5 min, target localhost:8000)
load-test:
	cd tests/load && locust -f locustfile.py \
		--headless \
		-u 50 \
		-r 10 \
		--run-time 5m \
		--host http://localhost:8000

## Rebuild all Docker images (no cache)
build:
	docker compose build --no-cache

## Compile MJML email templates to HTML
compile-mjml:
	@which mjml > /dev/null 2>&1 || (echo "mjml not found — install with: npm install -g mjml" && exit 1)
	@for f in backend/app/templates/*.mjml; do \
		out="backend/app/templates/compiled/$$(basename $$f .mjml).html"; \
		echo "Compiling $$f → $$out"; \
		mjml "$$f" -o "$$out"; \
	done
	@echo "MJML compilation complete."

# ---------------------------------------------------------------------------
# Convenience / admin targets
# ---------------------------------------------------------------------------

## Open a Python shell inside the API container
shell-api:
	docker compose exec api python

## Open a bash shell inside the API container
shell-bash:
	docker compose exec api bash

## Open psql connected to the local database
shell-db:
	docker compose exec db psql -U engg -d engg_intelligence

## Alias: psql shortcut
psql: shell-db

## Create the first admin user interactively
create-admin:
	docker compose exec api python -m app.cli create-admin

## Rotate the AES-256 encryption key (requires OLD_KEY and NEW_KEY env vars)
## Usage: make rotate-key OLD_KEY=<hex> NEW_KEY=<hex>
rotate-key:
	@test -n "$(OLD_KEY)" || (echo "Usage: make rotate-key OLD_KEY=<64-hex> NEW_KEY=<64-hex>" && exit 1)
	@test -n "$(NEW_KEY)" || (echo "Usage: make rotate-key OLD_KEY=<64-hex> NEW_KEY=<64-hex>" && exit 1)
	docker compose exec api python -m app.cli rotate-encryption-key \
		--old-key "$(OLD_KEY)" \
		--new-key "$(NEW_KEY)"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

## Show this help message
help:
	@echo ""
	@echo "engg-intelligence Makefile targets:"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
	@echo ""
