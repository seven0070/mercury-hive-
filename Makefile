.PHONY: setup dev migrate bootstrap-owner test lint format security-check sbom container-scan stop seed-demo

setup: ## Full setup: generate secrets, build, start DB, migrate, apply privileges
	@echo "=== Mercury Hive Setup ==="
	@test -f .env || python scripts/generate_secrets.py
	docker compose build
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL..."
	@sleep 5
	$(MAKE) migrate
	@echo "Setup complete. Run 'make bootstrap-owner' to create the owner."

dev: ## Start API (ensures DB + migrations first)
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL..."
	@sleep 3
	$(MAKE) migrate
	docker compose up api

migrate: ## Run Alembic (admin) then apply runtime privileges
	docker compose --profile admin run --rm admin alembic upgrade head
	docker compose --profile admin run --rm privileges
	@echo "=== Migration + privileges complete ==="

bootstrap-owner: ## Create owner account (admin credentials only)
	docker compose --profile admin run --rm admin python -m scripts.bootstrap_owner

seed-demo: ## Seed demo data
	docker compose --profile admin run --rm admin python -m scripts.seed_demo

test: ## Run containerized test suite against isolated test database
	@echo "=== Starting test database ==="
	docker compose -f docker-compose.test.yml up -d postgres-test
	@echo "Waiting for test PostgreSQL..."
	@sleep 4
	docker compose -f docker-compose.test.yml --profile test-admin run --rm test-admin alembic upgrade head
	docker compose -f docker-compose.test.yml --profile test-admin run --rm test-privileges
	@echo "=== Running containerized tests ==="
	docker compose -f docker-compose.test.yml run --rm tests
	@echo "=== Stopping test database & wiping volume ==="
	docker compose -f docker-compose.test.yml down -v

lint: ## Check code style
	ruff check .
	ruff format --check .

format: ## Auto-format code
	ruff format .
	ruff check --fix .

security-check: ## Run security audits
	@echo "=== Security checks ==="
	python scripts/security_check.py

sbom: ## Generate a CycloneDX SBOM from the installed environment
	cyclonedx-py environment --output-format json --output-file sbom.json

container-scan: ## Scan the production image for high and critical vulnerabilities
	trivy image --severity HIGH,CRITICAL --exit-code 1 mercury-hive:latest

stop: ## Stop all containers
	docker compose down
	docker compose -f docker-compose.test.yml down -v 2>/dev/null || true
