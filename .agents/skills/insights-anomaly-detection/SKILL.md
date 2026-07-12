---
name: insights-anomaly-detection
description: Use this skill when building spend insights — duplicate subscription detection, price-increase alerts, savings suggestions, or the "Total Savings Identified" metric. Trigger on "insights", "anomaly detection", "duplicate subscription", "price increase alert", "savings identified". Build real rules-based logic at MVP scale — do not stub this module, and do not build ML/embeddings versions yet.
---

# Insights & Anomaly Detection (Rules-Based MVP)

## Principle
This is genuinely buildable without ML at MVP scale. Implement real logic;
leave clearly commented extension points for a future embeddings/RAG
approach, but don't build that now.

## Detection rules to implement

**Duplicate subscription detection**
- Group settled transactions by `(entity_id, normalized_merchant_name)`.
- Flag as a potential duplicate when 2+ active recurring charges to the same
  normalized merchant exist within a rolling 35-day window at similar
  amounts (within ~10%), especially across different cards/departments.
- Store a `merchant_normalization` lookup table (raw descriptor →
  canonical merchant name) — this table is itself valuable IP; keep it
  editable/extendable.

**Price-increase alerts**
- For a merchant with a recurring charge history (3+ prior charges at a
  stable amount), flag when a new charge amount increases beyond a
  threshold (e.g. >8%) from the trailing average.

**Total Savings Identified**
- Sum of dollar amounts tied to *actioned* insights (e.g. a duplicate
  subscription the user confirmed and cancelled), not just flagged-but-open
  insights. Compute as a real rollup query, not a static/mocked number.

## Data model
```
insights(
  id, entity_id, type [DUPLICATE_SUBSCRIPTION|PRICE_INCREASE],
  related_transaction_ids[], estimated_savings_amount,
  status [OPEN|CONFIRMED|DISMISSED], detected_at
)
```

## Job design
Run detection as an async scheduled job (daily, or triggered after new
settlements batch in) — not synchronously on every transaction settle. Write
results into `insights`; the reporting dashboard reads from this table.

## Explicit non-goals at MVP
- No embeddings-based merchant matching.
- No ML anomaly-scoring model.
- No cross-customer benchmarking ("better pricing suggestions" vs. market)
  — that requires aggregate data across many customers you won't have yet;
  flag it as a documented future capability, don't fake it with hardcoded
  numbers.
