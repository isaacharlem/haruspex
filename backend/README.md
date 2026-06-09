# haruspex-server

The Haruspex API service and forecast/policy worker. One package, two entrypoints:

- `haruspex_server.api.app:create_app` — FastAPI application (ingest, CRUD, auth, SSE, copilot).
- `haruspex_server.worker` — asyncio loop that refits forecasts and evaluates kill policies.

See the repository root [README](../README.md) for the full picture.
