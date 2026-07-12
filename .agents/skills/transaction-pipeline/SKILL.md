---
name: transaction-pipeline
description: Use this skill when wiring the end-to-end flow from card authorization through settlement, categorization, approval routing, GL coding, and ERP sync. Trigger on "transaction pipeline", "authorization to settlement", "async job orchestration", "webhook events" for transactions. This is the integration skill that ties together ledger-core, card-issuing-mock, accounting-erp-sync, and approval-workflow-engine — use it when connecting those modules, not when building any one of them in isolation.
---

# Transaction Pipeline Orchestration

## The sequence to implement
```
1. Authorization request (mock issuing partner) 
   -> LedgerClient.post_hold()                         [sync, request path]
2. Settlement event arrives (mock, async)               
   -> LedgerClient.post_settlement()                    [async job]
3. Categorization                                        
   -> rules-based merchant/category lookup               [async job]
4. Approval routing (only if spend program requires it)  
   -> approval-workflow-engine                           [async, event-driven]
5. GL coding                                              
   -> auto-code via merchant-category -> GL mapping       [async job]
6. Push to sync_queue (sync_status = SYNC_READY)          
   -> accounting-erp-sync                                 [async job]
```

## Event emission points
Emit an internal event (usable for webhooks/notifications later) at each
step: `hold_created`, `settled`, `categorized`, `approval_required`,
`approved`/`rejected`, `gl_coded`, `sync_ready`, `synced`.

## Reliability rules
- Steps 2–6 run as async jobs off a queue, each idempotent and retryable.
  Never do settlement → sync as one long synchronous call chain.
- Each job should be resumable from its own state: if categorization fails,
  a retry should not re-run settlement.
- Use a job's `source_event_id` (see ledger-core) to trace a transaction's
  full pipeline history for debugging/support.

## What to build vs. stub
- Steps 1–2 talk to the mock `IssuingPartnerClient`/`LedgerClient` — real
  logic, mock external dependency.
- Steps 3, 5 (categorization, GL coding) are real rules-based logic — see
  insights-anomaly-detection and accounting-erp-sync skills.
- Step 4 only fires conditionally based on spend-program policy — most
  transactions should NOT require approval at MVP; reserve it for
  above-threshold or flagged-category spend.
- Step 6 hands off to the accounting-erp-sync skill's queue design.
