FROM python:3.12-slim AS base

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

WORKDIR /app

# Dependencies first for better layer caching
COPY ingestion/requirements.txt /app/ingestion-requirements.txt
COPY tools/requirements.txt /app/tools-requirements.txt
RUN pip install --no-cache-dir -r /app/ingestion-requirements.txt \
                                -r /app/tools-requirements.txt

# Source
COPY ingestion/src /app/src
COPY tools /app/tools
COPY schemas /app/schemas

ENV PYTHONPATH=/app/src:/app/tools
ENV PYTHONUNBUFFERED=1

USER app

ENTRYPOINT ["python3", "-m", "ingestion.main"]
