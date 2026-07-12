# Going Live - Business and Legal Requirements

This document outlines the business, legal, and compliance steps required to move each integration from sandbox/demo mode to production. These steps are outside the scope of code changes and require business decisions, agreements, and regulatory compliance.

---

## 1. Stripe Issuing - Production Readiness

### Business Requirements
- **Business Verification:** Complete Stripe's business verification process
  - Submit business formation documents (articles of incorporation, etc.)
  - Provide tax identification (EIN in the US)
  - Verify business address and ownership
  - Provide bank account for settlement

- **Issuing Program Agreement:** Sign Stripe's Issuing Program agreement
  - Review and sign the Stripe Issuing Program Agreement
  - Understand liability and chargeback responsibilities
  - Settle on pricing and fee structure

- **Compliance Review:** Undergo Stripe's compliance review
  - AML/KYC program documentation
  - Risk management policies
  - Fraud prevention procedures

### Legal/Regulatory Requirements
- **PCI-DSS Compliance:** If handling full PANs (currently we only store masked tokens)
  - Complete PCI-DSS Self-Assessment Questionnaire (SAQ)
  - Implement required security controls
  - Annual PCI audit if required

- **State Licensing:** Depending on card program structure
  - Money transmitter license may be required in some jurisdictions
  - Consult legal counsel for specific requirements

### Technical Steps
- Switch API keys from test mode (`sk_test_`) to live mode (`sk_live_`)
- Configure physical card fulfillment with card shipping provider
- Implement webhook signature verification (currently skipped in sandbox)
- Set up production monitoring and alerting for authorization failures
- Configure spending limits and fraud rules for production

### Estimated Timeline
- Business verification: 1-2 weeks
- Agreement signing: 1 week
- Compliance review: 2-4 weeks
- **Total: 4-7 weeks**

---

## 2. Dwolla - Production Readiness

### Business Requirements
- **Partner Approval:** Apply for and receive Dwolla Partner approval
  - Complete Dwolla's partner application
  - Provide business documentation
  - Undergo background checks

- **Business Verification:** Verify business identity
  - Submit business formation documents
  - Provide tax identification
  - Verify beneficial owners

- **Funding Source Setup:** Configure funding sources
  - Set up platform's Dwolla account with verified bank account
  - Configure funding source for customer transfers
  - Set up reserve accounts if required

### Legal/Regulatory Requirements
- **NACHA Compliance:** Comply with NACHA operating rules for ACH
  - Implement proper ACH return handling
  - Follow NACHA timing requirements
  - Maintain proper record retention

- **Money Transmitter License:** Required in most US states
  - Obtain money transmitter license in each state where customers operate
  - Maintain surety bonds as required by states
  - File regular reports with state regulators

- **AML/KYC Program:** Implement comprehensive AML/KYC program
  - Customer due diligence (CDD)
  - Enhanced due diligence for high-risk customers
  - OFAC screening
  - Suspicious activity reporting (SAR)

### Technical Steps
- Switch from sandbox to production API endpoints
- Implement full Dwolla customer creation and verification flow
- Add micro-deposit verification for bank accounts
- Implement webhook signature verification
- Set up production monitoring for transfer failures
- Configure retry logic for failed transfers

### Estimated Timeline
- Partner approval: 2-4 weeks
- Business verification: 1-2 weeks
- State licensing: 3-6 months (varies by state)
- **Total: 4-7 months** (state licensing is the bottleneck)

---

## 3. Plaid - Production Readiness

### Business Requirements
- **Plaid Business Account:** Apply for Plaid business account
  - Complete Plaid's business application
  - Provide business documentation
  - Agree to Plaid's terms of service

- **Pricing Agreement:** Establish pricing with Plaid
  - Review Plaid's pricing tiers
  - Choose appropriate plan基于 expected volume
  - Negotiate enterprise terms if needed

### Legal/Regulatory Requirements
- **Data Privacy Compliance:** Comply with data privacy regulations
  - GDPR compliance if serving EU customers
  - CCPA compliance for California residents
  - Implement proper data handling and consent

- **Bank Data Security:** Ensure secure handling of bank data
  - Follow Plaid's security best practices
  - Implement proper encryption for stored tokens
  - Follow data retention policies

### Technical Steps
- Switch from sandbox to production environment
- Update Plaid Link configuration for production
- Implement proper error handling for bank account failures
- Add bank account verification (if not using Plaid's built-in)
- Set up monitoring for Plaid API failures
- Configure production webhook endpoints

### Estimated Timeline
- Business account approval: 1-2 weeks
- Pricing agreement: 1 week
- **Total: 2-3 weeks**

---

## 4. Didit (KYC/KYB) - Production Readiness

### Business Requirements
- **Didit Business Account:** Set up Didit business account
  - Complete Didit's business application
  - Provide business documentation
  - Configure verification workflows

- **Verification Templates:** Configure verification templates
  - Set up business verification workflow
  - Configure document requirements
  - Set up approval/rejection criteria

### Legal/Regulatory Requirements
- **KYC/AML Compliance:** Implement comprehensive KYC/AML program
  - Customer identification program (CIP)
  - Customer due diligence (CDD)
  - Ongoing monitoring
  - Risk-based approach

- **Data Privacy:** Comply with data privacy regulations for personal data
  - GDPR compliance for EU data subjects
  - CCPA compliance for California residents
  - Proper consent management

- **Document Retention:** Follow regulatory requirements for document retention
  - Maintain KYC records for required period (typically 5 years)
  - Secure storage of sensitive documents
  - Proper disposal procedures

### Technical Steps
- Configure production Didit API endpoints
- Remove `AUTO_APPROVE_ONBOARDING` flag
- Implement proper verification flow with real document submission
- Add verification status polling or webhook handling
- Implement retry logic for failed verifications
- Set up monitoring for verification failures

### Estimated Timeline
- Business account setup: 1-2 weeks
- Workflow configuration: 1 week
- **Total: 2-3 weeks**

---

## 5. QuickBooks Online - Production Readiness

### Business Requirements
- **Intuit Developer Account:** Apply for Intuit Developer account
  - Complete Intuit's developer application
  - Provide business documentation
  - Agree to Intuit's terms of service

- **OAuth App Approval:** Get OAuth app approved for production
  - Submit OAuth app for production review
  - Provide app description and use case
  - Configure production redirect URIs

### Legal/Regulatory Requirements
- **Data Access Agreement:** Agree to Intuit's data access terms
  - Review and sign Intuit's data access agreement
  - Understand data usage restrictions
  - Comply with data retention requirements

- **Accountant Access:** If providing accounting services
  - May require professional accountant credentials
  - Follow professional standards and regulations

### Technical Steps
- Switch from sandbox to production OAuth credentials
- Implement OAuth token refresh logic
- Configure production webhook endpoints
- Implement full sync queue for transactions/bills/reimbursements
- Add error handling and retry logic for sync failures
- Set up monitoring for QBO API failures
- Implement rate limiting for QBO API calls

### Estimated Timeline
- Developer account approval: 1-2 weeks
- OAuth app approval: 1-2 weeks
- **Total: 2-4 weeks**

---

## Cross-Cutting Requirements

### Security
- **TLS/SSL:** All API communication must use TLS 1.2 or higher
- **Encryption:** Encrypt sensitive data at rest (API keys, tokens)
- **Secrets Management:** Use proper secrets management (not environment variables in production)
- **Audit Logging:** Comprehensive audit logging for all financial operations
- **Penetration Testing:** Annual penetration testing

### Compliance
- **SOC 2:** Consider SOC 2 Type II certification for B2B customers
- **ISO 27001:** Information security management certification
- **Privacy Policy:** Comprehensive privacy policy covering all data handling
- **Terms of Service:** Clear terms of service outlining liability and responsibilities

### Insurance
- **Cyber Insurance:** Cyber liability insurance policy
- **Errors & Omissions:** E&O insurance for financial services
- **Fidelity Bond:** Fidelity bond for employee dishonesty (if required)

### Operations
- **Monitoring:** Comprehensive monitoring and alerting
- **Disaster Recovery:** Disaster recovery plan with regular testing
- **Business Continuity:** Business continuity plan
- **Incident Response:** Incident response plan and team

---

## Recommended Go-Live Sequence

1. **Phase 1 (Low Risk):** Plaid and Didit
   - These don't move money
   - Lower regulatory burden
   - Can be done in parallel

2. **Phase 2 (Medium Risk):** QuickBooks Online
   - Data sync only, no money movement
   - Requires OAuth but no financial licensing

3. **Phase 3 (High Risk):** Stripe Issuing
   - Requires business verification and compliance
   - Cards can be used for fraud if not properly secured

4. **Phase 4 (Highest Risk):** Dwolla
   - Requires state money transmitter licenses
   - Highest regulatory burden
   - Longest timeline

---

## Legal Counsel Recommendation

**Engage legal counsel with fintech experience** to review:
- Money transmitter license requirements
- State-by-state compliance obligations
- AML/KYC program adequacy
- Customer agreements and terms of service
- Privacy policy adequacy
- Insurance requirements

---

## Estimated Total Timeline

- **Fastest Path (Plaid + Didit + QBO only):** 2-4 months
- **With Stripe Issuing:** 3-5 months
- **Full Stack (including Dwolla):** 6-9 months (state licensing is the bottleneck)

---

## Disclaimer

This document is for informational purposes only and does not constitute legal advice. Regulatory requirements vary by jurisdiction and business model. Consult qualified legal counsel before making business decisions based on this document.
