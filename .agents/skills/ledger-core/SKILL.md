---
name: ledger-core
description: Use this skill whenever building, modifying, or reasoning about the transaction ledger — the module that records card authorizations, holds, settlements, and balance mutations. Trigger on any task touching Transactions, balance updates, authorization/hold/settlement state, or double-entry bookkeeping logic. Do NOT use for reporting/read-only dashboards (see insights-anomaly-detection) or for accounting/ERP sync (see accounting-erp-sync) — this skill is specifically about the source-of-truth ledger itself.
---

# Ledger Core

## Why this is isolated
The ledger is the system's source of financial truth. It has different
consistency, latency, and audit requirements than every other module. Even in
a monolith, it must live in its own package/schema with no other module
writing to its tables directly.

## Core rules
1. **Append-only.** Never UPDATE a ledger row's amount. Corrections are new
   offsetting entries, never edits.
2. **Double-entry.** Every balance-affecting event writes at least two rows
   (debit + credit) that net to zero within a transaction group.
3. **State machine, not free-form status.** Authorization states must follow:
   `PENDING_AUTH → HELD → SETTLED` or `PENDING_AUTH → DECLINED` or
   `HELD → REVERSED`. No skipping states; enforce via a transition table, not
   scattered if/else.
4. **Idempotency keys required** on every mutating call (external partner
   webhook or internal job) — ledger writes must be safe to retry.
5. **Isolation level:** use `SERIALIZABLE` or row-level locking on balance
   mutations. Never read-then-write a balance without a lock.
6. **Every ledger row references** `entity_id`, `department_id`,
   `card_id` (nullable for non-card entries), and a `source_event_id` for
   traceability back to the event that caused it.

## What NOT to do
- Do not let the Bills, Reimbursements, or Reporting modules write to ledger
  tables. They call a `LedgerClient` interface (`post_hold`,
  `post_settlement`, `post_reversal`) — never raw SQL/ORM access from outside
  the ledger package.
- Do not compute "current balance" by summing all history on every read at
  scale — maintain a running balance snapshot updated transactionally, with
  history as the audit trail.

## Suggested schema shape
```
ledger_entries(
  id, entity_id, department_id, card_id, transaction_id,
  entry_type [DEBIT|CREDIT], amount, currency,
  state [PENDING_AUTH|HELD|SETTLED|DECLINED|REVERSED],
  source_event_id, idempotency_key, created_at
)
```
