.PHONY: test test-schemas test-ingestion test-alerts test-api validate fmt

# Runs all test suites. Because component package names (ingestion, alerts,
# api) collide with top-level directories, each suite is invoked separately
# with its own conftest injecting sys.path.
test: validate test-ingestion test-alerts test-api

validate:
	python3 tools/validate.py all
	python3 tools/test_validator.py

test-schemas: validate

test-ingestion:
	python3 -m pytest ingestion/tests/ -v

test-alerts:
	python3 -m pytest alerts/tests/ -v

test-api:
	python3 -m pytest api/tests/ -v

up-dev:
	docker compose -f docker-compose.dev.yml up --build

down-dev:
	docker compose -f docker-compose.dev.yml down -v
