"""Load backend/.env into the process environment.

Every credential and feature flag in this app is read through os.getenv()
(directly, or via app.secrets.provider.get_secret) — which reads the *process*
environment and nothing else. Without this module, backend/.env is inert: the
file can be fully populated and the app still falls back to every default
(SQLite instead of the configured Postgres, the insecure built-in JWT_SECRET,
every USE_REAL_* integration stubbed out).

Importing this module has the side effect of loading that file, so it must be
imported before anything that reads configuration at import time — notably
app.database, which resolves DATABASE_URL at module scope.

Values already present in the real environment win over the file (load_dotenv's
default), so a deployment that injects config the normal way — container env,
systemd unit, secrets manager — is unaffected by a stray .env on disk.
"""

import os
import sys

from dotenv import load_dotenv

# Anchored to this file rather than the working directory: uvicorn, pytest and
# alembic each get invoked from different places, and find_dotenv()'s cwd walk
# would silently pick up nothing (or the wrong file) depending on which.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(_BACKEND_DIR, ".env")

# Never under pytest. Every test module overrides get_db() to its own SQLite
# engine, but `with TestClient(app)` still fires the real startup event, and
# init_db() runs `alembic upgrade head` against the *module-level* engine —
# whatever DATABASE_URL resolved to at import. Loading .env here would point
# that at the configured production Postgres and migrate it from a test run.
UNDER_PYTEST = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ

loaded = False if UNDER_PYTEST else load_dotenv(ENV_FILE)
