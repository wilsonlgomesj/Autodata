FROM python:3.12-slim AS base

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

WORKDIR /app

COPY alerts/requirements.txt /app/alerts-requirements.txt
RUN pip install --no-cache-dir -r /app/alerts-requirements.txt

COPY alerts/src /app/src
COPY alerts/rules /app/rules

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV RULES_PATH=/app/rules

USER app

ENTRYPOINT ["python3", "-m", "alerts.main"]
