import os
import logging
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIDLogFilter(logging.Filter):
    """Injects the current request's correlation ID into every log record,
    so log lines from different concurrent requests can be told apart."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


def configure_logging():
    """Structured logging: every line carries a timestamp, level, logger
    name, and the request correlation ID (or '-' outside a request)."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
    ))
    handler.addFilter(_RequestIDLogFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def init_sentry():
    """Initialize Sentry error tracking if SENTRY_DSN is configured. A no-op
    otherwise, and a clear warning (not a crash) if sentry-sdk isn't
    installed — this is an optional, pluggable dependency like the other
    provider integrations in this codebase."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "sandbox"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            integrations=[FastApiIntegration()],
        )
        logger.info("Sentry error tracking initialized")
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk isn't installed; run `pip install sentry-sdk` to enable it")
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns each request a correlation ID (reusing an inbound X-Request-ID
    if the caller/load balancer supplied one), binds it for every log line
    emitted while handling the request, and echoes it back in the response
    so a client can correlate their request with our logs/support tickets."""

    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response
