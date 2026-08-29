# Apex — B2B Corporate Card & Spend Management Platform

Apex is a full-stack, Ramp/Brex-style corporate card and spend management
platform: it issues virtual and physical cards, routes every dollar through
policy and approvals, keeps a real-time ledger, and pushes clean, GL-coded
data out to your books. This document explains what it does, how the pieces
fit together, and who it's built for.

---

## 1. Who this is for

Apex is built for any company that has moved past "one shared corporate card
and a shoebox of receipts" and needs real controls without buying a full
enterprise finance stack. It's a strong fit for:

| Sector / company type | Why Apex helps |
|---|---|
| **Startups & scale-ups (Seed–Series C)** | Issue cards per employee/department instantly, cap spend before it happens instead of clawing it back, and keep books audit-ready for the next funding round without hiring a controller early. |
| **Digital agencies & professional services** | Track client-billable spend by department/project via custom fields, and reimburse contractor/employee expenses with a real approval trail. |
| **E-commerce & DTC brands** | Multi-currency support and vendor bill pay suit teams paying overseas suppliers and ad platforms; spend-leakage insights catch forgotten SaaS renewals. |
| **Multi-entity / holding companies** | Native parent/subsidiary entity structure, with users able to switch between entities they hold a role in and reporting that respects entity boundaries. |
| **Companies going through KYB/compliance** | Built-in onboarding status gate (nothing moves money until KYB is approved), AML/OFAC sanctions screening, and an audit log covering every state-changing action. |
| **Bookkeeping/accounting firms managing several clients** | Bookkeeper is a first-class role scoped to audit logs and financial reporting without full admin rights, and the entity switcher supports managing more than one company from one login. |
| **Any regulated or compliance-conscious org (fintech, healthcare admin, nonprofits)** | MFA, SSO/SAML via WorkOS, rate-limited login, and a dedicated Ops Center for disputes, reconciliation, and sanctions screening give the paper trail auditors ask for. |

---

## 2. The core flow, end to end

This is the actual path data takes through the app, in order:

1. **Sign-up & onboarding** — A new user registers against an existing
   company (or an admin creates a new company). New self-registered users
   land as `PENDING` with no role until an admin approves them and assigns a
   role and department. A company itself starts `PENDING` until its KYB is
   approved (root-entity admins approve subsidiary companies) — nothing that
   moves money works until then.
2. **Sign-in** — Email/password (rate-limited, with optional TOTP MFA), or
   enterprise SSO (WorkOS-backed SAML/OIDC, JIT-provisions the user on first
   login). Forgot/reset password uses single-use JWT tokens.
3. **Spend programs & card issuance** — An admin defines a *spend program*
   (a limit + limit type + allowed merchant categories). Employees request a
   card against a program; on approval a virtual or physical card is issued,
   with optional per-card velocity controls (max single transaction, max
   swipes/day) layered on top of the program's limit.
4. **Spend happens** — Card Swipe simulates real-time authorization against
   every active control (program limit, card limit, velocity controls,
   entity KYB status) and posts to a double-entry ledger. Receipts can be
   attached to any settled transaction.
5. **Non-card spend** — Vendor invoices go through **Bill Pay** (vendor →
   bill → approval → payment-rail payout, reconciled via webhook). Personal
   out-of-pocket spend goes through **Reimbursements** (claim → approval →
   payout), each GL-coded on the way in.
6. **Approvals** — Card requests, bills, and reimbursements all route
   through a configurable multi-step approval engine before money moves.
7. **Books stay current** — **Accounting** holds the chart of accounts and
   auto-coding rules (by merchant category, vendor, or department); settled
   activity flows into a mock ERP sync queue the same way it would to
   QuickBooks Online in production.
8. **Oversight** — **Insights** runs spend-leakage/anomaly detection over
   settled activity and tracks confirmed savings. The **Ops Center** is the
   admin/compliance control tower: pending user and company approvals,
   sanctions screening, card disputes, payment-rail reconciliation, and a
   KPI rollup of anything that needs attention.
9. **Tax time** — **Tax Reporting** rolls up 1099-NEC eligible vendor
   payments per year, with a CSV export formatted for filing.
10. **Everything is logged** — every state-changing action writes an audit
    log entry (who, what, when), and in-app notifications alert the right
    people as things happen.

---

## 3. Feature list

**Identity & access**
- Email/password login with TOTP-based MFA
- Enterprise SSO (WorkOS SAML/OIDC), with just-in-time user provisioning
- Self-registration into an existing company with admin approval
- Admin-driven company creation, with root-admin approval for subsidiaries
- Forgot/reset password (single-use tokens)
- Rate-limited login (Redis-backed, falls back to in-memory)
- Role-based access control: `ADMIN`, `MANAGER`, `EMPLOYEE`, `BOOKKEEPER`
- Multi-entity support with a parent/subsidiary hierarchy and an entity switcher
- Department-scoped data access

**Cards & spend**
- Spend programs (limit, limit type, allowed merchant categories)
- Card requests with approval routing
- Virtual and physical card issuance, freeze/unfreeze
- Per-card velocity controls (single-transaction cap, daily swipe count cap)
- Multi-currency card support
- Real-time swipe simulation against every active control
- Double-entry ledger with idempotent posting
- Paginated transaction feed with CSV export
- Receipt upload/attach per transaction

**Payables & reimbursements**
- Vendor management and bill creation
- Bill approval routing and payment-rail payout (webhook-driven status updates)
- Employee expense reimbursement claims with GL coding
- Configurable multi-step approval engine shared across cards/bills/reimbursements

**Accounting & reporting**
- Chart of accounts (GL accounts)
- Auto-coding rules by merchant category, vendor, or department
- Custom fields for transaction/expense coding
- Mock ERP sync queue (models a QuickBooks Online-style push)
- Budget vs. actual reporting by department
- Admin KPI dashboard (auto-audit efficiency, money saved, compliance score, approval turnaround)
- 1099-NEC tax reporting with CSV export
- Full audit log, paginated

**Risk & compliance**
- Onboarding/KYB status gate — blocks money movement on unapproved entities
- AML/OFAC sanctions screening for vendors
- Card dispute/chargeback handling
- Payment-rail reconciliation runs
- Signed, verified payment-rail webhooks

**Operational**
- Spend-leakage and anomaly detection (Insights) with confirmed-savings tracking
- In-app notifications with unread counts
- Background job processing for async settlement/sync work
- Structured logging, request-ID tracing, Sentry-ready observability

**Frontend UX**
- Single-page, role-aware dashboard (only see the nav items your role can use)
- Fully mobile-responsive: the sidebar becomes an off-canvas drawer below 900px wide
- Hover/focus reference tooltips on every sidebar item — what it is, why it exists, how to use it — so new users don't need a separate manual
- Dark theme with a full-bleed video login screen

---

## 4. Architecture

```
┌─────────────────────┐        /api/...  (same-origin)        ┌──────────────────────┐
│   Frontend (Vite)    │ ─────────────────────────────────▶  │   Backend (FastAPI)   │
│   React 19 + TS       │  ◀─────────────────────────────────  │   SQLAlchemy + Alembic│
│   single-page app     │        JSON over HTTPS                │                        │
└─────────────────────┘                                        └──────────┬────────────┘
                                                                            │
                                                          ┌─────────────────┼─────────────────┐
                                                          │                 │                 │
                                                   ┌──────▼─────┐   ┌───────▼──────┐   ┌───────▼──────┐
                                                   │  Postgres   │   │    Redis      │   │  Mock/real    │
                                                   │  (or SQLite │   │ (rate limit + │   │  integrations │
                                                   │   in dev)   │   │   Celery)     │   │ (Stripe, Plaid,│
                                                   └────────────┘   └──────────────┘   │  Dwolla, QBO,  │
                                                                                        │  WorkOS, Didit)│
                                                                                        └────────────────┘
```

- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic migrations. SQLite by default
  for zero-setup local dev; Postgres (Neon-compatible) in production via
  `DATABASE_URL`. Every external integration (card issuing, payment rails,
  Plaid, QuickBooks, KYC, SSO) is behind a mock/real client switch
  (`USE_REAL_*` env flags) so the whole app runs end to end with no
  third-party accounts required.
- **Frontend**: React 19 + TypeScript + Vite. Deliberately no router or
  state-management library — a single ~4,700-line component with a
  tab-based `activeTab` switch. Calls `/api/...` on its own origin; a Vite
  dev-proxy locally and a Vercel rewrite in production forward that to the
  backend, so there's no CORS preflight and no backend URL baked into the
  bundle.
- **CI**: GitHub Actions on every push to `main` and every PR — backend
  pytest suite, frontend `oxlint` + `tsc` + `vite build`.
- **Deployment**: Vercel for both frontend and backend (see `vercel.json`
  and `backend/.env.example`). `RUN_MIGRATIONS_ON_STARTUP` toggles whether
  the app runs `alembic upgrade head` on boot (on for a normal server, off
  for serverless where cold starts would race migrations).

---

## 5. Roles at a glance

| Role | Can do |
|---|---|
| `EMPLOYEE` | Request cards, swipe (once issued), submit reimbursement claims, view own activity |
| `MANAGER` | Everything an employee can, plus approve requests routed to them |
| `BOOKKEEPER` | View audit logs and financial reporting/tax exports across the entity, without admin control over users or cards |
| `ADMIN` | Full control: spend programs, GL accounts and mapping rules, user approval, SSO/MFA setup, Ops Center, company creation (root-entity admins also approve subsidiary companies) |

---

## 6. Getting started locally

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # defaults to local SQLite, no external services required
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173, proxies /api to :8000
```

**Try it out**: open the app, click **Seed Database with Demo Data** on the
login screen (or `POST /api/auth/seed`), then sign in with one of the demo
profiles shown on the login page (all use password `password123`) — an
admin, a manager, an employee, and a bookkeeper, each scoped realistically
across the seeded parent/subsidiary entities.

**Backend tests**: `cd backend && python -m pytest -q`

---

## 7. Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19, TypeScript, Vite, lucide-react icons |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL (production), SQLite (local dev) |
| Auth | JWT access tokens, passlib/bcrypt, pyotp (TOTP MFA), WorkOS (SSO) |
| Background/queue | Celery + Redis (optional locally — falls back gracefully) |
| Integrations (mockable) | Stripe Issuing, Dwolla, Plaid, QuickBooks Online, Didit (KYC) |
| CI | GitHub Actions |
| Hosting | Vercel (frontend + backend) |

---

## 8. Further reading

- `PRODUCTION_READINESS_REPORT.md` — what's been hardened for production use
- `GOING_LIVE.md` — the business/legal/compliance steps to flip each mocked integration to real (Stripe, Dwolla, Plaid, etc.)
- `SECURITY_PCI_SCOPE.md` — PCI-DSS scope notes
- `ADR-phase1.md` … `ADR-phase4.md` — architecture decision records from each build phase
- `backend/.env.example` — every environment variable the backend reads, documented inline
