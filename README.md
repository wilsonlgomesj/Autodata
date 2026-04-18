# Autodata — Sistema de Telemetria Geotécnica

Contrato de dados, schemas e metadata para telemetria de instrumentação
geotécnica (barragens, taludes). Fase 1 do projeto: **fundação do contrato
ponta-a-ponta** (payload, metadata, plano de instrumentação) com validação
automática.

## Estrutura

```
.
├── docs/
│   └── conventions.md           Convenções normativas (IDs, enums, QA/QC, versioning)
├── schemas/
│   ├── geo.telemetry.v1.schema.json    Payload canônico de medição
│   ├── geo.telemetry.v1.proto          Mesmo contrato em Protobuf
│   ├── geo.health.v1.schema.json       Heartbeat de dispositivo
│   ├── geo.alert.v1.schema.json        Evento de alerta
│   └── geo.command.v1.schema.json      Comando downlink
├── mqtt/
│   ├── topics.md                Catálogo de tópicos hierárquicos
│   └── acl.example.conf         ACL de exemplo (EMQX/Mosquitto)
├── metadata/
│   ├── schema.sql               DDL Postgres (org, site, structure, sensor, ...)
│   ├── erd.md                   Diagrama textual das entidades
│   └── seeds/
│       └── barragem_x.sql       Site-exemplo realista (Barragem X)
├── instrumentation/
│   ├── template.yaml            Plano de instrumentação — template
│   └── barragem_x.yaml          Plano da Barragem X (consistente com seed)
├── examples/payloads/           Exemplos de payload para cada caso (válidos em CI)
├── tools/
│   ├── validate.py              CLI de validação
│   ├── test_validator.py        Suite negativa (garante que rejeições funcionam)
│   └── requirements.txt
└── .github/workflows/validate.yml
```

## Quickstart

```bash
pip install -r tools/requirements.txt

# Valida tudo (schemas + plans + crosscheck plan ↔ seed SQL)
python3 tools/validate.py all

# Valida um payload específico
python3 tools/validate.py payload examples/payloads/piezometer_vw_good.json

# Valida um plano de instrumentação
python3 tools/validate.py plan instrumentation/barragem_x.yaml

# Garante que o plano YAML e o seed SQL referenciam os mesmos IDs
python3 tools/validate.py crosscheck \
    instrumentation/barragem_x.yaml \
    metadata/seeds/barragem_x.sql

# Suite negativa (deve listar 8 rejeições esperadas)
python3 tools/test_validator.py
```

## Fluxo de evolução

1. **Mudança backward-compatible** (novo `sensor_type`, novo campo opcional):
   bump **minor** do repositório, mantém `v<major>` dos schemas.
2. **Mudança breaking**: bump **major**. Novo `v<major>` coexiste com o anterior
   por no mínimo 12 meses.
3. Toda mudança exige:
   - Atualização em `docs/conventions.md`.
   - Exemplos em `examples/payloads/` refletindo a mudança.
   - CI verde (`python3 tools/validate.py all` + `test_validator.py`).
   - Entrada em `CHANGELOG.md`.

## Serviço de ingestão

Pipeline MQTT → validação → Postgres/TimescaleDB com idempotência por `msg_id`.

```
ingestion/
├── src/ingestion/    config, db, validator, persister, handler, mqtt_client, main
├── tests/            13 unit tests (fake executor, sem infra real)
├── requirements.txt
└── Dockerfile
```

Regras de segurança implementadas:

- Validação contra JSON Schema antes de persistir.
- `topic vs. payload mismatch` detection: device não pode publicar sobre o
  escopo de outro site (defesa em profundidade além da ACL do broker).
- Idempotência: `ON CONFLICT (site, sensor, metric, msg_id) DO NOTHING`.
- Dead-letter queue em `geo.dead_letter` para toda falha (parse, schema,
  mismatch, DB error).

### Rodar localmente (dev)

```bash
# Stack completa: TimescaleDB + Mosquitto + serviço de ingestão
docker compose -f docker-compose.dev.yml up --build

# Publicar uma mensagem de teste (precisa de mosquitto-clients instalado)
mosquitto_pub -h localhost -t \
  'tel/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1/pz-sec02-fund-01/meas' \
  -f examples/payloads/piezometer_vw_good.json

# Verificar persistência
psql postgresql://autodata:devpassword@localhost:5432/autodata \
  -c 'SELECT * FROM geo.measurement ORDER BY t_sample DESC LIMIT 10;'
```

### Testes

```bash
pip install -r ingestion/requirements.txt pytest
python3 -m pytest ingestion/tests/ -v
```

## Alert engine

Motor de regras declarativas em YAML, versionadas em Git. Avaliador com
persistência (duração), histerese e confirmação multi-sensor.

```
alerts/
├── src/alerts/    rules, evaluator, emitter, service, mqtt_runner, thresholds
├── rules/         regras YAML versionadas (barragem_x.yaml)
├── tests/         25 testes (rule parsing, state machine, confirmation)
├── requirements.txt
└── Dockerfile
```

Três mecanismos anti-falso-positivo implementados:

- **persistence**: rule só dispara após N segundos contínuos acima do threshold.
- **hysteresis**: release só ocorre depois que o valor recua além da banda
  `threshold × (1 - hysteresis_pct)`.
- **confirm_count**: EMERGENCIA_N2 só dispara com N sensores simultâneos
  acima do threshold dentro de janela configurável.

Thresholds são carregados do Postgres (`geo.threshold`) com cache TTL e podem
também ser literais na regra (`value: 420`).

```bash
pip install -r alerts/requirements.txt pytest
python3 -m pytest alerts/tests/ -v
```

## Read API (GraphQL)

API read-only sobre TimescaleDB. Strawberry + FastAPI. Queries principais:

- `sites`, `site(siteId)`, `structures(siteId)`, `sensors(siteId, ...)`
- `latestMeasurements(siteId, sensorId)`
- `timeseries(siteId, sensorId, metric, tFrom, tTo, resolution)` — `resolution`
  ∈ `raw | 1min | 1h` escolhe entre hypertable bruta e continuous aggregates.
- `alerts(siteId, level, since, limit)`

```
api/
├── src/api/       repository, schema, db, app
├── tests/         12 testes (repository + GraphQL resolvers)
├── requirements.txt
└── Dockerfile
```

GraphiQL disponível em `http://localhost:8080/graphql` quando `AUTH_DISABLED=true`
(dev). Em produção, auth via OIDC/Keycloak (stub em `app.require_auth`).

```bash
pip install -r api/requirements.txt pytest
python3 -m pytest api/tests/ -v
```

## RTU reference firmware (`rtu/`)

Simulador Python com Ed25519 real (assinatura sobre JSON canônico excluindo
`sig` e `t_ingest`). Store-and-forward em SQLite. Publica em MQTT com QoS 1
e só marca como enviado após PUBACK.

Chave privada: arquivo PEM via `PRIVATE_KEY_PEM` — se ausente, gera
efêmera e imprime a pública para provisionamento em `geo.device`.

## Notifications dispatcher (`notifications/`)

Consome `alert/+/+/+`. Roteamento por `min_level` + escopo de site + glob
de `rule_id` + filtro de estrutura. Canais: email (SMTP), webhook,
SMS (stub Twilio-like), voz (stub). `geo.notification_dispatch` é
append-only com UNIQUE `(alert_msg_id, route_id, channel)` — idempotente.

## Dashboard Grafana (`grafana/`)

Provisioning automático na inicialização:

- Datasource `TimescaleDB` apontando para o Postgres/TSDB.
- Dashboard `Autodata — Barragem (por site)` com variável dinâmica `$site`
  populada de `geo.site`.

Painéis:

1. Poropressão multi-PZ com thresholds (atencao → emergencia_n2) como bandas
2. Último valor por PZ fundação (stat colorido)
3. Chuva 24h acumulada (bars)
4. Inclinômetros crista (tilt X/Y)
5. Tabela de alertas ativos com cor por nível
6. Tabela de notificações da última hora (latência, erros)
7. Saúde — mensagens/15min, dead-letter/24h, sensores ativos
8. Annotations overlay de cada alerta disparado

## Frontend (`frontend/`)

SPA em React + Vite + TypeScript demonstrando todas as funcionalidades.
Páginas: visão geral com mapa + KPIs, sensores com timeseries, alertas
com reconhecimento MFA-gated, editor de thresholds time-versioned, emissão
de comandos MQTT, log de notificações. Stack: Tailwind + Apollo +
react-leaflet + Recharts.

## Demo de cliente — um comando

```bash
make demo
```

Sobe o stack completo em background, aguarda cada serviço reportar healthy
e imprime as URLs prontas para abrir no navegador:

```
Frontend   http://localhost:8082
GraphiQL   http://localhost:8080/graphql
Grafana    http://localhost:3000     (admin/admin)
Keycloak   http://localhost:8081     (admin/admin)
MailHog    http://localhost:8025
```

Demora ~5-10 min na primeira execução (build dos containers). Depois:

```bash
make demo-open             # abre o frontend no navegador padrão
make demo-trigger-alert    # dispara EMERGENCIA_N2 em segundos (demo momento)
make demo-status           # estado dos containers
make demo-logs             # tail dos logs
make demo-down             # para tudo e remove volumes
make demo-reset            # down + demo
```

`make demo-trigger-alert` publica dois piezômetros simultaneamente acima de
500 kPa — aciona a regra `pz-emergencia-confirmado` (persistence=PT0S,
confirm_count=2) imediatamente. Você verá dentro de segundos:

1. Alerta **EMERGENCIA_N2** vermelho na aba Alertas
2. Email capturado em MailHog
3. Anotação no dashboard Grafana
4. Registro em Notificações com latência de cada canal

Outros cenários:

```bash
make demo-trigger-alert-scenario SCENARIO=alert      # fires após PT30M
make demo-trigger-alert-scenario SCENARIO=attention  # PT1H
make demo-trigger-alert-scenario SCENARIO=normal     # baseline sem alertar
```

## Stack manual (sem Makefile)

```bash
docker compose -f docker-compose.dev.yml up --build
```

## Próximos passos

- Firmware de RTU para microcontrolador real (ESP32/STM32) em C++.
- Auth real via Keycloak com RBAC por site, MFA obrigatório em
  `acknowledgeAlert` e `updateThreshold`.
- Integração SCADA via OPC UA.
- ML para detecção de anomalias multivariada (autoencoder LSTM).
- GIS com PostGIS + QGIS Server.
