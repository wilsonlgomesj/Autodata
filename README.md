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

## Próximos passos

- Migração TimescaleDB para hypertable `measurement`.
- Motor de regras (OPA Rego) consumindo `threshold` e emitindo `geo.alert.v1`.
- Firmware de RTU de referência (store-and-forward, assinatura Ed25519).
- Ingestão (MQTT → Kafka → TimescaleDB) com idempotência por `msg_id`.
