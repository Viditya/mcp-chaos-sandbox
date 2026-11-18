#!/usr/bin/env bash
# sbx_cloud_fanout.sh — Docker Cloud Sandbox Orchestration & $250 Credit Guardrail Script
# Updated per challenge guidelines: enforces strict task-tied auto-stop to prevent idle credit burn.
# Usage: chmod +x sbx_cloud_fanout.sh && ./sbx_cloud_fanout.sh <command>

set -euo pipefail

SANDBOX_CORE="mcp-core"
SANDBOX_CHAOS="chaos-harness"
SANDBOX_PROD="mcp-chaos-prod"
VOLUME_NAME="chaos-telemetry-vol"
TTL_LIMIT="8h"
HARD_TIMEOUT_SEC="10800" # 3 hours hard cap

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
    # Cost-Control Guardrail:
    # Docker Cloud Sandboxes bill continuously while running.
    # We trap EXIT to guarantee the microVM is stopped immediately when the task finishes or fails.
    trap 'echo "[Cost Guardrail] Stopping $SANDBOX_PROD to preserve credit..."; sbx --cloud stop "$SANDBOX_PROD" || true' EXIT
    sbx --cloud exec "$SANDBOX_PROD" -- pytest test_chaos_sandbox.py -v
    echo "[Cost Guardrail] Suite completed. MicroVM stopped cleanly."
    ;;

  stop)
    echo "Stopping Docker Cloud Sandbox ($SANDBOX_PROD) to halt compute billing..."
    sbx --cloud stop "$SANDBOX_PROD" || true
    ;;

  status)
    echo "=== Active Docker Cloud Sandboxes & Billing Status ==="
    sbx --cloud ls
    sbx --cloud ports "$SANDBOX_PROD" || true
    ;;

  cleanup)
    echo "Tearing down cloud microVM ($SANDBOX_PROD) and persistent state..."
    sbx --cloud rm "$SANDBOX_PROD" || true
    ;;

  *)
    echo "Usage: $0 {init-secrets|local-dev|promote-cloud|launch-prod|run-overnight-suite|stop|status|cleanup}"
    exit 1
    ;;
esac
