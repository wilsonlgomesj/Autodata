.PHONY: test test-schemas test-ingestion test-alerts test-api test-rtu test-notifications validate fmt

# Runs all test suites. Because component package names (ingestion, alerts,
# api, rtu, notifications) collide with top-level directories, each suite
# is invoked separately with its own conftest injecting sys.path.
test: validate test-ingestion test-alerts test-api test-rtu test-notifications

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

test-rtu:
	python3 -m pytest rtu/tests/ -v

test-notifications:
	python3 -m pytest notifications/tests/ -v

up-dev:
	docker compose -f docker-compose.dev.yml up --build

down-dev:
	docker compose -f docker-compose.dev.yml down -v
