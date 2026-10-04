#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Docker Cleanup Script — Prune Temporary & Unused Containers and Images
# ==============================================================================

echo "========================================================"
echo " Starting Docker Cleanup: $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo "========================================================"

prune_portainer_endpoint() {
  local name="$1"
  local base_url="$2"
  local token="$3"
  local endpoint_id="$4"

  echo ""
  echo "--- Pruning Portainer: ${name} (Endpoint ${endpoint_id}) ---"
  
  if [ -z "${base_url}" ] || [ -z "${token}" ] || [ -z "${endpoint_id}" ]; then
    echo "Skipping ${name}: configuration incomplete"
    return 0
  fi

  # 1. Prune temporary and unused containers
  echo "Pruning temporary and unused containers..."
  local res
  res=$(curl -s -k -X POST \
    -H "X-API-Key: ${token}" \
    "${base_url}/api/endpoints/${endpoint_id}/docker/containers/prune" 2>&1 || true)

  if echo "${res}" | grep -q "ContainersDeleted"; then
    echo "✓ Container prune response: ${res}"
  else
    echo "ℹ Container prune notice: ${res}"
  fi

  # 2. Prune dangling/unused images
  echo "Pruning dangling and unused images..."
  local img_res
  img_res=$(curl -s -k -X POST \
    -H "X-API-Key: ${token}" \
    "${base_url}/api/endpoints/${endpoint_id}/docker/images/prune?filters=%7B%22dangling%22%3A%5B%22false%22%5D%7D" 2>&1 || true)
  echo "ℹ Image prune response: ${img_res}"

  # 3. Prune build cache
  echo "Pruning build cache..."
  curl -s -k -X POST \
    -H "X-API-Key: ${token}" \
    "${base_url}/api/endpoints/${endpoint_id}/docker/build/prune" >/dev/null 2>&1 || true
}

# 1. Prune MTCD Portainer
prune_portainer_endpoint \
  "MTCD Synology" \
  "${MTCD_PORTAINER_URL:-https://docker.server.mtcd.org}" \
  "${MTCD_PORTAINER_TOKEN:-ptr_caKh16OVXC+3G4shu9s7TXtumDZY04R6wwaOYkq+Pls=}" \
  "${MTCD_PORTAINER_ENDPOINT_ID:-2}"

# 2. Prune Abraham Portainer (if reachable)
prune_portainer_endpoint \
  "Abraham Synology" \
  "${ABRAHAM_PORTAINER_URL:-https://docker.abraham16.com}" \
  "${ABRAHAM_PORTAINER_TOKEN:-ptr_LAYVFvw5+DscmC2s2QsM+5aeO6iXGYcR4+KwjH7f/eU=}" \
  "${ABRAHAM_SYNOLOGY_ENDPOINT_ID:-5}"

prune_portainer_endpoint \
  "Mac Mini / OrbStack" \
  "${ABRAHAM_PORTAINER_URL:-https://docker.abraham16.com}" \
  "${ABRAHAM_PORTAINER_TOKEN:-ptr_LAYVFvw5+DscmC2s2QsM+5aeO6iXGYcR4+KwjH7f/eU=}" \
  "${ABRAHAM_MACMINI_ENDPOINT_ID:-3}"

# 3. Prune local Docker if Docker socket is available
if [ -S "/var/run/docker.sock" ] && command -v docker >/dev/null 2>&1; then
  echo ""
  echo "--- Pruning Local Docker Engine via /var/run/docker.sock ---"
  docker container prune -f || true
  docker image prune -f || true
fi

echo ""
echo "========================================================"
echo " Docker Cleanup Complete: $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo "========================================================"
