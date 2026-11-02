#!/usr/bin/env bash
# sbx_cloud_fanout.sh — Docker Cloud Sandbox Orchestration & $250 Credit Guardrail Script
# Execute on Scabbers: chmod +x sbx_cloud_fanout.sh && ./sbx_cloud_fanout.sh <command>


set -euo pipefail


SANDBOX_CORE="mcp-core"
SANDBOX_CHAOS="chaos-harness"
SANDBOX_PROD="mcp-chaos-prod"
VOLUME_NAME="chaos-telemetry-vol"
TTL_LIMIT="8h"


COMMAND="${1:-status}"


case "$COMMAND" in
  init-secrets)
    echo "[1/3] Authenticating Docker Sandboxes CLI (sbx)..."
    sbx login
    echo "[2/3] Setting out-of-band proxy secrets (never stored inside microVM filesystem)..."
    sbx secret set anthropic
    sbx --cloud secret set anthropic
    echo "[3/3] Creating persistent cloud volume: $VOLUME_NAME..."
    sbx volume create "$VOLUME_NAME"
    ;;


  local-dev)
    echo "Spawning isolated local microVMs (zero cloud credit burn)..."
    sbx run --name "$SANDBOX_CORE" claude .
    ;;


  promote-cloud)
    echo "Promoting validated local sandbox ($SANDBOX_CORE) to Docker Cloud with TTL=$TTL_LIMIT..."
    sbx move "$SANDBOX_CORE" --to cloud --ttl "$TTL_LIMIT"
    ;;


  launch-prod)
    echo "Launching sized Docker Cloud Sandbox ($SANDBOX_PROD: 2 vCPU, 4 GiB RAM @ $0.14/hr)..."
    sbx run --cloud claude --name "$SANDBOX_PROD" --cpus 2 --memory 4g
    sbx volume attach "$VOLUME_NAME" "$SANDBOX_PROD"
    ;;


  run-overnight-suite)
    echo "Triggering 65-config AgentChaos resilience suite inside $SANDBOX_PROD..."
    sbx --cloud exec "$SANDBOX_PROD" -- pytest test_chaos_sandbox.py -v
    ;;


  status)
    echo "=== Active Docker Cloud Sandboxes & Exposed Ports ==="
    sbx --cloud ls
    sbx --cloud ports "$SANDBOX_PROD" || true
    ;;


  cleanup)
    echo "Tearing down cloud microVM ($SANDBOX_PROD) to preserve $250 challenge credit..."
    sbx --cloud rm "$SANDBOX_PROD"
    ;;


  *)
    echo "Usage: $0 {init-secrets|local-dev|promote-cloud|launch-prod|run-overnight-suite|status|cleanup}"
    exit 1
    ;;
esac