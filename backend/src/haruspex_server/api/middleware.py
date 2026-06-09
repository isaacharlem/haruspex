"""ASGI middleware: request IDs and one structured log line per request."""

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from haruspex_server.api.context import set_request_id

logger = structlog.get_logger("haruspex.request")

REQUEST_ID_HEADER = b"x-request-id"


class RequestContextMiddleware:
    """Assigns a request ID, echoes it as ``X-Request-ID``, and logs the request."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or [])
        request_id = incoming.get(REQUEST_ID_HEADER, b"").decode("latin-1") or uuid.uuid4().hex
        set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers") or [])
                if not any(name.lower() == REQUEST_ID_HEADER for name, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            path = scope.get("path", "")
            if path not in ("/healthz", "/readyz"):
                logger.info(
                    "request",
                    method=scope.get("method", ""),
                    path=path,
                    status=status_holder["status"],
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            structlog.contextvars.unbind_contextvars("request_id")
