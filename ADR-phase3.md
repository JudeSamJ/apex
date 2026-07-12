# Architecture Decision Record — Phase 3 (Accounting Sync & Spend Insights)

## 1. Auto-Categorization & Sync Queue Chokepoint
* **Decision**: Auto-coded items (settled card transactions, paid AP bills, and reimbursed claims) are routed through a unified `SyncQueue` pipeline using custom mappings.
* **Rationale**: Decouples posting rules and ERP sync operations. Rather than writing distinct syncing hooks for all three modules, we feed them into a single idempotency gate mapped to a generic `MockERPConnector`.

## 2. Rules-Based Insights Batch Engine
* **Decision**: Designed the anomaly detection engine to query records periodically/upon request rather than executing inline during card authorization or settlements.
* **Rationale**: Maintains optimal transaction processing latency (which is critical for card authorization hold paths) while enabling comparative rolling window audits (duplicate monthly SaaS, price-increase detections).

## 3. Dynamic Budgeting and Admin KPIs Rollups
* **Decision**: Implemented read-only reporting aggregations over settled ledger history and metadata states.
* **Rationale**: Ensures the system does not add unnecessary write operations to the ledger core. Compliance and efficiency rollups represent live, dynamic metrics calculated straight from the double-entry source of truth.
