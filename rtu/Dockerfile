FROM python:3.12-slim AS base

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

WORKDIR /app

COPY rtu/requirements.txt /app/rtu-requirements.txt
RUN pip install --no-cache-dir -r /app/rtu-requirements.txt

COPY rtu/src /app/src

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER app

ENTRYPOINT ["python3", "-m", "rtu.main"]
