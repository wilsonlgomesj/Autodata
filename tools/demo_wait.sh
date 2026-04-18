#!/usr/bin/env bash
# Poll the dev stack's health endpoints until each service is ready.
# Prints a green check for each service that comes online, red cross otherwise.

set -u

GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

wait_url() {
  local url="$1"
  local name="$2"
  local max="${3:-60}"
  local i=0
  printf "  %-10s " "$name"
  while (( i < max )); do
    if curl -sf -o /dev/null --max-time 2 "$url"; then
      printf "${GREEN}ready${RESET} (%ds)\n" "$i"
      return 0
    fi
    ((i++))
    sleep 1
    printf "."
  done
  printf " ${RED}timeout${RESET} after %ds\n" "$max"
  return 1
}

wait_port() {
  local host="$1"
  local port="$2"
  local name="$3"
  local max="${4:-60}"
  local i=0
  printf "  %-10s " "$name"
  while (( i < max )); do
    if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
      printf "${GREEN}ready${RESET} (%ds)\n" "$i"
      return 0
    fi
    ((i++))
    sleep 1
    printf "."
  done
  printf " ${RED}timeout${RESET} after %ds\n" "$max"
  return 1
}

rc=0
wait_url  "http://localhost:8080/health"        "API"        120 || rc=1
wait_url  "http://localhost:8082"               "Frontend"    90 || rc=1
wait_url  "http://localhost:3000/api/health"    "Grafana"     90 || rc=1
wait_url  "http://localhost:8025"               "MailHog"     30 || rc=1
wait_port "localhost" 1883                      "MQTT"        60 || rc=1
wait_port "localhost" 5432                      "Postgres"    60 || rc=1

if (( rc != 0 )); then
  printf "\n${YELLOW}some services did not come up; check 'make demo-logs'${RESET}\n"
fi
exit $rc
