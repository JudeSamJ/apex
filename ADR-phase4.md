# Architecture Decision Record — Phase 4 (Hardening, Audits & Webhook Rails)

## 1. Explicit Entity-Scoping of Child Rows
* **Decision**: Added `entity_id` foreign keys and column definitions directly to line-item and auxiliary child tables (e.g. `BillLineItem`, `TripWaypoint`, `ApprovalStep`) rather than relying on parent relational mapping.
* **Rationale**: Enforces a strict, defense-in-depth isolation guarantee. This ensures that any direct SQL bulk query, report rollup, or row-level permission filter can select solely by `entity_id` without joining parent tables, preventing accidental cross-tenant data leaks.

## 2. In-Memory Sliding Window Rate Limiting
* **Decision**: Implemented rate limiting using a local in-memory sliding window queue mapping user requests.
* **Rationale**: Simple, zero-dependency, and lightweight enough for MVP production scaling. It shields mutate paths from rapid duplicate click submissions without introducing Redis caching overhead.

## 3. General Ledger Write Isolation
* **Decision**: Walled off the general ledger using static checking scripts.
* **Rationale**: Enforces strict domain driven design (DDD) boundaries. Isolating direct writes to `ledger` tables ensures that financial debit/credit rules cannot be bypassed by other application services.
