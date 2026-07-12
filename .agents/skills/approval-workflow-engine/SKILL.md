---
name: approval-workflow-engine
description: Use this skill whenever building or extending approval logic — for card requests, bills, reimbursements, or spend-program changes. Trigger on "approval", "approve/reject", "approval routing", "multi-step approval", "policy engine". This is core defensible IP for the product; build it as one generalized engine, not per-module bespoke logic. All of RBAC, bill-pay, and reimbursements depend on this skill's object model.
---

# Approval Workflow Engine

## Principle
Build ONE generalized `Approval` object and state machine that every module
(cards, bills, reimbursements) references, rather than separate approval
logic per module. This is one of the product's actual defensible IP
surfaces — treat it as a first-class subsystem, not a helper.

## State machine
```
DRAFT -> SUBMITTED -> IN_REVIEW -> APPROVED -> (module-specific terminal state)
                            \-> REJECTED
                            \-> ESCALATED -> IN_REVIEW (next approver)
```

## Data model
```
approvals(
  id, approvable_type [CARD_REQUEST|BILL|REIMBURSEMENT],
  approvable_id, entity_id, department_id,
  current_step, total_steps, state, created_at
)
approval_steps(
  id, approval_id, step_number, approver_id | approver_role,
  decision [PENDING|APPROVED|REJECTED], decided_at, comment
)
approval_rules(
  id, entity_id, applies_to [CARD_REQUEST|BILL|REIMBURSEMENT],
  condition (e.g. amount > threshold, department = X),
  required_steps (ordered list of roles or specific approvers)
)
```

## Routing logic
1. On submission, evaluate `approval_rules` for the entity + module + amount
   to build the ordered `approval_steps`.
2. Notify the current step's approver (in-app + event emission for
   notifications module).
3. Each decision advances `current_step` or terminates the approval.
4. On final `APPROVED`, emit an event the owning module (cards/bills/
   reimbursements) subscribes to, to move its own object out of
   `PENDING_APPROVAL`.

## What NOT to do
- Do not hardcode "manager approves reimbursements under $500" logic inside
  the Reimbursements module. That's a rule row in `approval_rules`.
- Do not let modules mutate `approvals` rows directly — they only read
  state and react to emitted events.
- Do not build a visual workflow builder UI at MVP — a rules table +ordered
  role list is sufficient; a drag-and-drop rule editor is a post-MVP feature.
