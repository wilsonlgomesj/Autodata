# Autodata — Frontend

SPA em React + Vite + TypeScript que demonstra todas as funcionalidades
do sistema. Consome a API GraphQL + REST em `api/` (porta 8080).

## Stack

- Vite + React 18 + TypeScript
- Tailwind CSS para estilização
- Apollo Client para GraphQL
- react-leaflet + OpenStreetMap tiles para mapa
- Recharts para séries temporais
- date-fns (pt-BR) para formatação

## Páginas

| Rota | O que demonstra |
|---|---|
| `/`              | Visão geral: mapa, KPIs, alertas recentes |
| `/sensors`       | Lista de sensores com filtros |
| `/sensors/:id`   | Timeseries (raw / 1min / 1h), últimas leituras |
| `/alerts`        | Tabela de alertas + modal de reconhecimento (MFA) |
| `/thresholds`    | Editor de limites — mutation time-versioned |
| `/commands`      | Emissão de comando downlink MQTT |
| `/notifications` | Log append-only de dispatches |

## Auth em dev

O backend roda com `AUTH_DISABLED=true` e aceita headers
`X-Dev-User`, `X-Dev-Roles`, `X-Dev-Mfa` para simular identidades.
O toggle **MFA ON/OFF** no topo alterna o claim para demonstrar:

- com **MFA ON**: ackAlert, updateThreshold e issueCommand passam
- com **MFA OFF**: as mutations são rejeitadas com 403 pelo guarda do
  backend

## Dev

```bash
npm install
npm run dev       # Vite na :5173 — aponta para http://localhost:8080
```

## Build

```bash
npm run typecheck
npm run build     # gera dist/
npm run preview   # serve dist/ para smoke-test
```

## Docker

```bash
# Standalone
docker build -t autodata-frontend -f Dockerfile ..
docker run -p 8082:80 autodata-frontend

# Junto com o stack completo
docker compose -f ../docker-compose.dev.yml up --build
# → http://localhost:8082
```
