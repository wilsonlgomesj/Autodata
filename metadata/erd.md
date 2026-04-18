# ERD — Metadata do Sistema

Representação textual. Relações mostradas como `A → B` significam "A referencia B".

```
organization (1) ───< site (N)
                        │
                        ├──< structure (N) ──< section (N) ──< sensor (N)
                        │                                        │
                        ├──< device (N) ────────────────────────┘ (sensor.device_id)
                        │
                        ├──< alert_rule (N) ──< alert_event (N)
                        │
                        └──< role_assignment (N) >── app_user (1)

sensor (1) ──< calibration (N, time-versioned)
sensor (1) ──< threshold   (N, time-versioned, por metric)
sensor (1) ──> sensor       (self, twin_sensor_id, par redundante)

app_user (1) ──< audit_event (N)
```

## Cardinalidades e regras de integridade

| De → Para | Cardinalidade | Regra |
|---|---|---|
| `site → organization` | N:1 | Site sempre pertence a uma org |
| `structure → site` | N:1 (composto) | PK `(site_id, structure_id)` |
| `section → structure` | N:1 | PK `(site_id, structure_id, section_id)` |
| `device → site` | N:1 | RTU exige `parent_gateway` não nulo; gateway tem `parent_gateway` nulo |
| `sensor → section` | N:1 | FK composta `(site, structure, section)` |
| `sensor → device` | N:1 | Cada sensor é lido por um RTU |
| `sensor → sensor (twin)` | 0..1 auto-ref | Deferred — permite criar par simultaneamente |
| `calibration → sensor` | N:1 | Apenas uma calibração corrente (`effective_to IS NULL`) por sensor |
| `threshold → sensor` | N:1 | Apenas um threshold corrente por `(sensor, metric)` |
| `alert_event → alert_rule` | N:1 | Evento referencia regra + versão |
| `role_assignment` | N:N | Usuário × site × role |
| `audit_event` | append-only | Trigger bloqueia UPDATE/DELETE |

## Princípios de modelagem

1. **IDs naturais, não surrogados**: `(site_id, sensor_id)` é a chave natural do sensor. FKs compostas garantem que referências nunca cruzem sites acidentalmente.
2. **Time-versioning em mudanças significativas**: calibração e threshold mantêm histórico completo. Consultas "qual era o threshold em `t`" são triviais.
3. **Soft-delete via `decommissioned_on`**: instrumentos decomissionados ficam no banco para preservar histórico de medições.
4. **Enum no banco + enum no JSON Schema**: nomes e valores idênticos, sincronizados via teste de CI que lê ambos.
5. **Auditoria imutável**: `audit_event` é append-only via trigger. Alterações em threshold e calibração **devem** escrever aqui.
6. **Separação metadata vs. time-series**: este schema é portável para qualquer Postgres. TimescaleDB é adicionado em migração separada.

## Convenções de nomeclatura

- Schema: `geo`.
- Tabelas: singular, snake_case (`site`, `sensor`, não `sites`, `sensors`).
- Colunas: snake_case, unidade no nome quando ambígua (`height_m`, `pressure_kpa`).
- Timestamps: `TIMESTAMPTZ` sempre; campos `t_*` para eventos, `*_at` para auditoria, `*_from/*_to` para intervalos de vigência, `*_on` para datas (sem hora).
