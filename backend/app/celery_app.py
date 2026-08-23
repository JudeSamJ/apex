import os
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

celery = Celery(
    "ramp_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
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
