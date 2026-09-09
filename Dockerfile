FROM python:3.11-alpine

LABEL org.opencontainers.image.title="CronDock"
LABEL org.opencontainers.image.description="Visual cron job manager with web UI"
LABEL org.opencontainers.image.source="https://github.com/mtcdtech/crondock"

# Runtime deps (curl, docker-cli, sqlite, ssh, rsync, tar for shell jobs)
RUN apk add --no-cache curl tzdata bash docker-cli sqlite openssh-client rsync tar

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
