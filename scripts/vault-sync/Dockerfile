FROM node:lts-slim

LABEL org.opencontainers.image.title="Vaultwarden Multi-Instance Sync"
LABEL org.opencontainers.image.description="Sync items, TOTP, and Passkeys between Vaultwarden instances"

# Pin @bitwarden/cli to 2026.8.0 to maintain full Vaultwarden compatibility
# (2026.9.x introduces unbackported key_id_backfill API calls that fail on Vaultwarden)
RUN npm install -g @bitwarden/cli@2026.8.0 && npm cache clean --force
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dateutil \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY sync.py /app/sync.py

# Default data mount for BW_DATA_ROOT
RUN mkdir -p /bw-data
VOLUME ["/bw-data"]

ENV BW_DATA_ROOT=/bw-data \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "/app/sync.py"]
