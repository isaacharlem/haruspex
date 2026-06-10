#!/usr/bin/env bash
# End-to-end smoke against the compose stack:
#   wait healthy -> mint key -> register run -> ingest batch
#   -> forecast appears <= 30s -> SSE event observed -> policy dry-run responds
# Usage: scripts/smoke.sh   (BASE_URL and COMPOSE overridable via env)
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://localhost:8000}"
COMPOSE="${COMPOSE:-docker compose -f deploy/docker-compose.yml}"

say() { echo "smoke: $*"; }

say "waiting for $BASE_URL/healthz"
for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/healthz" > /dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$BASE_URL/readyz" > /dev/null
say "api healthy"

if [ -z "${HARUSPEX_API_KEY:-}" ]; then
  KEY=$($COMPOSE exec -T api python -m haruspex_server.cli mint-key \
        --name smoke --scopes ingest,read,admin | grep HARUSPEX_API_KEY | cut -d= -f2)
else
  KEY="$HARUSPEX_API_KEY"
fi
[ -n "$KEY" ] || { say "FAIL: could not mint an API key"; exit 1; }
AUTH="Authorization: Bearer $KEY"
say "key minted (${KEY:0:8}...)"

RUN_JSON=$(curl -fsS -X POST "$BASE_URL/v1/runs" -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "name": "smoke-run", "tags": ["smoke"], "target_metric": "loss", "target_value": 2.9,
  "direction": "min", "budget_steps": 200, "budget_wallclock_s": 600,
  "gpu_type": "H100", "gpu_count": 1
}')
RUN_ID=$(echo "$RUN_JSON" | sed 's/.*"id":\([0-9]*\).*/\1/')
say "registered run $RUN_ID"

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
POINTS=$(python3 - "$NOW" <<'EOF'
import json, sys
now = sys.argv[1]
points = [
    {"step": step, "ts": now, "name": name, "value": value}
    for step in range(60)
    for name, value in (("loss", 5.0 - step * 0.02), ("grad_norm", 1.5), ("lr", 3e-4))
]
print(json.dumps(points))
EOF
)
curl -fsS -X POST "$BASE_URL/v1/ingest" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"run_id\": $RUN_ID, \"client_batch_id\": \"smoke-1\", \"points\": $POINTS}" > /dev/null
curl -fsS -X POST "$BASE_URL/v1/runs/$RUN_ID/heartbeat" -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"current_step": 59}' > /dev/null
say "ingested 180 points"

say "waiting for a forecast (<= 30s)"
FORECAST_OK=0
for _ in $(seq 1 30); do
  COUNT=$(curl -fsS "$BASE_URL/v1/runs/$RUN_ID/forecasts" -H "$AUTH" | python3 -c \
    'import json,sys; print(len(json.load(sys.stdin)["items"]))')
  if [ "$COUNT" -ge 1 ]; then FORECAST_OK=1; break; fi
  sleep 1
done
[ "$FORECAST_OK" = 1 ] || { say "FAIL: no forecast within 30s"; exit 1; }
say "forecast appeared"

say "checking the SSE stream delivers an event"
SSE_FILE=$(mktemp)
(curl -fsS -N --max-time 12 "$BASE_URL/v1/stream" -H "$AUTH" > "$SSE_FILE" 2>/dev/null || true) &
SSE_PID=$!
disown "$SSE_PID" 2>/dev/null || true
sleep 1
curl -fsS -X POST "$BASE_URL/v1/runs/$RUN_ID/heartbeat" -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"current_step": 60}' > /dev/null
SSE_OK=0
for _ in $(seq 1 12); do
  if grep -q "event: " "$SSE_FILE" 2>/dev/null; then SSE_OK=1; break; fi
  sleep 1
done
kill "$SSE_PID" 2>/dev/null || true
[ "$SSE_OK" = 1 ] || { say "FAIL: no SSE event observed"; exit 1; }
say "SSE event observed"

DRY=$(curl -fsS -X POST "$BASE_URL/v1/policies/dry-run" -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "definition": {
    "name": "smoke-candidate",
    "when": {"signal": "p_diverge", "op": ">=", "value": 0.8, "after_progress": 0.1, "sustained_evals": 2},
    "action": {"type": "kill", "grace_seconds": 60}
  }
}')
echo "$DRY" | grep -q 'would_have_fired' || { say "FAIL: dry-run malformed"; exit 1; }
say "policy dry-run responded"

say "PASS — register, ingest, forecast, SSE, dry-run all healthy"
