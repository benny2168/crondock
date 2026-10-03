FROM node:lts-slim

LABEL org.opencontainers.image.title="Vaultwarden Multi-Instance Sync"
LABEL org.opencontainers.image.description="Sync items, TOTP, and Passkeys between Vaultwarden instances"

# Install Bitwarden CLI and Python runtime
RUN npm install -g @bitwarden/cli && npm cache clean --force
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
