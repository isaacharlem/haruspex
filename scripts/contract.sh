#!/usr/bin/env bash
# Contract suite: schemathesis against the running app's OpenAPI schema,
# auth-aware, on an ephemeral database. Mirrors the CI `contract` job.
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_DB_URL="${HARUSPEX_DATABASE_URL:-postgresql+asyncpg://haruspex:haruspex@localhost:55432/haruspex}"
PORT="${CONTRACT_PORT:-18900}"
SCRATCH_DB="haruspex_contract_$$"
ADMIN_DSN="${BASE_DB_URL/postgresql+asyncpg/postgresql}"

# Imports via PYTHONPATH: immune to the macOS uv/UF_HIDDEN .pth issue
# (see DECISIONS.md); harmless elsewhere.
export PYTHONPATH="$PWD/backend/src:$PWD/sdk/src${PYTHONPATH:+:$PYTHONPATH}"

say() { echo "contract: $*"; }

scratch_url() {
  python3 - "$BASE_DB_URL" "$SCRATCH_DB" <<'EOF'
import sys
from urllib.parse import urlsplit, urlunsplit
parts = urlsplit(sys.argv[1])
print(urlunsplit(parts._replace(path=f"/{sys.argv[2]}")))
EOF
}

SCRATCH_URL=$(scratch_url)

cleanup() {
  if [ -n "${API_PID:-}" ]; then kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; fi
  pkill -f "uvicorn.*--port $PORT" 2>/dev/null || true
  uv run python - "$ADMIN_DSN" "$SCRATCH_DB" <<'EOF' || true
import asyncio, sys
import asyncpg
async def drop():
    conn = await asyncpg.connect(sys.argv[1])
    await conn.execute(f'DROP DATABASE IF EXISTS "{sys.argv[2]}" WITH (FORCE)')
    await conn.close()
asyncio.run(drop())
EOF
}
trap cleanup EXIT

say "creating scratch database $SCRATCH_DB"
uv run python - "$ADMIN_DSN" "$SCRATCH_DB" <<'EOF'
import asyncio, sys
import asyncpg
async def create():
    conn = await asyncpg.connect(sys.argv[1])
    await conn.execute(f'CREATE DATABASE "{sys.argv[2]}"')
    await conn.close()
asyncio.run(create())
EOF

export HARUSPEX_DATABASE_URL="$SCRATCH_URL"
unset ANTHROPIC_API_KEY || true
(cd backend && uv run alembic upgrade head > /dev/null)

say "booting api on :$PORT (log: /tmp/haruspex-contract-api.log)"
(cd backend && uv run uvicorn --factory haruspex_server.api.app:create_app \
  --host 127.0.0.1 --port "$PORT" --log-level warning) \
  > /tmp/haruspex-contract-api.log 2>&1 &
API_PID=$!
for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:$PORT/healthz" > /dev/null 2>&1 && break
  sleep 0.5
done

KEY=$(cd backend && uv run python -m haruspex_server.cli mint-key \
      --name contract --scopes ingest,read,admin | grep HARUSPEX_API_KEY | cut -d= -f2)
say "key minted (${KEY:0:8}...)"

# /v1/stream is an infinite SSE response and is exercised by the smoke and e2e
# suites instead; everything else is fuzzed.
uv run schemathesis run "http://127.0.0.1:$PORT/openapi.json" \
  --header "Authorization: Bearer $KEY" \
  --exclude-path /v1/stream \
  --checks not_a_server_error,response_schema_conformance \
  --exclude-checks ignored_auth \
  --max-examples 15 \
  --generation-deterministic \
  --max-failures 5

say "PASS"
