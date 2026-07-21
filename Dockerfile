FROM python:3.11-alpine

LABEL org.opencontainers.image.title="CronDock"
LABEL org.opencontainers.image.description="Visual cron job manager with web UI"
LABEL org.opencontainers.image.source="https://github.com/benny2168/crondock"

# Runtime deps (curl available for shell jobs)
RUN apk add --no-cache curl tzdata bash

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

# Data volume for SQLite
RUN mkdir -p /data
VOLUME ["/data"]

ENV DATA_DIR=/data \
    TZ=America/Chicago \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
