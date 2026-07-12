---
name: accounting-erp-sync
description: Use this skill when building GL account mapping, custom fields, or the sync queue that pushes transactions/bills/reimbursements to an external accounting system (QuickBooks/NetSuite/Xero-style). Trigger on "GL coding", "accounting sync", "sync_status", "ERP integration", "custom fields", "chart of accounts". Real ERP connectors are out of scope at MVP — build the sync-ready queue and a mock ERP connector only.
---

# Accounting / ERP Sync

## Model: pull/push queue, not direct push
Do not call a real ERP API synchronously when a transaction settles. Instead:

1. When a transaction/bill/reimbursement is GL-coded and ready, write/update
   a `sync_queue` row with `sync_status = SYNC_READY`.
2. A (mock) ERP connector polls `sync_status = SYNC_READY` items, "pushes"
   them (simulated), and calls back to mark `SYNCED` or `ERROR` with a
   reason.
3. Errors stay visible in an admin UI for manual re-sync — never silently
   drop failed syncs.

## Data model
```
gl_accounts(id, entity_id, code, name, type)
accounting_custom_fields(id, entity_id, name, field_type, options[])
sync_queue(
  id, syncable_type [TRANSACTION|BILL|REIMBURSEMENT], syncable_id,
  entity_id, gl_account_id, custom_field_values (jsonb),
  sync_status [NOT_READY|SYNC_READY|SYNCING|SYNCED|ERROR],
  error_message, synced_at
)
```

## GL coding logic
- A transaction/bill/reimbursement is only eligible for `SYNC_READY` after
  it has both a `gl_account_id` and passed approval (where applicable).
- Support rules-based auto-coding: map merchant category → default GL
  account per entity, with manual override always possible. This is
  real, buildable logic — implement it, don't stub it.
- Leave a clearly commented extension point for future embeddings-based
  auto-coding (see insights-anomaly-detection skill for the same pattern)
  — do not build the ML version now.

## Mock ERP connector
Build `MockERPConnector` that simulates realistic latency, occasional
`ERROR` responses (for retry-path testing), and idempotent processing (same
`sync_queue` row pushed twice should not duplicate on the "ERP" side).
