# Architecture Decision Record — Phase 1 (B2B Fintech Platform)

## 1. Multi-Entity and Schema Portability
* **Decision**: Table definitions were decoupled from hardcoded `public` schemas. The core tables are created in the default schema, while the isolated ledger tables are created in the `ledger` schema.
* **Rationale**: This allows SQLite (which does not support Postgres schemas natively) to run in local testing and host development environments by using an event-listener to dynamically run `ATTACH DATABASE './[name]_ledger.db' AS ledger;` on every SQLite connection.

## 2. Local Task Queue Fallback
* **Decision**: Celery has been configured to fall back to `task_always_eager = True` if the `REDIS_URL` broker environment variable is not defined or inactive.
* **Rationale**: This guarantees that the background transaction pipeline (settlements and MCC auto-categorizations) executes synchronously on the spot when running tests or running locally without Redis, while running asynchronously when deployed via Docker Compose.

## 3. Cryptographic Hashing Scheme
* **Decision**: Replaced `bcrypt` with `sha256_crypt` in `passlib` for password hashing and validation.
* **Rationale**: Bypasses host machine compilation and runtime errors on setuptools/passlib where the modern `bcrypt` module is incompatible with deprecated `passlib` methods.

## 4. Custom SVG Charting in Frontend
* **Decision**: Implemented charts using pure React-SVG elements rather than pulling in external libraries like `Recharts`.
* **Rationale**: Avoids module resolution, peer dependency mismatches, and build failures with React 19 and TypeScript 6.0, while maintaining full control over animations and visual styling.
