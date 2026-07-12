# Production Readiness Report

**Generated:** July 13, 2026  
**Status:** Sandbox/Demo Mode - Not Production Ready

## Overview

This report tracks the integration status of all external providers. The application currently runs in **sandbox/demo mode** using real provider sandbox environments. This provides realistic API round-trips and data for client demos but is **not suitable for production use** without completing the business/legal steps outlined in `GOING_LIVE.md`.

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
- Implement token refresh logic
- Full sync queue implementation for transactions/bills/reimbursements
- Error handling and retry logic for sync failures

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
