---
name: reimbursements-mileage
description: Use this skill when building out-of-pocket expense reimbursements or mileage-based reimbursements with trip/waypoint tracking. Trigger on "reimbursement", "out-of-pocket", "mileage", "trip tracking", "waypoints". Depends on approval-workflow-engine, rbac-multi-entity, and accounting-erp-sync for GL coding/sync.
---

# Reimbursements (Out-of-Pocket + Mileage)

## Data model
```
reimbursements(
  id, entity_id, user_id, type [OUT_OF_POCKET|MILEAGE],
  status [SUBMITTED|APPROVED|REJECTED|REIMBURSED],
  total_amount, approval_id, submitted_at, reimbursed_at
)
reimbursement_line_items(
  id, reimbursement_id, description, amount, gl_account_id,
  custom_field_values jsonb, receipt_url NULL
)
mileage_trips(
  id, reimbursement_id, purpose, mileage_rate, total_miles, computed_amount
)
trip_waypoints(id, trip_id, sequence, address, lat, lng)
```

## Mileage calculation
- `computed_amount = total_miles * mileage_rate`, where `mileage_rate` is
  configurable per entity (default to a standard published rate, e.g. IRS
  standard mileage rate as a sane default — but make it entity-editable, not
  hardcoded).
- `total_miles` should be derivable from waypoint sequence if you integrate
  a distance calculation (straight-line or routing-API-based); at MVP a
  manual mileage entry with waypoints stored for audit/context is
  acceptable — do not build a real routing/maps integration unless
  explicitly asked.

## Workflow
`SUBMITTED` → routes into approval-workflow-engine → `APPROVED` or
`REJECTED` → on approval, becomes eligible for payout (mock bank transfer
via the same `PaymentRailClient` used in bill-pay-ap) → `REIMBURSED`.

## Sync
Once `REIMBURSED`, push a `sync_queue` row exactly as described in
accounting-erp-sync — reimbursements are GL-coded per line item just like
bills.

## Rules
- Out-of-pocket line items should support receipt attachment
  (`receipt_url`); receipt-to-line-item matching logic can reuse whatever
  OCR/matching approach is used in the expense-management transaction feed
  — keep this consistent rather than building a second parallel matcher.
- A reimbursement with zero line items/trips cannot be submitted.
