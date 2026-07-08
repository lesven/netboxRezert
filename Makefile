.PHONY: install up down fresh logs test lint lint-fix typecheck generate-tokens seed-netbox

VM_COUNT ?= 1000
CONTACT_COUNT ?= 50

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

up:
	docker compose up -d --build

down:
	docker compose down

fresh:
	docker compose down -v
	docker compose up -d --build

logs:
	docker compose logs -f app

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

lint-fix:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

typecheck:
	.venv/bin/mypy app

# Batch-generate/refresh personalized links for all contacts that currently
# own VMs. Run against the live container so it uses the real NetBox config.
generate-tokens:
	docker compose exec app python -m scripts.generate_tokens --output /app/data/tokens.csv
	docker compose cp app:/app/data/tokens.csv ./tokens.csv
	@echo "Links geschrieben nach ./tokens.csv"

# Wipes+recreates synthetic test data (contacts + VMs, tagged
# 'recert-seed-data') on whatever NETBOX_URL/NETBOX_TOKEN point to in .env.
# Interactive confirmation prompt - requires a TTY (works fine from a normal
# terminal `make` invocation). Override counts with VM_COUNT=/CONTACT_COUNT=.
seed-netbox:
	docker compose exec app python -m scripts.seed_netbox --vm-count $(VM_COUNT) --contact-count $(CONTACT_COUNT)
