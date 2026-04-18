# Catálogo de Tópicos MQTT

Versão: 1.0.0
Broker de referência: EMQX 5 / VerneMQ / Mosquitto 2 (com TLS 1.3 e mTLS).

## Princípios

1. Hierarquia fixa: `<domain>/<site>/<gateway>/<device>/<sensor>/<leaf>`.
2. Um tópico por tipo de mensagem — nunca multiplexar payloads diferentes no mesmo tópico.
3. `retained` é reservado para **estado** (LWT, modo operacional). Telemetria **nunca** é retained.
4. QoS 1 é o default. QoS 0 só para telemetria de altíssima frequência opcional (ex.: sísmica ao vivo). QoS 2 não é usado.
5. Nomes de segmento seguem a regex de identifier (`^[a-z0-9][a-z0-9_-]{0,63}$`).
6. Wildcards (`+`, `#`) **somente em subscribe**, nunca em publish.

---

## Tópicos

### Telemetria principal (uplink)

| Tópico | Payload | QoS | Retained | Emissor | Consumidor |
|---|---|---|---|---|---|
| `tel/<site>/<gw>/<dev>/<sensor>/meas` | `geo.telemetry.v1` | 1 | não | RTU via gateway | ingestion |
| `tel/<site>/<gw>/<dev>/<sensor>/burst` | array de `geo.telemetry.v1` (até 1 MB) | 1 | não | RTU (recuperação de buffer pós-outage) | ingestion |
| `tel/<site>/<gw>/<dev>/<sensor>/qa` | flags QA/QC adicionais calculados no edge | 1 | não | gateway | analytics |

### Estado de dispositivo

| Tópico | Payload | QoS | Retained | Emissor |
|---|---|---|---|---|
| `state/<site>/<gw>/online` | `true` / `false` (JSON booleano) | 1 | **sim** | gateway; LWT = `false` |
| `state/<site>/<gw>/<dev>/online` | idem | 1 | **sim** | gateway publica pelo RTU |
| `state/<site>/<gw>/<dev>/sampling_mode` | `NORMAL` / `ATENCAO` / `ALERTA` / `EMERGENCIA` | 1 | **sim** | gateway reflete estado atual |
| `state/<site>/<gw>/<dev>/firmware` | versão atualmente rodando | 1 | **sim** | RTU ao subir |

### Saúde (heartbeat)

| Tópico | Payload | QoS | Retained | Periodicidade |
|---|---|---|---|---|
| `health/<site>/<gw>/<dev>` | `geo.health.v1` | 1 | não | 5 min (NORMAL); 1 min (ALERTA) |
| `health/<site>/<gw>` | `geo.health.v1` (gateway-level) | 1 | não | 1 min |

### Downlink (comandos)

| Tópico | Payload | QoS | Retained | Emissor | Consumidor |
|---|---|---|---|---|---|
| `cmd/<site>/<gw>/<dev>` | `geo.command.v1` | 1 | não | backend | gateway → RTU |
| `cmd/<site>/<gw>` | `geo.command.v1` (gateway-level) | 1 | não | backend | gateway |
| `ack/<site>/<gw>/<dev>/<correlation_id>` | `geo.ack.v1` | 1 | não | RTU/gateway | backend |

### Alertas

| Tópico | Payload | QoS | Retained | Emissor |
|---|---|---|---|---|
| `alert/<site>/<structure>/<level>` | `geo.alert.v1` | 1 | não | alert engine |
| `alert/<site>/<structure>/ack` | `geo.alert.v1` com `acknowledgement` | 1 | não | backend (pós-reconhecimento) |

### Infraestrutura do broker

| Tópico | Payload | Observação |
|---|---|---|
| `$SYS/#` | métricas do broker | uso restrito a operadores |

---

## Padrões de subscribe

| Consumidor | Subscribe pattern | Justificativa |
|---|---|---|
| Ingestion | `tel/+/+/+/+/meas`, `tel/+/+/+/+/burst` | captura toda telemetria |
| Alert engine | `tel/+/+/+/+/meas` | mesma fonte; regras filtram |
| UI realtime | `alert/+/+/+`, `state/+/+/+/sampling_mode` | mudanças de estado |
| Operador de um site | `tel/<meu-site>/#`, `alert/<meu-site>/#`, `state/<meu-site>/#` | ACL restringe ao próprio site |
| Ops infra | `health/#`, `$SYS/#` | visão transversal |

---

## Naming conventions

- `<site>`: `site_id` de convenção (ex.: `mineradora-x-barragem-norte`).
- `<gw>`: `gw-<slug>-<num>` (ex.: `gw-bx-001`).
- `<dev>`: `rtu-<slug>-<num>` (ex.: `rtu-bx-003`).
- `<sensor>`: `sensor_id` completo (ex.: `pz-sec01-fund-01`).
- `<structure>`: identificador de estrutura dentro do site.
- `<level>`: `atencao` | `alerta` | `emergencia_n1` | `emergencia_n2`.

---

## Exemplos concretos (Barragem X)

```
tel/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1/pz-sec02-fund-01/meas
tel/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1/rain-crista-01/meas
state/mineradora-x-barragem-norte/gw-bx-001/online
health/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-e1
cmd/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1
ack/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1/01HK4X9Q8RX200000000000042
alert/mineradora-x-barragem-norte/barragem-principal/alerta
```
