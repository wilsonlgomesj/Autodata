# Convenções do Sistema de Telemetria Geotécnica

Documento normativo. Alterações aqui exigem bump de versão e PR com aprovação
de engenharia + segurança de barragem.

Versão: 1.0.0
Data: 2026-04-18

---

## 1. Identificadores

Todos os identificadores são strings ASCII. Comprimento máximo 64 caracteres.
Regex geral: `^[a-z0-9][a-z0-9_-]{0,63}$`.

### 1.1 `site_id`

Identificador único do empreendimento (barragem, talude, conjunto de estruturas
geridas como uma unidade).

- Formato: `<org>-<slug>` (ex.: `mineradora-x-barragem-norte`).
- Imutável após criação.
- Usado como particionamento lógico no broker MQTT e em ACLs.

### 1.2 `structure_id`

Estrutura física dentro do site (uma barragem, um talude, um reservatório).

- Formato: `<site_id>/<slug>` no contexto canônico; `<slug>` local dentro do site.
- Uma site pode ter N estruturas (ex.: barragem principal + dique auxiliar).

### 1.3 `section_id`

Seção instrumentada de uma estrutura.

- Formato local: `sec-<num>` (ex.: `sec-01`, `sec-02-ombreira-esq`).
- Cada seção agrupa sensores por corte transversal.

### 1.4 `sensor_id`

Identificador canônico de um sensor individual.

- Formato: `<type_prefix>-<section>-<ordinal>`
- Prefixos padronizados: ver §2.
- Exemplos:
  - `pz-sec01-fund-01` (piezômetro VW na fundação da seção 1, primeiro)
  - `ipi-sec02-03` (inclinômetro na seção 2, terceiro anel)
  - `gnss-crista-04`

Sensor_id é **globalmente único dentro do site**. A tupla `(site_id, sensor_id)` é
globalmente única no sistema.

### 1.5 `device_id` (RTU, gateway)

Hardware físico que executa aquisição ou concentração.

- RTU: `rtu-<site_slug>-<num>` (ex.: `rtu-bx-001`).
- Gateway/concentrador: `gw-<site_slug>-<num>` (ex.: `gw-bx-001`).
- Serial number do hardware fica em metadata, não no ID.

### 1.6 `msg_id`

Identificador idempotente de mensagem. Obrigatório em toda publicação de
telemetria, health, alerta e comando.

- Formato: **ULID** (Universally Unique Lexicographically Sortable Identifier,
  26 caracteres, case-insensitive, ordenável por tempo).
- Geração: no dispositivo que origina a mensagem (RTU para telemetria, backend
  para comandos).
- Regra de idempotência: o backend **deve** deduplicar por `(site_id, msg_id)`
  em janela de 7 dias. Reenvios após store-and-forward nunca duplicam dados.

### 1.7 `correlation_id`

Usado em comandos e respostas. ULID. Propagado em todo o fluxo (log, auditoria).

---

## 2. Enum `sensor_type`

Lista canônica de tipos de sensor. Adicionar novo tipo exige bump minor do
schema. Remover exige bump major.

| `sensor_type` | Prefixo em `sensor_id` | Grandezas publicadas | Unidade SI canônica |
|---|---|---|---|
| `piezometer_vw` | `pz` | pressure, frequency, temperature | kPa, Hz, °C |
| `piezometer_casagrande` | `pzc` | water_level | m |
| `inclinometer_ipi_mems` | `ipi` | tilt_x, tilt_y, temperature | deg, deg, °C |
| `inclinometer_probe` | `incp` | tilt_x, tilt_y (por profundidade) | deg |
| `extensometer_magnetic` | `ext` | displacement | mm |
| `extensometer_multipoint` | `extm` | displacement (por ancoragem) | mm |
| `load_cell` | `lc` | force | kN |
| `settlement_cell` | `sc` | settlement | mm |
| `gnss_rover` | `gnss` | displacement_n, displacement_e, displacement_u | mm |
| `total_station_prism` | `prism` | displacement_n, displacement_e, displacement_u | mm |
| `rain_gauge_tipping` | `rain` | rainfall (por intervalo), cumulative | mm, mm |
| `flow_meter_weir` | `flow` | flow_rate, water_level | L/s, m |
| `seismograph_mems` | `seis` | accel_x, accel_y, accel_z, pga | g, g, g, g |
| `fiber_optic_dts` | `dts` | temperature (array por posição) | °C |
| `fiber_optic_dss` | `dss` | strain (array por posição) | µε |
| `weather_station` | `met` | air_temp, humidity, wind_speed, wind_dir, pressure, solar_rad | °C, %, m/s, deg, hPa, W/m² |
| `thermistor_string` | `therm` | temperature (array) | °C |
| `power_monitor` | `pwr` | v_bat, v_panel, i_charge, i_load, soc | V, V, A, A, % |

**Regra de unidade**: a unidade SI canônica é **a única** aceita no payload.
Conversão de unidades é responsabilidade do RTU antes da publicação. O backend
confia na unidade declarada no schema e nunca adivinha.

---

## 3. Códigos de Qualidade (QA/QC)

Cada amostra carrega um `quality.code` e zero ou mais `quality.flags`.

### 3.1 `quality.code` (enum)

| Código | Significado | Uso em alerta? |
|---|---|---|
| `GOOD` | Passou em todas as validações | Sim |
| `SUSPECT` | Falhou em validação branda (ex.: step check, cross-sensor) | Sim, com peso reduzido |
| `BAD` | Falhou em validação crítica (ex.: fora do range físico do sensor) | Não, mas não descartado |
| `MISSING` | Amostra esperada não chegou (gap detectado no backend) | Não, mas conta como evento |
| `CALIBRATING` | Sensor em calibração, valor não representa grandeza física | Não |
| `MAINTENANCE` | Sensor em manutenção declarada | Não |

### 3.2 `quality.flags` (lista, pode combinar)

| Flag | Disparador |
|---|---|
| `RANGE` | Valor fora do intervalo físico declarado do sensor |
| `STEP` | \|Δ entre amostras consecutivas\| > limite configurado |
| `STUCK` | Variância móvel em janela N abaixo de ε |
| `RATE` | d/dt > k·σ_histórico |
| `CROSS_SENSOR` | Sensores gêmeos divergem além da tolerância |
| `BRACKETING` | Valor fora do envelope hidrostático esperado |
| `GAP` | Tempo desde última amostra > esperado |
| `LOW_VOLTAGE` | V_bat do dispositivo < limite |
| `SIG_INVALID` | Falha de verificação de assinatura na ingestão |
| `SCHEMA_DOWNGRADE` | Mensagem recebida em schema inferior ao vigente |

Uma amostra pode ter `code=GOOD` com nenhum flag, `code=SUSPECT` com um ou mais
flags, ou `code=BAD` com flags indicando o motivo. **Nenhum dado é descartado**
por QA/QC; sempre é armazenado com seu código/flags.

---

## 4. Timestamps

- Todos os timestamps são **RFC 3339** em **UTC** com precisão de milissegundos.
- Formato: `2026-04-18T13:45:03.123Z`.
- Cada mensagem carrega:
  - `t_sample`: momento da medição, atribuído pelo RTU (GNSS-disciplined quando
    disponível).
  - `t_ingest`: atribuído pelo ingestion service no backend (preenchido nulo no
    envio).
- Relógios devem estar sincronizados dentro de ±1 s entre RTUs e ±100 ms do UTC.

---

## 5. Versionamento de Schema

- Campo obrigatório `schema` em toda mensagem.
- Formato: `geo.<domínio>.v<major>` (ex.: `geo.telemetry.v1`).
- Compatibilidade:
  - Mudança **backward-compatible** (adicionar campo opcional, novo `sensor_type`): bump **minor** do repositório, `v<major>` mantém.
  - Mudança **breaking** (remover campo, mudar unidade, renomear): bump **major**, novo `v<major>`. Os dois vigoram em paralelo por no mínimo 12 meses.
- Toda release exige:
  - Atualização deste documento.
  - Changelog em `CHANGELOG.md`.
  - Exemplos em `examples/payloads/` válidos contra a nova versão.
  - Validador CLI passando no CI.

---

## 6. Convenções de Tópicos MQTT

Ver `mqtt/topics.md` — espelha a hierarquia `site → gateway → device → sensor`.

---

## 7. Políticas de Retenção (resumo)

Para detalhes, ver arquitetura. Aqui só o essencial para consistência do schema:

- Bruto em TimescaleDB: 90 dias online.
- Agregados: 2 anos (1 min) / 15 anos (1 h).
- Arquivo imutável assinado em object storage WORM: 15 anos.
