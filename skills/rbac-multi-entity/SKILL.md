---
name: rbac-multi-entity
description: Use this skill first, before building any other module — it defines Entities, Departments, Locations, Users, and role-based access control that every other module (cards, bills, reimbursements, reporting) depends on for scoping and authorization. Trigger on "multi-entity", "RBAC", "roles", "permissions", "department", "entity scoping", or at the very start of the project when scaffolding the data model.
---

# RBAC & Multi-Entity Foundation

## Build this first
Every other module's rows must resolve to an `entity_id` (and usually a
`department_id`). Get this schema right before writing any business logic
elsewhere — retrofitting entity scoping later is expensive.

## Data model
```
entities(id, name, onboarding_status [PENDING|APPROVED|SUSPENDED], parent_entity_id NULL)
departments(id, entity_id, name)
locations(id, entity_id, name, address)
users(id, entity_id, email, name)
roles(id, name)  -- e.g. ADMIN, MANAGER, EMPLOYEE, AP_APPROVER, BOOKKEEPER
user_roles(user_id, role_id, entity_id, department_id NULL)
```

## Rules
- Support multi-entity via `entities.parent_entity_id` for a parent/child
  business structure (holding company with subsidiaries) — a user can have
  different roles per entity.
- Every domain query (cards, transactions, bills, reimbursements) must
  filter by the requesting user's accessible `entity_id`/`department_id`
  set — build this as a shared authorization middleware/decorator, not
  copy-pasted filters per endpoint.
- `entities.onboarding_status` gates activation: card issuance and bill pay
  should be blocked unless `APPROVED` (this stands in for KYB/KYC, which is
  out of scope to build for real — see product prompt).
- Roles are permission bundles, not per-action toggles at MVP: keep a fixed
  set (Admin, Manager, Employee, AP Approver, Bookkeeper) rather than a
  fine-grained permission-editor UI, which is a post-MVP feature.

## What NOT to do
- Do not scope by `user_id` alone anywhere — always resolve through
  entity/department, since a user can belong to multiple.
- Do not build a custom permission-editor UI at MVP; fixed roles are enough.
