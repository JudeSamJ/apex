# PCI-DSS Scoping & Cardholder Data Stance

This document details the PCI-DSS compliance boundaries and tokenization architecture of the B2B Fintech Platform.

---

## 1. Compliance Scope & Boundaries

The Apex platform is designed with a **Mock-First / Tokenization Architecture**, which keeps the cardholder data environment (CDE) completely out of scope of our core application servers. 

* **Primary Account Numbers (PANs)**: Full 16-digit card numbers are **never** stored, processed, or transmitted by the Apex backend application or database.
* **Card Verification Values (CVVs)**: Raw CVV codes are never handled or logged.
* **Database Storage**: The card tables store only masked PANs (`************1234`) and unique partner tokens (`card_token`), which are non-reversible references resolving to the card details at the issuing bank's API.

```
       [ Client Browser ]
               │
      (Request Card/Swipe)
               │
               ▼
       [ Apex API Server ] ──(card_token)──> [ Celtic Bank / Stripe Issuing API ]
     * Keeps ONLY card_token                 * Secure PCI-Compliant CDE
     * PAN / CVV never touches DB             * Stores raw PAN / PIN / CVV
```

---

## 2. Tokenization Stance & PAN Audit Results

A full audit of the codebase, seed databases, log files, and test files was performed using regular expression scanners matching 16-digit sequence patterns.

* **Checked Areas**: `app/cards`, `app/transactions`, database sqlite seeds, and test suites.
* **Findings**: Zero raw PAN or CVV records were discovered. All card references utilize masked strings or random UUID-based hashes representing API keys.
* **Verdict**: The current backend codebase is 100% out of scope for PCI-DSS audit requirements.
