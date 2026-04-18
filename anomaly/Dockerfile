FROM python:3.12-slim AS base

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

WORKDIR /app

COPY anomaly/requirements.txt /app/anomaly-requirements.txt
RUN pip install --no-cache-dir -r /app/anomaly-requirements.txt

COPY anomaly/src /app/src

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER app

ENTRYPOINT ["python3", "-m", "anomaly.main"]
