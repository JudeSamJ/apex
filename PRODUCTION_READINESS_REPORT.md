# Production Readiness Report

**Generated:** July 13, 2026  
**Status:** Sandbox/Demo Mode - Not Production Ready

## Overview

This report tracks the integration status of all external providers. The application currently runs in **sandbox/demo mode** using real provider sandbox environments. This provides realistic API round-trips and data for client demos but is **not suitable for production use** without completing the business/legal steps outlined in `GOING_LIVE.md`.

### Recent hardening (this pass)

Pure-code gaps that don't require a vendor account were closed:

- **Webhook signature verification** for Dwolla (`X-Request-Signature-SHA256`) and Didit (`X-Didit-Signature`), matching the pattern already used for Stripe. Verification is skipped with a loud warning log when the corresponding secret env var isn't set (sandbox default) — set `DWOLLA_WEBHOOK_SECRET`/`DIDIT_WEBHOOK_SECRET` before going live.
- **Idempotency-Key support** on `POST /api/bills/{id}/pay` and `POST /api/reimbursements/{id}/payout` — a client-supplied `Idempotency-Key` header now guards against double-submitting a payment on retry/double-click; a concurrent duplicate gets `409`, a replayed one gets the original response back instead of a second transfer.
- **Fixed a bug where card issuance always used the mock issuer** regardless of `USE_REAL_ISSUING` — `approvals/engine.py` was hardcoded to `MockIssuingPartnerClient` instead of going through the `get_issuing_client()` factory, so Stripe Issuing was silently never called even when configured.
- **QBO OAuth token refresh** — `refresh_access_token()` on `QuickBooksOnlineClient`, wired through `get_valid_qbo_connection()` so any QBO-calling endpoint transparently refreshes a token within 5 minutes of expiry instead of failing.
- **Real ERP sync queue** — `POST /api/accounting/sync/process` now pushes queued items to QBO as journal entries when the entity has a live `ERPConnection`, with exponential-backoff retry (up to 5 attempts) on failure; falls back to the existing simulated round-trip when no real connection is configured, so demos/tests are unaffected.

### Compliance scaffolding (this pass)

Two new modules, built as pluggable mock/real clients following the same pattern as Stripe/Dwolla/Plaid — functional end-to-end today in mock mode, and code-complete for production once a real vendor account and key are supplied:

- **AML/OFAC sanctions screening** (`app/screening/`) — every new entity (on `/api/auth/register`) and every new vendor (on `POST /api/bills/vendors`) is screened against a watchlist provider. `MockSanctionsScreeningClient` is deterministic (flags names containing an obvious test marker like "OFAC TEST") so demos and tests are reliable without a real watchlist; `ComplyAdvantageClient` calls the real ComplyAdvantage Search API when `USE_REAL_SCREENING=true` and `COMPLYADVANTAGE_API_KEY` is set. A screening `HIT` blocks entity auto-approval (both the `AUTO_APPROVE_ONBOARDING` path and the Didit-webhook approval path) and blocks `POST /api/bills/{id}/pay` for the flagged vendor (`403`) until an admin manually re-screens via `POST /api/screening/rescreen/vendor/{vendor_id}`. Every screen is recorded in `sanctions_screenings` as an audit trail, readable via `GET /api/screening`.
  - **Still needed for production:** a real ComplyAdvantage (or equivalent) account, `COMPLYADVANTAGE_API_KEY`, ongoing/periodic re-screening (not just at creation time — sanctions lists change), and a documented manual-review workflow for hits.
- **Dispute & chargeback handling** (`app/disputes/`) — `webhooks/router.py` now handles Stripe's `issuing_dispute.created`, `issuing_dispute.updated`, `issuing_dispute.funds_reinstated`, and `issuing_dispute.funds_rescinded` events, mirroring dispute state into a local `card_disputes` table (resolving the card via one Stripe API call to expand the issuing transaction, since the webhook payload only carries the transaction ID). `GET /api/disputes` lists them; `POST /api/disputes/{id}/evidence` lets an admin attach evidence and move a dispute to `UNDER_REVIEW`, submitting it to Stripe for real when `USE_REAL_ISSUING=true`.
  - **Still needed for production:** a cardholder-facing dispute-initiation flow (today disputes only arrive via Stripe webhook, there's no "report this transaction" button), evidence file/receipt upload, and SLA tracking against Stripe's response deadlines.

### Platform hardening (this pass)

- **Fixed a real bug in `celery_app.py`**: the Redis-broker check only matched `redis://`, so a TLS broker URL (`rediss://` — what every managed Redis provider, e.g. Upstash, actually issues, including the one already in `backend/.env`) was silently rejected and Celery fell back to synchronous eager execution even though a real broker was configured. Background jobs (settlement, categorization, GL coding, sync-queue push) have effectively never run asynchronously. Now accepts both schemes.
- **Rate limiting is now Redis-backed with automatic fallback** (`app/rate_limit.py`) — when `REDIS_URL` is configured and reachable, `check_rate_limit` uses a Redis sorted-set sliding window shared across every API process (the old in-memory version under-counted the instant you ran more than one instance); falls back to the original per-process in-memory window with zero config change when Redis isn't available, so local dev/tests are unaffected.
- **Payment-rail reconciliation** (`app/reconciliation/`) — `POST /api/reconciliation/run` (admin-only) compares every bank-transfer bill payment and reimbursement payout against the payment rail's current view of that transfer (`get_transfer_status`, now implemented on the mock client too), flagging drift (e.g. we think a bill is `PAID` but the rail says the transfer failed or was cancelled) as a `ReconciliationDiscrepancy`. `GET /api/reconciliation/runs` and `.../{id}/discrepancies` expose the history.
  - **Still needed for production:** a scheduled/periodic run (today it's on-demand only), Stripe Issuing-side reconciliation (no transaction-listing capability exists yet in `StripeIssuingClient`), and alerting on discrepancies rather than requiring someone to check the endpoint.
- **Structured logging + request correlation IDs + optional Sentry hook** (`app/observability.py`) — every log line now carries a request correlation ID (`X-Request-ID`, generated or passed through, echoed back in the response) so concurrent requests' logs can be told apart; `SENTRY_DSN` optionally turns on Sentry error tracking (no-op, not a crash, if unset or `sentry-sdk` isn't installed).
  - **Still needed for production:** a real log aggregator (this only formats to stdout — ship it to Datadog/CloudWatch/etc.), and installing `sentry-sdk` + setting `SENTRY_DSN`/`SENTRY_ENVIRONMENT` for an actual account.

New env vars: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `LOG_LEVEL` (all optional, all default to off/INFO).

### Product features (this pass)

- **TOTP multi-factor authentication** (`entities_rbac/router.py`, `pyotp`) — `POST /api/auth/mfa/enroll` issues a secret + `otpauth://` URL (for any authenticator app), `POST /api/auth/mfa/confirm` activates it once the user proves possession. Once enabled, `POST /api/auth/token` no longer returns an access token directly — it returns a short-lived, single-purpose `mfa_challenge_token` that a normal request can't use as a bearer token (enforced in `get_current_user_context`), which must be exchanged via `POST /api/auth/mfa/verify-login` (rate-limited to 5 attempts/5 minutes per user) for a real one. `POST /api/auth/mfa/disable` requires a valid code, so a stolen session token alone can't turn off the second factor.
  - **Still needed for production:** enforcing MFA for privileged roles (currently opt-in per user), backup/recovery codes for a lost authenticator, and SSO/SAML for enterprise customers (a separate, larger integration).
- **In-app notifications + pluggable email** (`app/notifications/`) — `Notification` rows plus a mock/real (`SMTPEmailClient`, any SendGrid/Postmark/SES/relay via `USE_REAL_EMAIL`) client. Wired into: a new approval step's first-round approvers, a vendor sanctions-screening hit, a QBO sync item exhausting its retries, and a new card dispute — all notify the relevant `ADMIN`/approver users, with email on the higher-severity ones. `GET /api/notifications`, `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all`.
  - **Still needed for production:** a real SMTP/ESP account (`SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL`), SMS for time-sensitive alerts, and a push/websocket channel so the frontend doesn't have to poll.
- **CSV statement export** — `GET /api/transactions/export.csv`, same visibility rules as the existing transaction list (non-admin/bookkeeper users only see their own card).
  - **Still needed for production:** PDF statements, and export for bills/reimbursements/ledger history (today only card transactions are covered).
- **1099-NEC vendor tax reporting** (`app/tax_reporting/`) — `GET /api/tax-reporting/1099-nec/{year}` aggregates bank-transfer bill payments per vendor for a calendar year and flags every vendor at or above the IRS $600 nonemployee-compensation threshold; `.../export.csv` produces a ready-to-file-shaped CSV (Vendor Name, TIN, Address, Box 1 amount). Added `tax_id`/`tax_address` to `Vendor` plus `PATCH /api/bills/vendors/{id}/tax-info` so a W-9's data can actually be recorded — the export shows `TIN_REQUIRED`/`ADDRESS_REQUIRED` placeholders until it is.
  - **Still needed for production:** a real e-file/mail service (Track1099, Tax1099, or filing directly with the IRS FIRE system) — this report gives you the numbers, it doesn't file them; W-9 collection UX; and 1099-K awareness for the card-issuing side (currently out of scope here, Stripe handles it separately).
- **Admin ops console** (`app/ops/`) — `GET /api/ops/summary` is a one-screen view of everything needing admin attention (pending approvals, open disputes, vendors with a sanctions hit, sync errors, open reconciliation discrepancies, unread notifications). `POST /api/ops/reconciliation-discrepancies/{id}/resolve` closes the loop the reconciliation engine opens: `RETRY` resets the underlying bill/reimbursement to `APPROVED` so it can be paid out again, `ACKNOWLEDGE` closes a false positive — both audit-logged.
  - **Still needed for production:** a real admin UI (today this is API-only), and broader ops actions (e.g. force-canceling a stuck card, manually re-running a single sync item) beyond the reconciliation-discrepancy workflow.

New env vars: `USE_REAL_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `COMPLYADVANTAGE_API_KEY`, `USE_REAL_SCREENING` (all optional, default to mock/off).

### Enterprise SSO (this pass)

- **SSO/SAML login via WorkOS** (`app/sso/`) — WorkOS abstracts SAML/OIDC across every major IdP (Okta, Azure AD, Google Workspace, OneLogin, etc.) behind one API, which is why it's the fast path here rather than implementing SAML directly. `POST /api/sso/connections` (admin) provisions a WorkOS Organization for the entity's email domain and returns an Admin Portal link where the customer's IT admin configures their actual IdP; the connection stays `PENDING` until `POST /api/sso/connections/{id}/activate` confirms it (mock client activates immediately for sandbox/demo). `GET /api/sso/login-url?email=` lets the frontend decide whether to show a password field at all — 404 falls back to normal login. `POST /api/sso/exchange` takes the IdP's authorization code, resolves the matching connection, and **just-in-time provisions** the user (`EMPLOYEE` role, `auth_provider="SSO"`, a random unusable password hash so the password-login path can never work for that account) if they don't already exist — from there an SSO user is indistinguishable from a password user. Defense in depth: the exchanged profile's email domain is checked against the connection's registered domain even though a real WorkOS connection should never mismatch, and an existing account under a different entity is never silently reassigned.
  - **Still needed for production:** a real WorkOS account and `WORKOS_API_KEY`/`WORKOS_CLIENT_ID`; a frontend `/sso-callback` route and a login-page branch that calls `GET /api/sso/login-url` before showing a password field; SCIM-based deprovisioning (today a deactivated IdP user still has a valid local account and JWT until it expires); and enforcing SSO-only login for a domain once configured (currently a JIT-provisioned SSO user's account exists locally and nothing stops an admin from also using password-reset-style flows against it, since none exist yet — see MFA's own "still needed" note).

New env vars: `WORKOS_API_KEY`, `WORKOS_CLIENT_ID`, `USE_REAL_SSO` (optional, default off/mock).

### Multi-currency support (this pass)

Auditing the schema for this surfaced a real, pre-existing bug: `BalanceSnapshot` (the running per-entity ledger balance) had `entity_id` as its *sole* primary key despite also carrying a `currency` column — every currency's deltas were landing on the same single row, so a USD hold and a EUR hold got silently summed into one meaningless number. Fixed at the root (composite `(entity_id, currency)` key) as part of this pass, not papered over.

- **Cards can now be issued and spent in a currency different from the entity's policy currency** — `Entity.base_currency` (default `USD`) is what `Card`/`CardRequest`/`SpendProgram`.`limit_amount` and all reporting totals are denominated in; `Card.currency`/`CardRequest.currency` (settable on `POST /api/cards/request`, validated against a supported-currency list, defaults to the entity's base currency) is what the card actually spends in — mirroring how real corporate card issuers work (a card is issued in one currency; spend on it settles in that currency; the *policy limit* is set by finance in the company's own currency).
- **New `app/fx/` module**: pluggable `FXRateClient` (mock deterministic rate table + real `ExchangeRateAPIClient` via exchangerate-api.com, `USE_REAL_FX`), following the same pattern as every other provider here. `GET /api/fx/currencies` and `GET /api/fx/rate?from_currency=&to_currency=`.
- **Fixed mixed-currency aggregation everywhere it existed**: card/program spend-limit checks at swipe time, the dashboard's total/by-department/by-category/by-time spend, and budget-vs-actual comparison all used to run a SQL-level `SUM()` across whatever currencies happened to be present — which silently adds incompatible units the moment more than one currency exists. All four now fetch `(amount, currency)` and convert+sum in Python (`fx.service.sum_converted`) before aggregating.
- **`GET /api/reporting/dashboard`** now includes a `currency` field on `metrics` naming what its totals are denominated in (the entity's `base_currency`).
  - **Still needed for production:** currency on `Bill`/`Reimbursement` (out of scope this pass — 1099-NEC reporting is inherently USD-only per IRS rules, so this was a deliberate boundary, not an oversight); the `Insight.potential_savings` rollup (`GET /api/insights/savings-summary`) still sums raw amounts across insights that could originate from different-currency cards — same class of bug as the dashboard, not yet fixed; historical FX-rate snapshotting for audit-correct point-in-time reporting (today a rate is always "now," so re-running a report for a past period uses today's rate, not the rate at settlement time); and a real `EXCHANGE_RATE_API_KEY` account.

New env vars: `USE_REAL_FX`, `EXCHANGE_RATE_API_KEY` (optional, default off/mock).

---

## Integration Status

### 1. Card Issuing - Stripe Issuing

| Status | Mode | Notes |
|--------|------|-------|
| ✅ **Real Sandbox Integration** | Test Mode | Uses real Stripe Issuing API in test mode. Creates actual virtual cardholders and cards. Physical cards can be created but won't ship in test mode. |

**Implementation:**
- Client: `StripeIssuingClient` in `backend/app/cards/partner_client.py`
- Webhook: `/api/webhooks/stripe` handles authorization, hold, and settlement events
- Environment Variables: `STRIPE_SECRET_KEY`, `USE_REAL_ISSUING=true`

**What's Working:**
- Virtual card creation with real Stripe cardholders
- Card freeze/unfreeze via Stripe API
- Spending limit updates via Stripe SpendingControls
- Webhook handlers for authorization → hold → settlement pipeline

**What's Needed for Production:**
- Business verification with Stripe
- Signed Issuing Program agreement
- Compliance review
- Switch from test mode (`sk_test_`) to live mode (`sk_live_`)
- Physical card fulfillment configuration
- PCI-DSS compliance audit (if handling full PANs, which we don't)

---

### 2. Bank Transfers - Dwolla

| Status | Mode | Notes |
|--------|------|-------|
| ✅ **Real Sandbox Integration** | Sandbox | Uses Dwolla Sandbox API for ACH transfers. Simulates transfer creation in demo mode. |

**Implementation:**
- Client: `DwollaPaymentRailClient` in `backend/app/bills/payment_rail.py`
- Webhook: `/api/webhooks/dwolla` handles transfer_completed, transfer_failed, transfer_cancelled
- Environment Variables: `DWOLLA_APP_KEY`, `DWOLLA_APP_SECRET`, `USE_REAL_PAYMENT_RAIL=true`

**What's Working:**
- Transfer initiation with Dwolla API structure
- Webhook handlers for transfer status updates
- Integration with bill payment and reimbursement payout flows

**What's Needed for Production:**
- Business verification with Dwolla
- Dwolla Partner approval
- Bank account verification (micro-deposits or instant verification)
- Switch from sandbox to production API
- Funding source setup for platform's Dwolla account
- NACHA compliance for ACH processing
- ~~Webhook signature verification~~ — done (`DWOLLA_WEBHOOK_SECRET`, HMAC-SHA256 on `X-Request-Signature-SHA256`)

---

### 3. Vendor Bank Account Linking - Plaid

| Status | Mode | Notes |
|--------|------|-------|
| ✅ **Real Sandbox Integration** | Sandbox | Uses Plaid Link in sandbox mode with test institutions. Replaces manual account entry. |

**Implementation:**
- Client: `PlaidClient` in `backend/app/plaid/client.py`
- API: `/api/plaid/link-token`, `/api/plaid/exchange-public-token`
- Environment Variables: `PLAID_CLIENT_ID`, `PLAID_SECRET`, `USE_REAL_PLAID=true`

**What's Working:**
- Plaid Link token generation for frontend
- Public token exchange for access tokens
- Account retrieval and masking (last 4 digits only)
- Storage of Plaid tokens in `vendor_bank_accounts` table

**What's Needed for Production:**
- Plaid business account approval
- Switch from sandbox to production environment
- Implement bank account verification (if not using Plaid's built-in)
- Ensure compliance with Plaid's data retention policies

---

### 4. Entity Onboarding (KYC/KYB) - Didit

| Status | Mode | Notes |
|--------|------|-------|
| ✅ **Real Sandbox Integration** | Demo/Sandbox | Uses Didit for KYC/KYB verification. Free alternative to Persona. |

**Implementation:**
- Client: `DiditClient` in `backend/app/kyc/client.py`
- Webhook: `/api/webhooks/didit` handles verification status updates
- Environment Variables: `DIDIT_API_KEY`, `USE_REAL_DIDIT=true`, `AUTO_APPROVE_ONBOARDING=true`

**What's Working:**
- Verification creation on entity registration
- Verification status checking
- Webhook handler for approval/rejection updates
- Auto-approval in sandbox mode for demo purposes

**What's Needed for Production:**
- Didit business account setup
- Configure production API endpoints
- Remove `AUTO_APPROVE_ONBOARDING` flag
- Implement proper verification flow with real document submission
- Ensure compliance with KYC/AML regulations
- ~~Webhook signature verification~~ — done (`DIDIT_WEBHOOK_SECRET`, HMAC-SHA256 on `X-Didit-Signature`)

---

### 5. Accounting/ERP Sync - QuickBooks Online

| Status | Mode | Notes |
|--------|------|-------|
| ✅ **Real Sandbox Integration** | Sandbox | Uses QBO Sandbox API for OAuth and data sync. |

**Implementation:**
- Client: `QuickBooksOnlineClient` in `backend/app/qbo/client.py`
- API: `/api/qbo/oauth-url`, `/api/qbo/exchange-token`, `/api/qbo/sync-accounts`
- Environment Variables: `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_REDIRECT_URI`, `USE_REAL_QBO=true`

**What's Working:**
- OAuth flow for QBO connection
- Chart of accounts sync from QBO sandbox company
- Token storage in `erp_connections` table
- Journal entry and bill creation API structure

**What's Needed for Production:**
- Intuit Developer account approval
- Production OAuth app credentials
- ~~Implement token refresh logic~~ — done (`refresh_access_token`, auto-refreshed within 5 minutes of expiry via `get_valid_qbo_connection`)
- ~~Full sync queue implementation for transactions/bills/reimbursements~~ — done: `/api/accounting/sync/process` now pushes real journal entries to QBO when an `ERPConnection` exists, instead of always simulating
- ~~Error handling and retry logic for sync failures~~ — done: failed items retry with exponential backoff (up to 5 attempts) before landing in `ERROR`

---

## Core Business Logic Status

The following modules are **production-ready** and do not require external provider changes:

| Module | Status | Notes |
|--------|--------|-------|
| ✅ Ledger Core | Production Ready | Double-entry bookkeeping, transaction state machine |
| ✅ Approval Workflow Engine | Production Ready | Multi-step approval routing, role-based decisions |
| ✅ RBAC/Multi-Entity | Production Ready | Entity scoping, role-based access control |
| ✅ Insights/Anomaly Detection | Production Ready | Rules-based duplicate detection, price increase alerts |
| ✅ Bill Pay AP | Production Ready (with Dwolla sandbox) | Vendor invoices, approval routing, payment initiation |
| ✅ Reimbursements | Production Ready (with Dwolla sandbox) | Out-of-pocket and mileage reimbursements |

---

## Sandbox Mode Indicator

The application includes a sandbox mode indicator. When running with sandbox credentials, the following should be displayed in the UI:

- **Admin Dashboard:** "Sandbox Mode" badge
- **API Responses:** `X-Sandbox-Mode: true` header
- **Webhook Logs:** Clear indication of sandbox vs production events

---

## Environment Variables Summary

To enable real sandbox integrations, set the following environment variables:

```bash
# Stripe Issuing
STRIPE_SECRET_KEY=sk_test_...
USE_REAL_ISSUING=true

# Dwolla
DWOLLA_APP_KEY=...
DWOLLA_APP_SECRET=...
USE_REAL_PAYMENT_RAIL=true

# Plaid
PLAID_CLIENT_ID=...
PLAID_SECRET=...
USE_REAL_PLAID=true

# Didit
DIDIT_API_KEY=...
USE_REAL_DIDIT=true
AUTO_APPROVE_ONBOARDING=true  # For demo only

# QuickBooks Online
QBO_CLIENT_ID=...
QBO_CLIENT_SECRET=...
QBO_REDIRECT_URI=http://localhost:5173/qbo-callback
USE_REAL_QBO=true
```

---

## Next Steps

1. **Review `GOING_LIVE.md`** for business/legal requirements to move to production
2. **Complete provider business verifications** for each integration
3. **Run integration tests** with real sandbox credentials: `pytest backend/app/tests/test_integrations.py`
4. **Perform end-to-end testing** of all flows in sandbox mode
5. **Configure production OAuth callbacks** and webhooks
6. **Implement token refresh logic** for QBO and other OAuth providers
7. **Add monitoring and alerting** for webhook failures and sync errors

---

## Disclaimer

**This application is in sandbox/demo mode only.** No real money moves, no real cards are issued, and no real ACH transfers are processed. All integrations use provider sandbox environments for demonstration purposes. To move to production, complete all business/legal steps outlined in `GOING_LIVE.md`.
