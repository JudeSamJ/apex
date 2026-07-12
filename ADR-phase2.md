# Architecture Decision Record — Phase 2 (Approvals, Bill Pay & Reimbursements)

## 1. Unified Approvals Pipeline
* **Decision**: Implemented a generalized `Approval`, `ApprovalStep`, and `ApprovalRule` database structure instead of writing custom, isolated approval state fields inside card requests, vendor bills, and reimbursement records.
* **Rationale**: Decouples logic of steps routing from individual module schemas. This allows easily extending rules (e.g. multi-step logic) for any type of entity request without schema mutations.

## 2. Shared Payout Rail
* **Decision**: Created a single `MockPaymentRailClient` to simulate ACH/bank transfers.
* **Rationale**: Eliminates duplication of mock disbursement logic. Both AP vendor bill payouts and employee reimbursement payouts route through the same rails using unified transaction tracking.

## 3. Fuzzy Duplicate Vendor Matching
* **Decision**: Implemented a simple string-cleansing fuzzy matches routine to check if a new vendor matches any existing vendor name.
* **Rationale**: Restricts database duplicate entry accumulation at MVP scale without introducing heavy external NLP or machine learning libraries.

## 4. Admin Overrides in Workflow Engine
* **Decision**: Integrated an implicit authorization override where users with the `ADMIN` role can approve any pending step.
* **Rationale**: Preserves administrative control and backward compatibility with Phase 1's integration tests which rely on direct admin-mediated overrides.
