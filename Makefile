.PHONY: test test-schemas test-ingestion test-alerts test-api test-rtu \
        test-notifications test-anomaly validate fmt \
        demo demo-up demo-down demo-logs demo-status demo-reset demo-open \
        demo-trigger-alert demo-trigger-alert-scenario demo-help \
        up-dev down-dev

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Runs all test suites. Because component package names (ingestion, alerts,
# api, rtu, notifications, anomaly) collide with top-level directories,
# each suite is invoked separately with its own conftest injecting sys.path.
test: validate test-ingestion test-alerts test-api test-rtu test-notifications test-anomaly

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

test-anomaly:
	python3 -m pytest anomaly/tests/ -v

# ---------------------------------------------------------------------------
# Demo (one-liner stack orchestration for client walkthroughs)
# ---------------------------------------------------------------------------

COMPOSE := docker compose -f docker-compose.dev.yml

## demo: build + start stack in background, wait for readiness, print URLs
demo:
	@echo "→ Building and starting the stack (first run takes a few minutes)…"
	@$(COMPOSE) up --build -d
	@echo
	@echo "→ Waiting for services to report healthy…"
	@bash tools/demo_wait.sh || true
	@echo
	@echo "\033[32m✓ Stack ready. Open the panels:\033[0m"
	@echo
	@echo "  Frontend   http://localhost:8082"
	@echo "  GraphiQL   http://localhost:8080/graphql"
	@echo "  Grafana    http://localhost:3000     (admin/admin)"
	@echo "  Keycloak   http://localhost:8081     (admin/admin)"
	@echo "  MailHog    http://localhost:8025"
	@echo
	@echo "Demo actions:"
	@echo "  make demo-trigger-alert     dispara EMERGENCIA_N2 em segundos"
	@echo "  make demo-open              abre o frontend no navegador"
	@echo "  make demo-logs              acompanha logs de todos os serviços"
	@echo "  make demo-status            estado dos containers"
	@echo "  make demo-down              para tudo e remove volumes"
	@echo "  make demo-help              lista todos os comandos de demo"

demo-up:
	$(COMPOSE) up --build -d

demo-down:
	$(COMPOSE) down -v

demo-logs:
	$(COMPOSE) logs -f --tail=50

demo-status:
	$(COMPOSE) ps

demo-reset: demo-down demo

# Triggers an EMERGENCIA_N2 alert: publishes two PZ sensors above 500 kPa
# simultaneously, which satisfies the pz-emergencia-confirmado rule
# (persistence=PT0S, confirm_count=2) and fires immediately.
demo-trigger-alert:
	@python3 -c "import paho.mqtt.client" 2>/dev/null || pip install --quiet paho-mqtt
	@python3 tools/demo_trigger.py emergency

# demo-trigger-alert-scenario SCENARIO=alert make demo-trigger-alert-scenario
demo-trigger-alert-scenario:
	@python3 -c "import paho.mqtt.client" 2>/dev/null || pip install --quiet paho-mqtt
	@python3 tools/demo_trigger.py $(SCENARIO)

demo-open:
	@command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:8082 || \
	  command -v open >/dev/null 2>&1 && open http://localhost:8082 || \
	  echo "open http://localhost:8082 in your browser"

demo-help:
	@echo "Autodata demo commands:"
	@echo "  make demo                     build+up+wait+print URLs"
	@echo "  make demo-up                  up detached (no wait, no URLs)"
	@echo "  make demo-down                stop and remove volumes"
	@echo "  make demo-reset               down + demo"
	@echo "  make demo-status              docker compose ps"
	@echo "  make demo-logs                tail logs of all services"
	@echo "  make demo-trigger-alert       publish values that fire EMERGENCIA_N2"
	@echo "  make demo-trigger-alert-scenario SCENARIO=[emergency|alert|attention|normal]"
	@echo "  make demo-open                open the frontend in the default browser"

# Legacy targets (kept for backwards compatibility)
up-dev: demo-up
down-dev: demo-down
