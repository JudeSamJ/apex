---
name: bill-pay-ap
description: Use this skill when building vendor invoices, bill line items, bill approval routing, or bill payment (by card or bank transfer). Trigger on "bill pay", "accounts payable", "AP", "vendor invoice", "pay by card", "pay by bank transfer". Depends on approval-workflow-engine, rbac-multi-entity, ledger-core (for card payments), and card-issuing-mock/payment-rail mocks.
---

# Bill Pay / Accounts Payable

## Data model
```
vendors(id, entity_id, name, default_gl_account_id)
vendor_contacts(id, vendor_id, name, email)
vendor_bank_accounts(id, vendor_id, masked_account_ref)  -- mock rail token only
bills(
  id, entity_id, vendor_id, status [DRAFT|PENDING_APPROVAL|APPROVED|PAID|VOID],
  due_date, total_amount, payment_method [CARD|BANK_TRANSFER],
  approval_id, created_at
)
bill_line_items(id, bill_id, description, amount, gl_account_id, custom_field_values jsonb)
bill_payments(id, bill_id, transaction_id NULL, transfer_ref NULL, paid_at)
```

## Payment methods — two distinct paths
- **Pay by card:** call `LedgerClient.post_settlement` to create a linked
  `Transaction`, then set `bills.payment_method = CARD` and
  `bill_payments.transaction_id` to that transaction's id. The bill and its
  linked transaction must be mutually discoverable
  (`bill.details.transaction_ids`-style reference).
- **Pay by bank transfer:** call a mock `PaymentRailClient.initiate_transfer`
  (never a real ACH/wire integration) and record `bill_payments.transfer_ref`.

## Workflow
`DRAFT → PENDING_APPROVAL` (submits into approval-workflow-engine) →
`APPROVED` → payment initiated → `PAID`. A rejected approval returns the
bill to `DRAFT` with the rejection comment visible.

## Rules
- Bills require at least one line item with a `gl_account_id` before they
  can leave `DRAFT`.
- Vendor matching: when creating a bill, fuzzy-match the vendor name against
  existing `vendors` for the entity before creating a duplicate record
  (simple string similarity is fine at MVP — no ML needed here).
- Once `PAID`, a bill is immutable except for VOID (with reason), which must
  also reverse any linked ledger entry via `LedgerClient.post_reversal`.
