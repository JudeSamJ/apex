# Skills Index — Ramp-style B2B Fintech Platform

Drop this `skills/` folder into your project (e.g. `.cursor/skills/` or
wherever Antigravity/Cursor looks for skill/context files). Each `SKILL.md`
is scoped to one subsystem with a trigger description, so the agent should
consult the relevant one before touching that part of the codebase.

## Recommended build/read order

1. **rbac-multi-entity** — foundation every other module depends on. Build
   first.
2. **ledger-core** — isolated financial source of truth. Build early, wall
   it off.
3. **card-issuing-mock** — Cards module, behind a swappable partner
   interface.
4. **approval-workflow-engine** — generalized approvals used by cards,
   bills, reimbursements.
5. **transaction-pipeline** — orchestrates auth → settlement →
   categorization → approval → GL coding → sync as one traceable flow.
6. **bill-pay-ap** — vendor invoices, approvals, payment (card or mock
   bank transfer).
7. **reimbursements-mileage** — out-of-pocket + mileage claims.
8. **accounting-erp-sync** — GL mapping + sync queue to a mock ERP.
9. **insights-anomaly-detection** — rules-based duplicate/price-increase
   detection and the "Total Savings Identified" rollup.

## Cross-cutting rules that apply everywhere
- Nothing outside `ledger-core` writes to ledger tables directly — always
  through `LedgerClient`.
- Nothing outside `card-issuing-mock` / the payment-rail mock calls a
  "real" external financial partner — everything is a swappable mock
  interface at MVP.
- Every domain row resolves to `entity_id` (+ usually `department_id`) per
  `rbac-multi-entity` — no exceptions.
- Async, retryable, idempotent jobs for anything past the initial
  synchronous request path (see `transaction-pipeline`).
