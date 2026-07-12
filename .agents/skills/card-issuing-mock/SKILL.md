---
name: card-issuing-mock
description: Use this skill when building the Cards module — virtual/physical card creation, limits, freezing, or anything that would in production call a real issuing bank (Celtic Bank/Stripe Issuing/Marqeta-style). Trigger on "card issuance", "virtual card", "physical card", "card limits", "freeze card", "Request Card flow". This skill defines the mock IssuingPartnerClient boundary — real issuing/BaaS integration is explicitly out of scope; do not build real bank connectivity.
---

# Card Issuing (Mock Partner Boundary)

## The boundary
Real card issuing requires a chartered/partner bank (BaaS/program-manager
model). Build a swappable interface so a real partner can be dropped in later
without touching the rest of the app.

```
IssuingPartnerClient
  create_card(entity_id, owner_id, type[VIRTUAL|PHYSICAL], limit) -> Card
  update_limit(card_id, new_limit) -> Card
  freeze_card(card_id) -> Card
  unfreeze_card(card_id) -> Card
  get_card_token(card_id) -> masked_pan_token   # never a real PAN
```

Implement `MockIssuingPartnerClient` that generates fake masked tokens
(`**** **** **** 4242`-style), simulated latency, and realistic
success/decline responses — never a real PAN, real card number, or real BIN.

## Card domain rules
- A card always belongs to exactly one `entity_id` and one `owner_id` (user),
  and is attributed to a `department_id` for reporting.
- Limits are enforced by a **Spend Program** (policy), not hardcoded on the
  card — the card references a `spend_program_id`; the program defines
  monthly/yearly/one-time limit type, allowed merchant categories, and
  approval requirements above a threshold.
- `RequestCard` self-serve flow creates a card request object in
  `PENDING_APPROVAL` state that routes through the approval-workflow-engine
  skill, not directly to card creation.
- Freezing a card must be synchronous and immediate from the user's
  perspective (optimistic UI + confirmed mock-partner call), since this is a
  fraud/security-critical action.

## PCI-DSS posture
Never store or log a full card number anywhere in this codebase, including
the mock. Only store the masked token returned by `IssuingPartnerClient`.
This keeps the app out of full PCI scope even in mock form, and keeps the
right habits in place for a real integration later.
