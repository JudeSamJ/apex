# Before REDIS_URL is read below, and for the standalone worker entry point
# (`celery -A app.celery_app worker`), which never imports app.main.
import app.dotenv_bootstrap  # noqa: F401  (imported for its side effect)

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from celery import Celery

# Check if Redis URL is configured and active
REDIS_URL = os.getenv("REDIS_URL", "")

# Default to eager execution for local testing if Redis is not specified or unavailable.
# Accept rediss:// (TLS) as well as redis:// — managed brokers like Upstash only
# issue rediss:// URLs, and excluding that scheme meant Celery silently ran in
# eager mode even with a real broker configured in REDIS_URL.
always_eager = True
if REDIS_URL.startswith(("redis://", "rediss://")):
    always_eager = False
else:
    # Use dummy value for initialization but run in eager mode
    REDIS_URL = "redis://localhost:6379/0"

def _with_ssl_cert_reqs(url: str) -> str:
    """kombu refuses a rediss:// broker URL that carries no ssl_cert_reqs
    parameter — it raises ValueError at publish time ("A rediss:// URL must
    have parameter ssl_cert_reqs..."), which surfaces as a 500 from whichever
    request queued the task. Managed brokers hand out bare rediss:// URLs
    (Upstash does), so supply the parameter here rather than requiring every
    deployment to remember to append it to REDIS_URL.

    CERT_REQUIRED is the safe default: it verifies the broker's certificate,
    which managed providers present validly.
    """
    parts = urlsplit(url)
    if parts.scheme != "rediss":
        return url

    query = dict(parse_qsl(parts.query))
    if "ssl_cert_reqs" in query:
        return url

    query["ssl_cert_reqs"] = "CERT_REQUIRED"
    return urlunsplit(parts._replace(query=urlencode(query)))


BROKER_URL = _with_ssl_cert_reqs(REDIS_URL)

celery = Celery(
    "ramp_tasks",
    broker=BROKER_URL,
    backend=BROKER_URL,
    include=["app.transactions.tasks"]
)

celery.conf.update(
    task_always_eager=always_eager,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
