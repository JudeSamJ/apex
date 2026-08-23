import React, { useState, useEffect } from 'react';
import {
  CreditCard,
  TrendingUp,
  Layers,
  RefreshCw,
  ShieldAlert,
  Check,
  X,
  Lock,
  Unlock,
  AlertTriangle,
  DollarSign,
  CheckSquare,
  FileText,
  Receipt,
  MapPin,
  Database,
  Sliders,
  Settings,
  Bell,
  Shield
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

interface UserMe {
  id: string;
  email: string;
  name: string;
  active_entity_id: string;
  roles: string[];
  accessible_departments: string[] | null;
  mfa_enabled?: boolean;
}

interface Entity {
  id: string;
  name: string;
  onboarding_status: string;
  parent_entity_id: string | null;
}

interface Department {
  id: string;
  entity_id: string;
  name: string;
}

interface SpendProgram {
  id: string;
  name: string;
  limit_amount: number;
  limit_type: string;
  allowed_mcc: string[] | null;
}

interface Card {
  id: string;
  owner_name: string;
  department_name: string;
  spend_program_name: string;
  type: string;
  limit_amount: number;
  currency: string;
  status: string;
  masked_pan: string;
  created_at: string;
}

interface CardRequest {
  id: string;
  requester_name: string;
  department_name: string;
  spend_program_name: string;
  type: string;
  limit_amount: number;
  currency: string;
  status: string;
  created_at: string;
}

interface Transaction {
  id: string;
  owner_name: string;
  masked_pan: string;
  amount: number;
  currency: string;
  merchant_name: string;
  merchant_mcc: string;
  category: string | null;
  status: string;
  decline_reason: string | null;
  created_at: string;
}

interface DashboardMetrics {
  metrics: {
    total_spend: number;
    active_cards: number;
    pending_requests: number;
    currency?: string;
  };
  spend_by_department: { department: string; amount: number }[];
  spend_by_category: { category: string; amount: number }[];
  spend_over_time: { date: string; amount: number }[];
}

interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string | null;
  read: boolean;
  created_at: string;
}

interface OpsSummary {
  pending_approvals: number;
  open_disputes: number;
  vendors_sanctions_hit: number;
  sync_errors: number;
  open_reconciliation_discrepancies: number;
  unread_admin_notifications: number;
}

interface ScreeningRecord {
  id: string;
  subject_type: string;
  subject_id: string;
  subject_name: string;
  provider: string;
  status: string;
  match_details: any;
  created_at: string;
}

interface CardDispute {
  id: string;
  card_id: string | null;
  transaction_id: string | null;
  stripe_dispute_id: string;
  amount: number;
  reason: string | null;
  status: string;
  evidence_note: string | null;
  created_at: string;
  updated_at: string;
}

interface ReconciliationRun {
  id: string;
  provider: string;
  status: string;
  checked_count: number;
  discrepancy_count: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

interface ReconciliationDiscrepancy {
  id: string;
  subject_type: string;
  subject_id: string;
  transfer_ref: string;
  local_status: string;
  provider_status: string;
  amount: number | null;
  resolved: string | null;
  created_at: string;
}

interface NecReportRow {
  vendor_id: string;
  vendor_name: string;
  tax_id: string | null;
  tax_address: string | null;
  total_paid: number;
  payment_count: number;
  reportable: boolean;
}

interface SSOConnection {
  id: string;
  domain: string;
  provider: string;
  status: string;
  admin_portal_url: string | null;
  created_at: string;
}

interface PendingUser {
  id: string;
  email: string;
  name: string;
  requested_role_id: string | null;
  requested_department_id: string | null;
  created_at: string | null;
}

const ROLE_OPTIONS = ['EMPLOYEE', 'MANAGER', 'AP_APPROVER', 'BOOKKEEPER', 'ADMIN'];

interface ApprovalStep {
  id: string;
  approval_id: string;
  approvable_type: string;
  approvable_id: string;
  step_number: number;
  total_steps: number;
  approver_role: string;
  department_name: string;
  created_at: string;
}

interface Vendor {
  id: string;
  name: string;
}

interface BillLineItem {
  description: string;
  amount: number;
  gl_account_id?: string;
}

interface Bill {
  id: string;
  department_name: string;
  vendor_name: string;
  status: string;
  due_date: string;
  total_amount: number;
  payment_method: string;
  approval_id: string | null;
  line_items: BillLineItem[];
}

interface Waypoint {
  sequence: number;
  address: string;
}

interface TripDetails {
  purpose: string;
  mileage_rate: number;
  total_miles: number;
  computed_amount: number;
  waypoints: Waypoint[];
}

interface Reimbursement {
  id: string;
  type: string;
  status: string;
  total_amount: number;
  requester_name: string;
  department_name: string;
  approval_id: string | null;
  submitted_at: string;
  line_items: BillLineItem[];
  trip: TripDetails | null;
}

interface GLAccount {
  id: string;
  code: string;
  name: string;
  type: string;
  is_active: boolean;
}

interface GLMapping {
  id: string;
  mapping_type: string;
  source_value: string;
  gl_account_id: string;
  gl_account_code: string;
  gl_account_name: string;
}

interface SyncQueueItem {
  id: string;
  record_type: string;
  record_id: string;
  gl_account_id: string;
  gl_account_code: string;
  gl_account_name: string;
  status: string;
  error_message: string | null;
  synced_at: string | null;
  created_at: string;
}

interface CustomField {
  id: string;
  name: string;
  field_type: string;
  select_options: string[] | null;
  is_required: boolean;
}

interface Insight {
  id: string;
  type: string;
  status: string;
  severity: string;
  description: string;
  potential_savings: number;
  created_at: string;
}

interface BudgetCompare {
  id: string;
  department_name: string;
  category: string;
  period: string;
  budgeted_amount: number;
  actual_amount: number;
  remaining_amount: number;
}

interface AdminKPIs {
  operational_efficiency: number;
  money_saved: number;
  compliance_score: number;
  avg_approval_turnaround_hours: number;
}

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [user, setUser] = useState<UserMe | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [activeEntityId, setActiveEntityId] = useState<string>('');
  const [departments, setDepartments] = useState<Department[]>([]);
  const [spendPrograms, setSpendPrograms] = useState<SpendProgram[]>([]);
  
  // Dashboard & Feed Data
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [cardRequests, setCardRequests] = useState<CardRequest[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  
  // Phase 2 State Data
  const [approvalSteps, setApprovalSteps] = useState<ApprovalStep[]>([]);
  const [bills, setBills] = useState<Bill[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [reimbursements, setReimbursements] = useState<Reimbursement[]>([]);

  // Phase 3 State Data
  const [glAccounts, setGlAccounts] = useState<GLAccount[]>([]);
  const [glMappings, setGlMappings] = useState<GLMapping[]>([]);
  const [syncQueue, setSyncQueue] = useState<SyncQueueItem[]>([]);
  const [, setCustomFields] = useState<CustomField[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [totalSavings, setTotalSavings] = useState<number>(0);
  const [budgets, setBudgets] = useState<BudgetCompare[]>([]);
  const [adminKPIs, setAdminKPIs] = useState<AdminKPIs | null>(null);

  // Notifications / Ops Center / SSO / MFA / FX state
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [showNotifications, setShowNotifications] = useState<boolean>(false);
  const [opsSummary, setOpsSummary] = useState<OpsSummary | null>(null);
  const [screenings, setScreenings] = useState<ScreeningRecord[]>([]);
  const [disputes, setDisputes] = useState<CardDispute[]>([]);
  const [reconciliationRuns, setReconciliationRuns] = useState<ReconciliationRun[]>([]);
  const [reconciliationDiscrepancies, setReconciliationDiscrepancies] = useState<Record<string, ReconciliationDiscrepancy[]>>({});
  const [necReport, setNecReport] = useState<NecReportRow[]>([]);
  const [necYear, setNecYear] = useState<number>(new Date().getFullYear());
  const [ssoConnections, setSsoConnections] = useState<SSOConnection[]>([]);
  const [ssoDomainInput, setSsoDomainInput] = useState<string>('');
  const [supportedCurrencies, setSupportedCurrencies] = useState<string[]>(['USD']);
  const [disputeEvidenceInput, setDisputeEvidenceInput] = useState<Record<string, string>>({});
  const [vendorTaxIdInput, setVendorTaxIdInput] = useState<string>('');
  const [vendorTaxAddressInput, setVendorTaxAddressInput] = useState<string>('');
  const [taxInfoVendorId, setTaxInfoVendorId] = useState<string>('');

  // MFA self-service state
  const [mfaEnabled, setMfaEnabled] = useState<boolean>(false);
  const [mfaEnrollSecret, setMfaEnrollSecret] = useState<string | null>(null);
  const [mfaEnrollUrl, setMfaEnrollUrl] = useState<string | null>(null);
  const [mfaCodeInput, setMfaCodeInput] = useState<string>('');

  // Login-time MFA challenge state
  const [mfaChallengeToken, setMfaChallengeToken] = useState<string | null>(null);
  const [loginMfaCode, setLoginMfaCode] = useState<string>('');

  // SSO login state
  const [ssoEmailInput, setSsoEmailInput] = useState<string>('');
  const [ssoLoginError, setSsoLoginError] = useState<string | null>(null);

  // Self-registration state
  const [showRegister, setShowRegister] = useState<boolean>(false);
  const [registerEntities, setRegisterEntities] = useState<Entity[]>([]);
  const [registerDepartments, setRegisterDepartments] = useState<Department[]>([]);
  const [regName, setRegName] = useState<string>('');
  const [regEmail, setRegEmail] = useState<string>('');
  const [regPassword, setRegPassword] = useState<string>('');
  const [regEntityId, setRegEntityId] = useState<string>('');
  const [regRoleId, setRegRoleId] = useState<string>('EMPLOYEE');
  const [regDepartmentId, setRegDepartmentId] = useState<string>('');
  const [registerMessage, setRegisterMessage] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);

  // Admin: pending user registrations awaiting approval
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [pendingApproveRole, setPendingApproveRole] = useState<Record<string, string>>({});
  const [pendingApproveDept, setPendingApproveDept] = useState<Record<string, string>>({});

  // Tab control
  const [activeTab, setActiveTab] = useState<'dashboard' | 'cards' | 'bills' | 'reimbursements' | 'transactions' | 'approvals' | 'accounting' | 'insights' | 'ops' | 'settings'>('dashboard');

  const [emailInput, setEmailInput] = useState<string>('employee@apex.com');
  const [passwordInput, setPasswordInput] = useState<string>('password123');

  // Hardening Phase 4 States
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [backgroundJobs, setBackgroundJobs] = useState<any[]>([]);

  // Form states - Cards
  const [reqType, setReqType] = useState<'VIRTUAL' | 'PHYSICAL'>('VIRTUAL');
  const [reqProgramId, setReqProgramId] = useState<string>('');
  const [reqLimit, setReqLimit] = useState<number>(1000);
  const [reqCurrency, setReqCurrency] = useState<string>('USD');
  const [createProgramName, setCreateProgramName] = useState<string>('');
  const [createProgramLimit, setCreateProgramLimit] = useState<number>(5000);
  const [createProgramType, setCreateProgramType] = useState<string>('MONTHLY');
  
  // Form states - Vendors
  const [newVendorName, setNewVendorName] = useState<string>('');
  const [newVendorEmail, setNewVendorEmail] = useState<string>('');
  const [newVendorBank, setNewVendorBank] = useState<string>('');
  const [vendorFuzzyWarning, setVendorFuzzyWarning] = useState<string | null>(null);

  // Form states - Bills
  const [billDeptId, setBillDeptId] = useState<string>('');
  const [billVendorId, setBillVendorId] = useState<string>('');
  const [billDueDate, setBillDueDate] = useState<string>('');
  const [billPaymentMethod, setBillPaymentMethod] = useState<'CARD' | 'BANK_TRANSFER'>('BANK_TRANSFER');
  const [billLineDesc, setBillLineDesc] = useState<string>('');
  const [billLineAmount, setBillLineAmount] = useState<number>(0);
  const [billLineItems, setBillLineItems] = useState<BillLineItem[]>([]);
  const [billGLAccountId, setBillGLAccountId] = useState<string>('');

  // Form states - Reimbursements
  const [reimbType, setReimbType] = useState<'OUT_OF_POCKET' | 'MILEAGE'>('OUT_OF_POCKET');
  const [reimbDeptId, setReimbDeptId] = useState<string>('');
  const [reimbLineDesc, setReimbLineDesc] = useState<string>('');
  const [reimbLineAmount, setReimbLineAmount] = useState<number>(0);
  const [reimbLineItems, setReimbLineItems] = useState<BillLineItem[]>([]);
  const [reimbGLAccountId, setReimbGLAccountId] = useState<string>('');
  
  // Mileage waypoint form
  const [mileagePurpose, setMileagePurpose] = useState<string>('');
  const [mileageMiles, setMileageMiles] = useState<number>(0);
  const [waypoints, setWaypoints] = useState<string[]>(['', '']);

  // Form states - Phase 3 GL Accounts
  const [newGLCode, setNewGLCode] = useState<string>('');
  const [newGLName, setNewGLName] = useState<string>('');
  const [newGLType, setNewGLType] = useState<string>('EXPENSE');

  // Form states - Phase 3 Mappings
  const [newMapType, setNewMapType] = useState<string>('MCC');
  const [newMapSource, setNewMapSource] = useState<string>('');
  const [newMapGLId, setNewMapGLId] = useState<string>('');

  // Form states - Phase 3 Budgets
  const [budgetDeptId, setBudgetDeptId] = useState<string>('');
  const [budgetCategory, setBudgetCategory] = useState<string>('');
  const [budgetPeriod, setBudgetPeriod] = useState<string>('2026-07');
  const [budgetAmount, setBudgetAmount] = useState<number>(10000);

  // Form states - Phase 3 Custom Fields
  const [newFieldName, setNewFieldName] = useState<string>('');
  const [newFieldType, setNewFieldType] = useState<string>('TEXT');
  const [newFieldOptions, setNewFieldOptions] = useState<string>('');
  const [newFieldRequired, setNewFieldRequired] = useState<boolean>(false);

  // Swipe simulation states
  const [swipeCardId, setSwipeCardId] = useState<string>('');
  const [swipeAmount, setSwipeAmount] = useState<number>(150);
  const [swipeMerchant, setSwipeMerchant] = useState<string>('AWS Cloud Services');
  const [swipeMcc, setSwipeMcc] = useState<string>('4816'); 
  const [swipeResult, setSwipeResult] = useState<{ status: string; decline_reason?: string } | null>(null);

  // General loader/alerts
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Sync error generator override
  const [syncForceError, setSyncForceError] = useState<boolean>(false);

  // Auto-refresh timer for background items
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (token && user) {
      interval = setInterval(() => {
        fetchTransactions();
        fetchMetrics();
        fetchApprovalsInbox();
        fetchBills();
        fetchReimbursements();
        fetchSyncQueue();
        fetchInsights();
        fetchTotalSavings();
        fetchBudgetsComparison();
        fetchNotifications();
        if (user.roles.includes('ADMIN') || user.roles.includes('BOOKKEEPER')) {
          fetchAdminKPIs();
          fetchAuditLogs();
          fetchBackgroundJobs();
          fetchOpsSummary();
        }
        if (user.roles.includes('ADMIN')) {
          fetchPendingUsers();
        }
      }, 5000);
    }
    return () => clearInterval(interval);
  }, [token, user, activeEntityId]);

  useEffect(() => {
    if (token) {
      fetchUser();
    }
  }, [token]);

  useEffect(() => {
    if (user) {
      fetchEntities();
      fetchDepartments();
      fetchSpendPrograms();
      fetchMetrics();
      fetchCards();
      fetchCardRequests();
      fetchTransactions();
      fetchApprovalsInbox();
      fetchBills();
      fetchVendors();
      fetchReimbursements();
      fetchGLAccounts();
      fetchGLMappings();
      fetchSyncQueue();
      fetchCustomFields();
      fetchInsights();
      fetchTotalSavings();
      fetchBudgetsComparison();
      fetchNotifications();
      fetchSupportedCurrencies();
      fetchDisputes();
      fetchScreenings();
      fetchReconciliationRuns();
      fetchNecReport();
      if (user.roles.includes('ADMIN') || user.roles.includes('BOOKKEEPER')) {
        fetchAdminKPIs();
        fetchAuditLogs();
        fetchBackgroundJobs();
        fetchOpsSummary();
      }
      if (user.roles.includes('ADMIN')) {
        fetchSsoConnections();
        fetchPendingUsers();
      }
    }
  }, [user, activeEntityId]);

  useEffect(() => {
    if (user) fetchNecReport();
  }, [necYear]);

  const fetchUser = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: getHeaders()
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      const data = await res.json();
      setUser(data);
      setMfaEnabled(!!data.mfa_enabled);
      if (!activeEntityId) {
        setActiveEntityId(data.active_entity_id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const getHeaders = () => {
    const headers: Record<string, string> = {
      'Authorization': `Bearer ${token}`
    };
    if (activeEntityId) {
      headers['X-Entity-Id'] = activeEntityId;
    }
    return headers;
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    setMetrics(null);
    setCards([]);
    setCardRequests([]);
    setTransactions([]);
    setApprovalSteps([]);
    setBills([]);
    setVendors([]);
    setReimbursements([]);
    setGlAccounts([]);
    setGlMappings([]);
    setSyncQueue([]);
    setCustomFields([]);
    setInsights([]);
    setTotalSavings(0);
    setBudgets([]);
    setAdminKPIs(null);
    setNotifications([]);
    setOpsSummary(null);
    setScreenings([]);
    setDisputes([]);
    setReconciliationRuns([]);
    setReconciliationDiscrepancies({});
    setNecReport([]);
    setSsoConnections([]);
    setMfaEnabled(false);
    setMfaEnrollSecret(null);
    setMfaEnrollUrl(null);
    setMfaChallengeToken(null);
    setPendingUsers([]);
    setShowRegister(false);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMessage(null);
    try {
      const formData = new URLSearchParams();
      formData.append('username', emailInput);
      formData.append('password', passwordInput);

      const res = await fetch(`${API_BASE}/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Invalid email or password');
      }

      const data = await res.json();
      if (data.mfa_required) {
        // Password check passed, but a second factor is required — the
        // access_token isn't issued yet, just a short-lived challenge token.
        setMfaChallengeToken(data.mfa_challenge_token);
        return;
      }
      localStorage.setItem('token', data.access_token);
      setToken(data.access_token);
    } catch (err: any) {
      setErrorMessage(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleMfaVerifyLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/mfa/verify-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ challenge_token: mfaChallengeToken, code: loginMfaCode })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Invalid authentication code');
      }
      const data = await res.json();
      localStorage.setItem('token', data.access_token);
      setToken(data.access_token);
      setMfaChallengeToken(null);
      setLoginMfaCode('');
    } catch (err: any) {
      setErrorMessage(err.message || 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSsoLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setSsoLoginError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/sso/login-url?email=${encodeURIComponent(ssoEmailInput)}`);
      if (!res.ok) {
        throw new Error('No SSO connection is configured for this email domain');
      }
      const data = await res.json();
      window.location.href = data.authorization_url;
    } catch (err: any) {
      setSsoLoginError(err.message || 'SSO login failed');
      setLoading(false);
    }
  };

  // Handles the IdP redirecting back with ?code=... after an SSO login —
  // exchanges it for a real access token, same as the QBO/Plaid OAuth flows.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (!code) return;

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sso/exchange`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code })
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'SSO sign-in failed');
        }
        const data = await res.json();
        localStorage.setItem('token', data.access_token);
        setToken(data.access_token);
      } catch (err: any) {
        setErrorMessage(err.message || 'SSO sign-in failed');
      } finally {
        window.history.replaceState({}, '', window.location.pathname);
      }
    })();
  }, []);

  const handleQuickLogin = (email: string) => {
    setEmailInput(email);
    setPasswordInput('password123');
  };

  // Pre-login (public) company/department lookups for the registration form
  const fetchRegisterEntities = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/entities`);
      if (res.ok) setRegisterEntities(await res.json());
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    if (showRegister) fetchRegisterEntities();
  }, [showRegister]);

  useEffect(() => {
    if (!regEntityId) {
      setRegisterDepartments([]);
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/entities/${regEntityId}/departments`);
        if (res.ok) setRegisterDepartments(await res.json());
      } catch (e) { console.error(e); }
    })();
  }, [regEntityId]);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegisterError(null);
    setRegisterMessage(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: regName,
          email: regEmail,
          password: regPassword,
          entity_id: regEntityId,
          requested_role_id: regRoleId,
          requested_department_id: regDepartmentId || null
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Registration failed');
      }
      setRegisterMessage(data.message || 'Registration submitted for admin approval.');
      setRegName('');
      setRegEmail('');
      setRegPassword('');
      setRegEntityId('');
      setRegDepartmentId('');
    } catch (err: any) {
      setRegisterError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  // --- Admin: pending user registrations ---
  const fetchPendingUsers = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/pending-users`, { headers: getHeaders() });
      if (res.ok) setPendingUsers(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleApproveUser = async (userId: string) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const pu = pendingUsers.find(p => p.id === userId);
      // Fall back to what the select is actually showing (the requested
      // role/department) when the admin approves without touching it —
      // otherwise a silent null would override the visible default.
      const roleId = pendingApproveRole[userId] ?? pu?.requested_role_id ?? 'EMPLOYEE';
      const departmentId = (pendingApproveDept[userId] ?? pu?.requested_department_id) || null;
      const res = await fetch(`${API_BASE}/api/auth/users/${userId}/approve`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_id: roleId, department_id: departmentId })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to approve user');
      }
      setSuccessMessage('User approved.');
      fetchPendingUsers();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleRejectUser = async (userId: string) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/users/${userId}/reject`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to reject user');
      }
      setSuccessMessage('User rejected.');
      fetchPendingUsers();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const fetchEntities = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/entities`, { headers: getHeaders() });
      const data = await res.json();
      setEntities(data);
    } catch (e) { console.error(e); }
  };

  const fetchDepartments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/departments`, { headers: getHeaders() });
      const data = await res.json();
      setDepartments(data);
      if (data.length > 0) {
        setBillDeptId(data[0].id);
        setReimbDeptId(data[0].id);
        setBudgetDeptId(data[0].id);
      }
    } catch (e) { console.error(e); }
  };

  const fetchSpendPrograms = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/cards/spend-programs`, { headers: getHeaders() });
      const data = await res.json();
      setSpendPrograms(data);
      if (data.length > 0) {
        setReqProgramId(data[0].id);
      }
    } catch (e) { console.error(e); }
  };

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reporting/dashboard`, { headers: getHeaders() });
      const data = await res.json();
      setMetrics(data);
    } catch (e) { console.error(e); }
  };

  const fetchCards = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/cards`, { headers: getHeaders() });
      const data = await res.json();
      setCards(data);
      if (data.length > 0) {
        setSwipeCardId(data[0].id);
      }
    } catch (e) { console.error(e); }
  };

  const fetchCardRequests = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/cards/requests`, { headers: getHeaders() });
      const data = await res.json();
      setCardRequests(data);
    } catch (e) { console.error(e); }
  };

  const fetchTransactions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/transactions`, { headers: getHeaders() });
      const data = await res.json();
      setTransactions(data);
    } catch (e) { console.error(e); }
  };

  const fetchApprovalsInbox = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/approvals/inbox`, { headers: getHeaders() });
      const data = await res.json();
      setApprovalSteps(data);
    } catch (e) { console.error(e); }
  };

  const fetchBills = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/bills`, { headers: getHeaders() });
      const data = await res.json();
      setBills(data);
    } catch (e) { console.error(e); }
  };

  const fetchVendors = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/bills/vendors`, { headers: getHeaders() });
      const data = await res.json();
      setVendors(data);
      if (data.length > 0) {
        setBillVendorId(data[0].id);
      }
    } catch (e) { console.error(e); }
  };

  const fetchReimbursements = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reimbursements`, { headers: getHeaders() });
      const data = await res.json();
      setReimbursements(data);
    } catch (e) { console.error(e); }
  };

  // Phase 3 Fetch calls
  const fetchGLAccounts = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/accounting/gl-accounts`, { headers: getHeaders() });
      const data = await res.json();
      setGlAccounts(data);
      if (data.length > 0) {
        setBillGLAccountId(data[0].id);
        setReimbGLAccountId(data[0].id);
        setNewMapGLId(data[0].id);
      }
    } catch (e) { console.error(e); }
  };

  const fetchGLMappings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/accounting/mappings`, { headers: getHeaders() });
      const data = await res.json();
      setGlMappings(data);
    } catch (e) { console.error(e); }
  };

  const fetchSyncQueue = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/accounting/sync/queue`, { headers: getHeaders() });
      const data = await res.json();
      setSyncQueue(data);
    } catch (e) { console.error(e); }
  };

  const fetchCustomFields = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/accounting/custom-fields`, { headers: getHeaders() });
      const data = await res.json();
      setCustomFields(data);
    } catch (e) { console.error(e); }
  };

  const fetchInsights = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/insights`, { headers: getHeaders() });
      const data = await res.json();
      setInsights(data);
    } catch (e) { console.error(e); }
  };

  const fetchTotalSavings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/insights/savings-summary`, { headers: getHeaders() });
      const data = await res.json();
      setTotalSavings(data.total_savings);
    } catch (e) { console.error(e); }
  };

  const fetchBudgetsComparison = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reporting/budgets`, { headers: getHeaders() });
      const data = await res.json();
      setBudgets(data);
    } catch (e) { console.error(e); }
  };

  const fetchAdminKPIs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reporting/admin-kpis`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        setAdminKPIs(data);
      }
    } catch (e) { console.error(e); }
  };

  const fetchAuditLogs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reporting/audit-logs`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        setAuditLogs(data);
      }
    } catch (e) { console.error(e); }
  };

  const fetchBackgroundJobs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reporting/background-jobs`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        setBackgroundJobs(data);
      }
    } catch (e) { console.error(e); }
  };

  // --- Notifications ---
  const fetchNotifications = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications`, { headers: getHeaders() });
      if (res.ok) setNotifications(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleMarkNotificationRead = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications/${id}/read`, { method: 'POST', headers: getHeaders() });
      if (res.ok) fetchNotifications();
    } catch (e) { console.error(e); }
  };

  const handleMarkAllNotificationsRead = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications/read-all`, { method: 'POST', headers: getHeaders() });
      if (res.ok) fetchNotifications();
    } catch (e) { console.error(e); }
  };

  // --- Ops Center ---
  const fetchOpsSummary = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ops/summary`, { headers: getHeaders() });
      if (res.ok) setOpsSummary(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchScreenings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/screening`, { headers: getHeaders() });
      if (res.ok) setScreenings(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchDisputes = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/disputes`, { headers: getHeaders() });
      if (res.ok) setDisputes(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleSubmitDisputeEvidence = async (id: string) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/disputes/${id}/evidence`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ evidence: disputeEvidenceInput[id] || '' })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to submit evidence');
      }
      setSuccessMessage('Evidence submitted, dispute moved to review.');
      fetchDisputes();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const fetchReconciliationRuns = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reconciliation/runs`, { headers: getHeaders() });
      if (res.ok) setReconciliationRuns(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchReconciliationDiscrepancies = async (runId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/reconciliation/runs/${runId}/discrepancies`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        setReconciliationDiscrepancies(prev => ({ ...prev, [runId]: data }));
      }
    } catch (e) { console.error(e); }
  };

  const handleRunReconciliation = async () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/reconciliation/run`, { method: 'POST', headers: getHeaders() });
      if (!res.ok) throw new Error('Reconciliation run failed');
      const data = await res.json();
      setSuccessMessage(`Reconciliation complete: ${data.checked_count} checked, ${data.discrepancy_count} discrepancy(ies) found.`);
      fetchReconciliationRuns();
      fetchOpsSummary();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleResolveDiscrepancy = async (runId: string, discrepancyId: string, action: 'RETRY' | 'ACKNOWLEDGE') => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/ops/reconciliation-discrepancies/${discrepancyId}/resolve`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to resolve discrepancy');
      }
      setSuccessMessage(`Discrepancy ${action === 'RETRY' ? 'reset for retry' : 'acknowledged'}.`);
      fetchReconciliationDiscrepancies(runId);
      fetchOpsSummary();
      fetchBills();
      fetchReimbursements();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const fetchNecReport = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tax-reporting/1099-nec/${necYear}`, { headers: getHeaders() });
      if (res.ok) setNecReport(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleDownloadNecCsv = () => {
    window.open(`${API_BASE}/api/tax-reporting/1099-nec/${necYear}/export.csv`, '_blank');
  };

  const handleDownloadTransactionsCsv = () => {
    window.open(`${API_BASE}/api/transactions/export.csv`, '_blank');
  };

  const handleUpdateVendorTaxInfo = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/bills/vendors/${taxInfoVendorId}/tax-info`, {
        method: 'PATCH',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ tax_id: vendorTaxIdInput, tax_address: vendorTaxAddressInput })
      });
      if (!res.ok) throw new Error('Failed to save vendor tax info');
      setSuccessMessage('Vendor tax info saved.');
      setVendorTaxIdInput('');
      setVendorTaxAddressInput('');
      fetchNecReport();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  // --- SSO ---
  const fetchSsoConnections = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sso/connections`, { headers: getHeaders() });
      if (res.ok) setSsoConnections(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleCreateSsoConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/sso/connections`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: ssoDomainInput })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to create SSO connection');
      }
      setSuccessMessage('SSO connection created.');
      setSsoDomainInput('');
      fetchSsoConnections();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  // --- FX ---
  const fetchSupportedCurrencies = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/fx/currencies`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        setSupportedCurrencies(data.currencies);
      }
    } catch (e) { console.error(e); }
  };

  // --- MFA self-service ---
  const handleMfaEnroll = async () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/mfa/enroll`, { method: 'POST', headers: getHeaders() });
      if (!res.ok) throw new Error('Failed to start MFA enrollment');
      const data = await res.json();
      setMfaEnrollSecret(data.secret);
      setMfaEnrollUrl(data.otpauth_url);
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleMfaConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/mfa/confirm`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: mfaCodeInput })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Invalid code');
      }
      setSuccessMessage('MFA enabled on your account.');
      setMfaEnabled(true);
      setMfaEnrollSecret(null);
      setMfaEnrollUrl(null);
      setMfaCodeInput('');
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleMfaDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/mfa/disable`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: mfaCodeInput })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Invalid code');
      }
      setSuccessMessage('MFA disabled on your account.');
      setMfaEnabled(false);
      setMfaCodeInput('');
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/reporting/background-jobs/${jobId}/retry`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchBackgroundJobs();
        fetchSyncQueue();
      }
    } catch (e) { console.error(e); }
  };

  const handleUpdateEntityStatus = async (status: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/entities/${activeEntityId}/status?status=${status}`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchEntities();
      }
    } catch (e) { console.error(e); }
  };

  const handleSeed = async () => {
    setLoading(true);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/seed`, {
        method: 'POST'
      });
      if (res.ok) {
        setSuccessMessage('Demo environment seeded successfully! Log in to test.');
      } else {
        setErrorMessage('Seeding failed');
      }
    } catch (e) {
      setErrorMessage('Seeding failed');
    } finally {
      setLoading(false);
    }
  };

  // Phase 3 Handlers
  const handleCreateGLAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/accounting/gl-accounts`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: newGLCode,
          name: newGLName,
          type: newGLType
        })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create GL Account');
      }
      setSuccessMessage(`GL Account ${newGLCode} - ${newGLName} added successfully.`);
      setNewGLCode('');
      setNewGLName('');
      fetchGLAccounts();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleCreateGLMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/accounting/mappings`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mapping_type: newMapType,
          source_value: newMapSource,
          gl_account_id: newMapGLId
        })
      });
      if (!res.ok) throw new Error('Failed to create mapping rule');
      setSuccessMessage('Mapping rule updated!');
      setNewMapSource('');
      fetchGLMappings();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleCreateCustomField = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    
    let options: string[] | null = null;
    if (newFieldType === 'SELECT' && newFieldOptions) {
      options = newFieldOptions.split(',').map(o => o.trim());
    }

    try {
      const res = await fetch(`${API_BASE}/api/accounting/custom-fields`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newFieldName,
          field_type: newFieldType,
          select_options: options,
          is_required: newFieldRequired
        })
      });
      if (!res.ok) throw new Error('Failed to create custom field');
      setSuccessMessage(`Custom field "${newFieldName}" created.`);
      setNewFieldName('');
      setNewFieldOptions('');
      fetchCustomFields();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleProcessSync = async () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/accounting/sync/process?force_error=${syncForceError}`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) throw new Error('ERP sync processing encountered an error');
      const data = await res.json();
      setSuccessMessage(`ERP Sync completed. Synced: ${data.synced}, Errors: ${data.errors}`);
      fetchSyncQueue();
      if (user?.roles.includes('ADMIN') || user?.roles.includes('BOOKKEEPER')) {
        fetchAdminKPIs();
      }
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleRetrySync = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/accounting/sync/queue/${id}/retry`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchSyncQueue();
      }
    } catch (e) { console.error(e); }
  };

  const handleCreateBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/reporting/budgets`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          department_id: budgetDeptId || null,
          category: budgetCategory || null,
          period: budgetPeriod,
          amount: budgetAmount
        })
      });
      if (!res.ok) throw new Error('Failed to configure budget');
      setSuccessMessage('Budget allocation recorded!');
      setBudgetCategory('');
      fetchBudgetsComparison();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleTriggerDetect = async () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/insights/detect`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) throw new Error('Failed to run anomaly checks');
      const data = await res.json();
      setSuccessMessage(`spend audit checks completed. Newly flagged anomalies: ${data.insights_created}`);
      fetchInsights();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleConfirmInsight = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/insights/${id}/confirm`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchInsights();
        fetchTotalSavings();
        if (user?.roles.includes('ADMIN') || user?.roles.includes('BOOKKEEPER')) {
          fetchAdminKPIs();
        }
      }
    } catch (e) { console.error(e); }
  };

  const handleDismissInsight = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/insights/${id}/dismiss`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchInsights();
      }
    } catch (e) { console.error(e); }
  };

  // Phase 1/2 Handlers
  const handleRequestCard = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/cards/request`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spend_program_id: reqProgramId,
          type: reqType,
          limit_amount: reqLimit,
          currency: reqCurrency
        })
      });
      if (!res.ok) throw new Error('Failed to request card');
      setSuccessMessage('Card request submitted for manager approval workflow!');
      fetchCardRequests();
      fetchApprovalsInbox();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleCreateSpendProgram = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/cards/spend-programs`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createProgramName,
          limit_amount: createProgramLimit,
          limit_type: createProgramType
        })
      });
      if (!res.ok) throw new Error('Failed to create spend program');
      setSuccessMessage(`Spend Program "${createProgramName}" created!`);
      setCreateProgramName('');
      fetchSpendPrograms();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleFreeze = async (cardId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/cards/${cardId}/freeze`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchCards();
      }
    } catch (e) { console.error(e); }
  };

  const handleUnfreeze = async (cardId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/cards/${cardId}/unfreeze`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchCards();
      }
    } catch (e) { console.error(e); }
  };

  const handleDecideApproval = async (stepId: string, decision: 'APPROVED' | 'REJECTED') => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/approvals/steps/${stepId}/decide`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, comment: `${decision} via Approvals Inbox` })
      });
      if (!res.ok) throw new Error('Failed to decide approval');
      setSuccessMessage(`Step successfully ${decision.toLowerCase()}!`);
      fetchApprovalsInbox();
      fetchCardRequests();
      fetchCards();
      fetchBills();
      fetchReimbursements();
    } catch (e: any) {
      setErrorMessage(e.message);
    }
  };

  const handleCreateVendor = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    setVendorFuzzyWarning(null);
    try {
      const res = await fetch(`${API_BASE}/api/bills/vendors`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newVendorName,
          email: newVendorEmail,
          masked_bank_account: newVendorBank
        })
      });
      if (!res.ok) throw new Error('Failed to create vendor');
      const data = await res.json();
      
      if (existingVendorMatched(data.name, newVendorName)) {
        setVendorFuzzyWarning(`Matched existing vendor "${data.name}" to prevent duplicate creation.`);
      } else {
        setSuccessMessage(`Vendor "${newVendorName}" created successfully!`);
      }
      
      setNewVendorName('');
      setNewVendorEmail('');
      setNewVendorBank('');
      fetchVendors();
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  const handleAddBillLine = () => {
    if (!billLineDesc || billLineAmount <= 0) return;
    setBillLineItems([...billLineItems, { description: billLineDesc, amount: billLineAmount, gl_account_id: billGLAccountId || undefined }]);
    setBillLineDesc('');
    setBillLineAmount(0);
  };

  const handleCreateBill = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    if (billLineItems.length === 0) {
      setErrorMessage('Add at least one line item first');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/bills`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          department_id: billDeptId,
          vendor_id: billVendorId,
          due_date: billDueDate,
          payment_method: billPaymentMethod,
          line_items: billLineItems
        })
      });
      if (!res.ok) throw new Error('Failed to create bill');
      setSuccessMessage('Invoice created as DRAFT. Submit for approval when ready.');
      setBillLineItems([]);
      setBillDueDate('');
      fetchBills();
    } catch (e: any) {
      setErrorMessage(e.message);
    }
  };

  const handleSubmitBill = async (billId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/bills/${billId}/submit`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchBills();
        fetchApprovalsInbox();
      }
    } catch (e) { console.error(e); }
  };

  const handlePayBill = async (billId: string) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/bills/${billId}/pay`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Payment failed');
      }
      setSuccessMessage('Bill payment processed successfully through payment rail.');
      fetchBills();
      fetchTransactions();
      fetchMetrics();
      fetchSyncQueue();
    } catch (e: any) {
      setErrorMessage(e.message);
    }
  };

  const handleVoidBill = async (billId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/bills/${billId}/void`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchBills();
        fetchTransactions();
        fetchMetrics();
        fetchSyncQueue();
      }
    } catch (e) { console.error(e); }
  };

  const handleAddReimbLine = () => {
    if (!reimbLineDesc || reimbLineAmount <= 0) return;
    setReimbLineItems([...reimbLineItems, { description: reimbLineDesc, amount: reimbLineAmount, gl_account_id: reimbGLAccountId || undefined }]);
    setReimbLineDesc('');
    setReimbLineAmount(0);
  };

  const handleAddWaypoint = () => {
    setWaypoints([...waypoints, '']);
  };

  const handleWaypointChange = (idx: number, val: string) => {
    const updated = [...waypoints];
    updated[idx] = val;
    setWaypoints(updated);
  };

  const handleSubmitReimbursement = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    const body: Record<string, any> = {
      type: reimbType,
      department_id: reimbDeptId
    };

    if (reimbType === 'OUT_OF_POCKET') {
      if (reimbLineItems.length === 0) {
        setErrorMessage('Add at least one line item first');
        return;
      }
      body.line_items = reimbLineItems;
    } else {
      if (!mileagePurpose || mileageMiles <= 0) {
        setErrorMessage('Enter trip purpose and valid mileage');
        return;
      }
      body.trip = {
        purpose: mileagePurpose,
        total_miles: mileageMiles,
        waypoints: waypoints.map((address, idx) => ({ sequence: idx + 1, address }))
      };
    }

    try {
      const res = await fetch(`${API_BASE}/api/reimbursements`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!res.ok) throw new Error('Failed to submit reimbursement claim');
      setSuccessMessage('Reimbursement claim submitted for manager approvals!');
      setReimbLineItems([]);
      setMileagePurpose('');
      setMileageMiles(0);
      setWaypoints(['', '']);
      fetchReimbursements();
      fetchApprovalsInbox();
    } catch (e: any) {
      setErrorMessage(e.message);
    }
  };

  const handlePayoutReimbursement = async (reimbId: string) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/reimbursements/${reimbId}/payout`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) throw new Error('Failed to pay reimbursement');
      setSuccessMessage('Reimbursement paid via ACH bank transfer.');
      fetchReimbursements();
      fetchSyncQueue();
    } catch (e: any) {
      setErrorMessage(e.message);
    }
  };

  const handleSwipeSimulation = async (e: React.FormEvent) => {
    e.preventDefault();
    setSwipeResult(null);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/transactions/simulate-swipe`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          card_id: swipeCardId,
          amount: swipeAmount,
          merchant_name: swipeMerchant,
          merchant_mcc: swipeMcc
        })
      });
      const data = await res.json();
      setSwipeResult(data);
      fetchTransactions();
      fetchMetrics();
    } catch (err: any) {
      setErrorMessage('Swipe simulation failed');
    }
  };

  const existingVendorMatched = (realName: string, inputName: string) => {
    return realName.toLowerCase().replace(/\s/g, '') !== inputName.toLowerCase().replace(/\s/g, '');
  };

  // If not logged in, show Auth form
  if (!token || !user) {
    return (
      <div className="login-container">
        <div className="login-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '2rem', justifyContent: 'center' }}>
            <CreditCard size={32} color="var(--color-primary)" />
            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, fontFamily: 'Outfit', letterSpacing: '0.05em' }}>APEX PORTAL</h1>
          </div>
          
          {showRegister ? (
            <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
              {registerError && (
                <div style={{ color: 'var(--color-danger)', fontSize: '0.9rem', display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                  <ShieldAlert size={16} />
                  <span>{registerError}</span>
                </div>
              )}
              {registerMessage && (
                <div style={{ color: 'var(--color-success)', fontSize: '0.85rem' }}>{registerMessage}</div>
              )}
              <div>
                <label>Full Name</label>
                <input type="text" value={regName} onChange={(e) => setRegName(e.target.value)} required />
              </div>
              <div>
                <label>Work Email</label>
                <input type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} required />
              </div>
              <div>
                <label>Password</label>
                <input type="password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} required minLength={8} />
              </div>
              <div>
                <label>Company</label>
                <select value={regEntityId} onChange={(e) => setRegEntityId(e.target.value)} required>
                  <option value="">Select your company...</option>
                  {registerEntities.map(ent => (
                    <option key={ent.id} value={ent.id}>{ent.name}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={{ flex: 1 }}>
                  <label>Requested Role</label>
                  <select value={regRoleId} onChange={(e) => setRegRoleId(e.target.value)}>
                    {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label>Department (optional)</label>
                  <select value={regDepartmentId} onChange={(e) => setRegDepartmentId(e.target.value)}>
                    <option value="">None</option>
                    {registerDepartments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </div>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Your account will be created as <strong>pending</strong> — an admin at your company must approve it before you can sign in.
              </p>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Submit Registration Request
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ width: '100%' }}
                onClick={() => { setShowRegister(false); setRegisterError(null); setRegisterMessage(null); }}
              >
                Back to Sign In
              </button>
            </form>
          ) : mfaChallengeToken ? (
            <form onSubmit={handleMfaVerifyLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {errorMessage && (
                <div style={{ color: 'var(--color-danger)', fontSize: '0.9rem', display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                  <ShieldAlert size={16} />
                  <span>{errorMessage}</span>
                </div>
              )}
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Enter the 6-digit code from your authenticator app.
              </p>
              <div>
                <label>Authentication Code</label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoFocus
                  value={loginMfaCode}
                  onChange={(e) => setLoginMfaCode(e.target.value)}
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Verify &amp; Sign In
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ width: '100%' }}
                onClick={() => { setMfaChallengeToken(null); setLoginMfaCode(''); setErrorMessage(null); }}
              >
                Back
              </button>
            </form>
          ) : (
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {errorMessage && (
              <div style={{ color: 'var(--color-danger)', fontSize: '0.9rem', display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                <ShieldAlert size={16} />
                <span>{errorMessage}</span>
              </div>
            )}

            <div>
              <label>Corporate Email</label>
              <input
                type="email"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                required
              />
            </div>

            <div>
              <label>Password</label>
              <input
                type="password"
                value={passwordInput}
                onChange={(e) => setPasswordInput(e.target.value)}
                required
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '0.5rem' }}>
              Sign In
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ width: '100%', fontSize: '0.85rem' }}
              onClick={() => { setShowRegister(true); setErrorMessage(null); }}
            >
              Create an account
            </button>
          </form>
          )}

          {!mfaChallengeToken && !showRegister && (
          <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
            <form onSubmit={handleSsoLogin} style={{ display: 'flex', gap: '0.5rem' }}>
              <input
                type="email"
                placeholder="you@company.com"
                value={ssoEmailInput}
                onChange={(e) => setSsoEmailInput(e.target.value)}
                style={{ flex: 1 }}
                required
              />
              <button type="submit" className="btn btn-secondary" style={{ whiteSpace: 'nowrap' }}>
                Sign in with SSO
              </button>
            </form>
            {ssoLoginError && (
              <div style={{ color: 'var(--color-danger)', fontSize: '0.8rem', marginTop: '0.5rem' }}>{ssoLoginError}</div>
            )}
          </div>
          )}

          {!mfaChallengeToken && !showRegister && (
          <div style={{ marginTop: '2rem', borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem' }}>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem', textAlign: 'center' }}>
              Quick Switch Role Profiles
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '0.5rem' }} onClick={() => handleQuickLogin('admin@apex.com')}>
                Alice Admin (Apex Parent)
              </button>
              <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '0.5rem' }} onClick={() => handleQuickLogin('manager@apex.com')}>
                Bob Manager (Apex Engineering)
              </button>
              <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '0.5rem' }} onClick={() => handleQuickLogin('employee@apex.com')}>
                Charlie Employee (Apex Parent + Child)
              </button>
              <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '0.5rem' }} onClick={() => handleQuickLogin('bookkeeper@apex.com')}>
                Diane Bookkeeper (Entity Scope Audit)
              </button>
            </div>

            <div style={{ borderTop: '1px solid var(--border-color)', margin: '1.5rem 0', paddingTop: '1rem' }} />

            <button className="btn btn-primary" onClick={handleSeed} style={{ width: '100%' }}>
              <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
              Seed Database with Demo Data
            </button>
          </div>
          )}
        </div>
      </div>
    );
  }

  const activeEntity = entities.find(e => e.id === activeEntityId);

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <div style={{ width: '260px', borderRight: '1px solid var(--border-color)', background: '#0e1014', padding: '1.5rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '2.5rem' }}>
            <CreditCard size={28} color="var(--color-primary)" />
            <span style={{ fontFamily: 'Outfit', fontWeight: 800, fontSize: '1.25rem', letterSpacing: '0.05em' }}>APEX</span>
          </div>

          <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <button 
              className={`btn ${activeTab === 'dashboard' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('dashboard')}
            >
              <TrendingUp size={18} />
              <span>Dashboard</span>
            </button>

            <button 
              className={`btn ${activeTab === 'cards' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('cards')}
            >
              <CreditCard size={18} />
              <span>Cards</span>
            </button>

            <button 
              className={`btn ${activeTab === 'bills' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('bills')}
            >
              <FileText size={18} />
              <span>Bill Pay</span>
            </button>

            <button 
              className={`btn ${activeTab === 'reimbursements' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('reimbursements')}
            >
              <Receipt size={18} />
              <span>Reimburse</span>
            </button>

            <button 
              className={`btn ${activeTab === 'accounting' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('accounting')}
            >
              <Database size={18} />
              <span>Accounting</span>
            </button>

            <button 
              className={`btn ${activeTab === 'insights' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%', position: 'relative' }}
              onClick={() => setActiveTab('insights')}
            >
              <Sliders size={18} />
              <span>Insights</span>
              {insights.filter(i => i.status === 'OPEN').length > 0 && (
                <span className="badge badge-danger" style={{ position: 'absolute', right: '12px', fontSize: '0.7rem' }}>
                  {insights.filter(i => i.status === 'OPEN').length}
                </span>
              )}
            </button>

            <button 
              className={`btn ${activeTab === 'transactions' ? 'btn-primary' : 'btn-secondary'}`} 
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('transactions')}
            >
              <Layers size={18} />
              <span>Card Swipe</span>
            </button>

            {(user.roles.includes('MANAGER') || user.roles.includes('ADMIN')) && (
              <button 
                className={`btn ${activeTab === 'approvals' ? 'btn-primary' : 'btn-secondary'}`} 
                style={{ justifyContent: 'flex-start', width: '100%', position: 'relative' }}
                onClick={() => setActiveTab('approvals')}
              >
                <CheckSquare size={18} />
                <span>Approvals</span>
                {approvalSteps.length > 0 && (
                  <span className="badge badge-warning" style={{ position: 'absolute', right: '12px', fontSize: '0.7rem' }}>
                    {approvalSteps.length}
                  </span>
                )}
              </button>
            )}

            {(user.roles.includes('ADMIN') || user.roles.includes('BOOKKEEPER')) && (
              <button
                className={`btn ${activeTab === 'ops' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ justifyContent: 'flex-start', width: '100%', position: 'relative' }}
                onClick={() => setActiveTab('ops')}
              >
                <Shield size={18} />
                <span>Ops Center</span>
                {(opsSummary && opsSummary.open_disputes + opsSummary.open_reconciliation_discrepancies + pendingUsers.length > 0) && (
                  <span className="badge badge-danger" style={{ position: 'absolute', right: '12px', fontSize: '0.7rem' }}>
                    {opsSummary.open_disputes + opsSummary.open_reconciliation_discrepancies + pendingUsers.length}
                  </span>
                )}
              </button>
            )}

            <button
              className={`btn ${activeTab === 'settings' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', width: '100%' }}
              onClick={() => setActiveTab('settings')}
            >
              <Settings size={18} />
              <span>Settings</span>
            </button>
          </nav>
        </div>

        {/* Current user & logout */}
        {user && (
          <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem' }}>
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>{user.name}</p>
                <button
                  className="btn btn-secondary"
                  style={{ position: 'relative', padding: '0.4rem' }}
                  onClick={() => setShowNotifications(v => !v)}
                  title="Notifications"
                >
                  <Bell size={16} />
                  {notifications.filter(n => !n.read).length > 0 && (
                    <span className="badge badge-danger" style={{ position: 'absolute', top: '-6px', right: '-6px', fontSize: '0.6rem' }}>
                      {notifications.filter(n => !n.read).length}
                    </span>
                  )}
                </button>
              </div>
              {showNotifications && (
                <div style={{ maxHeight: '260px', overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: '8px', margin: '0.5rem 0', padding: '0.5rem' }}>
                  {notifications.length === 0 && (
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>No notifications</p>
                  )}
                  {notifications.length > 0 && (
                    <button className="btn btn-secondary" style={{ width: '100%', fontSize: '0.75rem', marginBottom: '0.5rem' }} onClick={handleMarkAllNotificationsRead}>
                      Mark all read
                    </button>
                  )}
                  {notifications.map(n => (
                    <div
                      key={n.id}
                      onClick={() => !n.read && handleMarkNotificationRead(n.id)}
                      style={{ padding: '0.5rem', borderRadius: '6px', marginBottom: '0.25rem', background: n.read ? 'transparent' : 'rgba(59,130,246,0.1)', cursor: n.read ? 'default' : 'pointer' }}
                    >
                      <p style={{ fontSize: '0.75rem', fontWeight: n.read ? 400 : 600 }}>{n.title}</p>
                      <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{n.body}</p>
                    </div>
                  ))}
                </div>
              )}
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user.email}</p>
              <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                {user.roles.map(r => (
                  <span key={r} className="badge badge-info" style={{ fontSize: '0.65rem' }}>{r}</span>
                ))}
              </div>
            </div>

            {/* Entity Switcher */}
            {entities.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <label>Active Entity</label>
                <select value={activeEntityId} onChange={(e) => setActiveEntityId(e.target.value)} style={{ fontSize: '0.85rem', padding: '0.5rem' }}>
                  {entities.map(ent => (
                    <option key={ent.id} value={ent.id}>
                      {ent.name} {ent.parent_entity_id ? '(Sub)' : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <button className="btn btn-secondary" style={{ width: '100%', fontSize: '0.9rem' }} onClick={handleLogout}>
              Logout
            </button>
          </div>
        )}
      </div>

      {/* Main Panel */}
      <div className="main-content">
        {/* Banner if Onboarding Status is not APPROVED */}
        {activeEntity && activeEntity.onboarding_status !== 'APPROVED' && (
          <div style={{ background: 'var(--color-danger-glow)', border: '1px solid rgba(239,68,68,0.2)', padding: '1rem', borderRadius: '12px', color: 'var(--color-danger)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <AlertTriangle size={24} />
              <div>
                <h4 style={{ fontWeight: 700 }}>Entity status: {activeEntity.onboarding_status}</h4>
                <p style={{ fontSize: '0.9rem', color: 'rgba(239, 68, 68, 0.8)' }}>Onboarding functions are currently restricted.</p>
              </div>
            </div>
            {user?.roles.includes('ADMIN') && (
              <button className="btn btn-primary" onClick={() => handleUpdateEntityStatus('APPROVED')}>
                Approve KYB
              </button>
            )}
          </div>
        )}

        {activeEntity && activeEntity.onboarding_status === 'APPROVED' && (
          <div style={{ background: 'var(--color-success-glow)', border: '1px solid rgba(16,185,129,0.2)', padding: '1rem', borderRadius: '12px', color: 'var(--color-success)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <Check size={24} />
              <div>
                <h4 style={{ fontWeight: 700 }}>Entity is Onboarded & KYB Approved</h4>
                <p style={{ fontSize: '0.9rem', color: 'rgba(16,185,129,0.8)' }}>Mock partners and ledgers are operational.</p>
              </div>
            </div>
            {user?.roles.includes('ADMIN') && (
              <button className="btn btn-secondary" style={{ color: 'var(--color-danger)' }} onClick={() => handleUpdateEntityStatus('PENDING')}>
                Suspend KYB (Test Block)
              </button>
            )}
          </div>
        )}

        {errorMessage && (
          <div style={{ background: 'var(--color-danger-glow)', border: '1px solid rgba(239,68,68,0.2)', padding: '1rem', borderRadius: '12px', color: 'var(--color-danger)', marginBottom: '1.5rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <AlertTriangle size={20} />
            <span>{errorMessage}</span>
          </div>
        )}

        {successMessage && (
          <div style={{ background: 'var(--color-success-glow)', border: '1px solid rgba(16,185,129,0.2)', padding: '1rem', borderRadius: '12px', color: 'var(--color-success)', marginBottom: '1.5rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <Check size={20} />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Tab 1: Dashboard */}
        {activeTab === 'dashboard' && metrics && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            
            {/* Admin Operational KPIs widgets */}
            {(user.roles.includes('ADMIN') || user.roles.includes('BOOKKEEPER')) && adminKPIs && (
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Executive Operations Command</h3>
                <div className="grid-4">
                  <div className="card" style={{ background: 'linear-gradient(135deg, #101b22, #0d1e16)' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Auto-Audit Efficiency</p>
                    <h3 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-success)', marginTop: '0.5rem' }}>
                      {adminKPIs.operational_efficiency}%
                    </h3>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Auto-categorized & auto-coded</p>
                  </div>
                  
                  <div className="card" style={{ background: 'linear-gradient(135deg, #101b22, #1b1625)' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Money Saved</p>
                    <h3 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-primary)', marginTop: '0.5rem' }}>
                      ${adminKPIs.money_saved.toFixed(2)}
                    </h3>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Confirmed subscription leakage alerts</p>
                  </div>

                  <div className="card" style={{ background: 'linear-gradient(135deg, #101b22, #1e1313)' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Compliance Health Score</p>
                    <h3 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-danger)', marginTop: '0.5rem' }}>
                      {adminKPIs.compliance_score}%
                    </h3>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>GL coding completion + limits check</p>
                  </div>

                  <div className="card" style={{ background: 'linear-gradient(135deg, #101b22, #0e1e24)' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Avg. Turnaround Time</p>
                    <h3 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-info)', marginTop: '0.5rem' }}>
                      {adminKPIs.avg_approval_turnaround_hours}h
                    </h3>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Approval turnaround time</p>
                  </div>
                </div>
              </div>
            )}

            <div className="grid-3">
              <div className="card">
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Total Settled Card Spend</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <DollarSign size={24} color="var(--color-success)" />
                  <span style={{ fontSize: '2rem', fontWeight: 800, fontFamily: 'Outfit' }}>
                    {metrics.metrics.currency || 'USD'} {metrics.metrics.total_spend.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>

              <div className="card">
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Active Cards</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <CreditCard size={24} color="var(--color-primary)" />
                  <span style={{ fontSize: '2rem', fontWeight: 800, fontFamily: 'Outfit' }}>
                    {metrics.metrics.active_cards}
                  </span>
                </div>
              </div>

              <div className="card">
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Pending Card Requests</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <AlertTriangle size={24} color="var(--color-warning)" />
                  <span style={{ fontSize: '2rem', fontWeight: 800, fontFamily: 'Outfit' }}>
                    {metrics.metrics.pending_requests}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid-2">
              <div className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Spend Trend</h3>
                {metrics.spend_over_time.length === 0 ? (
                  <div style={{ height: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                    No settled transactions to chart. Swipe a card!
                  </div>
                ) : (
                  <div style={{ height: '220px', position: 'relative' }}>
                    <svg width="100%" height="100%" viewBox="0 0 500 200" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                      <defs>
                        <linearGradient id="chart-grad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.4" />
                          <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <line x1="0" y1="50" x2="500" y2="50" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
                      <line x1="0" y1="100" x2="500" y2="100" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
                      <line x1="0" y1="150" x2="500" y2="150" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
                      
                      {(() => {
                        const maxVal = Math.max(...metrics.spend_over_time.map(d => d.amount), 1);
                        const points = metrics.spend_over_time.map((d, i) => {
                          const x = (i / (metrics.spend_over_time.length - 1 || 1)) * 500;
                          const y = 200 - (d.amount / maxVal) * 160 - 20; 
                          return { x, y, ...d };
                        });

                        const dPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
                        const dArea = points.length > 0 ? `${dPath} L ${points[points.length - 1].x} 180 L ${points[0].x} 180 Z` : '';

                        return (
                          <>
                            {points.length > 1 && (
                              <>
                                <path d={dArea} fill="url(#chart-grad)" />
                                <path d={dPath} fill="none" stroke="var(--color-primary)" strokeWidth="2.5" />
                              </>
                            )}
                            {points.map((p, i) => (
                              <g key={i}>
                                <circle cx={p.x} cy={p.y} r="4" fill="var(--color-primary)" stroke="#0e1014" strokeWidth="1" />
                                <text x={p.x} y={195} fill="var(--text-secondary)" fontSize="8" textAnchor="middle">
                                  {p.date.split('-').slice(1).join('/')}
                                </text>
                              </g>
                            ))}
                          </>
                        );
                      })()}
                    </svg>
                  </div>
                )}
              </div>

              <div className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Spend by Department</h3>
                {metrics.spend_by_department.length === 0 ? (
                  <div style={{ display: 'flex', height: '220px', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                    No department spend recorded.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: '220px', overflowY: 'auto' }}>
                    {metrics.spend_by_department.map((dept, i) => {
                      const maxDeptVal = Math.max(...metrics.spend_by_department.map(d => d.amount), 1);
                      const percent = (dept.amount / maxDeptVal) * 100;
                      return (
                        <div key={i}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.35rem' }}>
                            <span style={{ fontWeight: 600 }}>{dept.department}</span>
                            <span style={{ color: 'var(--text-secondary)' }}>${dept.amount.toFixed(2)}</span>
                          </div>
                          <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ width: `${percent}%`, height: '100%', background: 'var(--color-primary)', borderRadius: '4px' }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Budget vs Actual allocation lists */}
            <div className="card animate-fade-in">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Departmental Budget-vs-Actual Audit</h3>
                {user.roles.includes('ADMIN') && (
                  <button className="btn btn-secondary" style={{ padding: '0.5rem 1rem', fontSize: '0.8rem' }} onClick={() => {
                    const el = document.getElementById('budget-builder-form');
                    if (el) el.scrollIntoView({ behavior: 'smooth' });
                  }}>
                    + Adjust Budget Allocation
                  </button>
                )}
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Department Scope</th>
                      <th style={{ padding: '0.75rem' }}>Spend Category</th>
                      <th style={{ padding: '0.75rem' }}>Period</th>
                      <th style={{ padding: '0.75rem' }}>Allocated Budget</th>
                      <th style={{ padding: '0.75rem' }}>Actual Ledger Spend</th>
                      <th style={{ padding: '0.75rem' }}>Remaining Threshold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {budgets.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                          No budgets allocated. Admin can define budgets below.
                        </td>
                      </tr>
                    ) : (
                      budgets.map(b => {
                        const budgeted = Number(b.budgeted_amount);
                        const actual = Number(b.actual_amount);
                        const remaining = Number(b.remaining_amount);
                        const usageRatio = budgeted > 0 ? (actual / budgeted) * 100 : 0;
                        const isOver = actual > budgeted;
                        return (
                          <tr key={b.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                            <td style={{ padding: '0.75rem', fontWeight: 600 }}>{b.department_name}</td>
                            <td style={{ padding: '0.75rem' }}>{b.category}</td>
                            <td style={{ padding: '0.75rem' }}>{b.period}</td>
                            <td style={{ padding: '0.75rem', fontWeight: 600 }}>${budgeted.toFixed(2)}</td>
                            <td style={{ padding: '0.75rem', color: isOver ? 'var(--color-danger)' : 'var(--color-success)', fontWeight: 700 }}>
                              ${actual.toFixed(2)}
                            </td>
                            <td style={{ padding: '0.75rem' }}>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                                <span style={{ color: isOver ? 'var(--color-danger)' : 'var(--text-secondary)', fontWeight: 600 }}>
                                  ${remaining.toFixed(2)}
                                </span>
                                <div style={{ width: '100px', height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
                                  <div style={{ width: `${Math.min(usageRatio, 100)}%`, height: '100%', background: isOver ? 'var(--color-danger)' : 'var(--color-primary)' }} />
                                </div>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Allocate budget builder form (Admin only) */}
            {user.roles.includes('ADMIN') && (
              <div id="budget-builder-form" className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem' }}>Configure Budget Allocation</h3>
                <form onSubmit={handleCreateBudget} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div style={{ flex: 1, minWidth: '180px' }}>
                    <label>Attributed Department</label>
                    <select value={budgetDeptId} onChange={(e) => setBudgetDeptId(e.target.value)}>
                      <option value="">All Departments</option>
                      {departments.map(d => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ flex: 1, minWidth: '180px' }}>
                    <label>Category (Optional)</label>
                    <input type="text" value={budgetCategory} onChange={(e) => setBudgetCategory(e.target.value)} placeholder="e.g. Software & SaaS, Food & Dining" />
                  </div>
                  <div style={{ width: '120px' }}>
                    <label>Period (YYYY-MM)</label>
                    <input type="text" value={budgetPeriod} onChange={(e) => setBudgetPeriod(e.target.value)} required placeholder="2026-07" />
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Amount (USD)</label>
                    <input type="number" value={budgetAmount} onChange={(e) => setBudgetAmount(Number(e.target.value))} required min="1" />
                  </div>
                  <button type="submit" className="btn btn-primary">Allocate Budget</button>
                </form>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Cards */}
        {activeTab === 'cards' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
            {user.roles.includes('ADMIN') && (
              <div className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Define Spend Program</h3>
                <form onSubmit={handleCreateSpendProgram} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div style={{ flex: 1, minWidth: '200px' }}>
                    <label>Program Name</label>
                    <input type="text" value={createProgramName} onChange={(e) => setCreateProgramName(e.target.value)} required placeholder="e.g. Travel Stipend, SaaS tools" />
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Limit (USD)</label>
                    <input type="number" value={createProgramLimit} onChange={(e) => setCreateProgramLimit(Number(e.target.value))} required min="1" />
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Limit Type</label>
                    <select value={createProgramType} onChange={(e) => setCreateProgramType(e.target.value)}>
                      <option value="DAILY">DAILY</option>
                      <option value="MONTHLY">MONTHLY</option>
                      <option value="YEARLY">YEARLY</option>
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary">Create Program</button>
                </form>
              </div>
            )}

            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Request Corporate Card</h3>
              {spendPrograms.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>No spend programs defined.</p>
              ) : (
                <form onSubmit={handleRequestCard} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div style={{ flex: 1, minWidth: '200px' }}>
                    <label>Spend Program</label>
                    <select value={reqProgramId} onChange={(e) => setReqProgramId(e.target.value)}>
                      {spendPrograms.map(p => (
                        <option key={p.id} value={p.id}>{p.name} (Max Limit: ${p.limit_amount})</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Card Type</label>
                    <select value={reqType} onChange={(e) => setReqType(e.target.value as any)}>
                      <option value="VIRTUAL">VIRTUAL</option>
                      <option value="PHYSICAL">PHYSICAL</option>
                    </select>
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Requested Limit</label>
                    <input type="number" value={reqLimit} onChange={(e) => setReqLimit(Number(e.target.value))} required min="1" />
                  </div>
                  <div style={{ width: '120px' }}>
                    <label>Currency</label>
                    <select value={reqCurrency} onChange={(e) => setReqCurrency(e.target.value)}>
                      {supportedCurrencies.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary">Submit Card Request</button>
                </form>
              )}
            </div>

            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '1.25rem' }}>Issued Active Cards</h3>
              {cards.length === 0 ? (
                <div className="card" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No active cards issued.
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem' }}>
                  {cards.map(card => (
                    <div key={card.id} className="card card-neon" style={{ position: 'relative', overflow: 'hidden' }}>
                      <div style={{ position: 'absolute', top: '1rem', right: '1rem' }}>
                        <span className={`badge ${card.status === 'ACTIVE' ? 'badge-success' : 'badge-danger'}`}>
                          {card.status}
                        </span>
                      </div>
                      
                      <div style={{ marginBottom: '2rem' }}>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                          {card.spend_program_name} Program
                        </p>
                        <h4 style={{ fontSize: '1.25rem', fontWeight: 700, fontFamily: 'monospace', marginTop: '0.5rem', letterSpacing: '0.15em' }}>
                          {card.masked_pan}
                        </h4>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                        <div>
                          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>CARDHOLDER</p>
                          <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>{card.owner_name}</p>
                          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Dept: {card.department_name}</p>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>LIMIT</p>
                          <p style={{ fontWeight: 700, fontSize: '1.1rem' }}>{card.currency} {card.limit_amount.toLocaleString()}</p>
                        </div>
                      </div>

                      <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
                        {card.status === 'ACTIVE' ? (
                          <button className="btn btn-secondary" style={{ width: '100%', display: 'flex', gap: '0.5rem', justifyContent: 'center' }} onClick={() => handleFreeze(card.id)}>
                            <Lock size={16} />
                            <span>Freeze Card</span>
                          </button>
                        ) : (
                          <button className="btn btn-primary" style={{ width: '100%', display: 'flex', gap: '0.5rem', justifyContent: 'center' }} onClick={() => handleUnfreeze(card.id)}>
                            <Unlock size={16} />
                            <span>Activate Card</span>
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Card Requests Queue</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Requester</th>
                      <th style={{ padding: '0.75rem' }}>Department</th>
                      <th style={{ padding: '0.75rem' }}>Program</th>
                      <th style={{ padding: '0.75rem' }}>Limit</th>
                      <th style={{ padding: '0.75rem' }}>Type</th>
                      <th style={{ padding: '0.75rem' }}>Status</th>
                      <th style={{ padding: '0.75rem' }}>Created At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cardRequests.map(req => (
                      <tr key={req.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                        <td style={{ padding: '0.75rem', fontWeight: 600 }}>{req.requester_name}</td>
                        <td style={{ padding: '0.75rem' }}>{req.department_name}</td>
                        <td style={{ padding: '0.75rem' }}>{req.spend_program_name}</td>
                        <td style={{ padding: '0.75rem', fontWeight: 700 }}>{req.currency} {req.limit_amount.toLocaleString()}</td>
                        <td style={{ padding: '0.75rem' }}>{req.type}</td>
                        <td style={{ padding: '0.75rem' }}>
                          <span className={`badge ${req.status === 'APPROVED' ? 'badge-success' : req.status === 'PENDING_APPROVAL' ? 'badge-warning' : 'badge-danger'}`}>
                            {req.status}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem', color: 'var(--text-muted)' }}>{new Date(req.created_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Bill Pay (Accounts Payable) */}
        {activeTab === 'bills' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Create Vendor</h3>
              {vendorFuzzyWarning && (
                <div style={{ background: 'var(--color-warning-glow)', border: '1px solid rgba(245,158,11,0.2)', padding: '0.75rem 1rem', borderRadius: '8px', color: 'var(--color-warning)', marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.9rem' }}>
                  <AlertTriangle size={18} />
                  <span>{vendorFuzzyWarning}</span>
                </div>
              )}
              <form onSubmit={handleCreateVendor} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ flex: 1, minWidth: '180px' }}>
                  <label>Vendor Name</label>
                  <input type="text" value={newVendorName} onChange={(e) => { setNewVendorName(e.target.value); setVendorFuzzyWarning(null); }} required placeholder="e.g. Acme Corp" />
                </div>
                <div style={{ flex: 1, minWidth: '180px' }}>
                  <label>Vendor Contact Email</label>
                  <input type="email" value={newVendorEmail} onChange={(e) => setNewVendorEmail(e.target.value)} required placeholder="billing@acme.com" />
                </div>
                <div style={{ width: '200px' }}>
                  <label>Bank Account routing ref</label>
                  <input type="text" value={newVendorBank} onChange={(e) => setNewVendorBank(e.target.value)} required placeholder="ACH account / routing ref token" />
                </div>
                <button type="submit" className="btn btn-primary">Create Vendor</button>
              </form>
            </div>

            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Submit Vendor Bill</h3>
              {vendors.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>Define a vendor above before adding invoices.</p>
              ) : (
                <form onSubmit={handleCreateBill} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div className="grid-3" style={{ gap: '1rem' }}>
                    <div>
                      <label>Attributed Department</label>
                      <select value={billDeptId} onChange={(e) => setBillDeptId(e.target.value)}>
                        {departments.map(d => (
                          <option key={d.id} value={d.id}>{d.name}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label>Select Vendor</label>
                      <select value={billVendorId} onChange={(e) => setBillVendorId(e.target.value)}>
                        {vendors.map(v => (
                          <option key={v.id} value={v.id}>{v.name}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label>Due Date</label>
                      <input type="date" value={billDueDate} onChange={(e) => setBillDueDate(e.target.value)} required />
                    </div>
                  </div>

                  <div className="grid-3" style={{ gap: '1.0rem', alignItems: 'flex-end' }}>
                    <div style={{ gridColumn: 'span 2' }}>
                      <label>Line Item Description</label>
                      <input type="text" value={billLineDesc} onChange={(e) => setBillLineDesc(e.target.value)} placeholder="Consulting Services, Office Supplies" />
                    </div>
                    <div>
                      <label>Select GL Code Mapping</label>
                      <select value={billGLAccountId} onChange={(e) => setBillGLAccountId(e.target.value)}>
                        <option value="">No Mapping (Uncoded)</option>
                        {glAccounts.map(g => (
                          <option key={g.id} value={g.id}>{g.code} - {g.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', justifyContent: 'space-between' }}>
                    <div style={{ width: '150px' }}>
                      <label>Amount (USD)</label>
                      <input type="number" value={billLineAmount} onChange={(e) => setBillLineAmount(Number(e.target.value))} placeholder="Amount" />
                    </div>
                    <button type="button" className="btn btn-secondary" onClick={handleAddBillLine}>Add Line Item</button>
                  </div>

                  {billLineItems.length > 0 && (
                    <div style={{ background: '#0e1014', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                      <p style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem' }}>Invoice Line Items Checklist</p>
                      {billLineItems.map((li, idx) => (
                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', padding: '0.25rem 0' }}>
                          <span>{li.description} {li.gl_account_id ? `(GL account attached)` : ''}</span>
                          <span style={{ fontWeight: 700 }}>${li.amount.toFixed(2)}</span>
                        </div>
                      ))}
                      <div style={{ borderTop: '1px solid var(--border-color)', margin: '0.5rem 0', paddingTop: '0.5rem', display: 'flex', justifyContent: 'space-between', fontWeight: 700 }}>
                        <span>TOTAL AMOUNT:</span>
                        <span>${billLineItems.reduce((acc, curr) => acc + curr.amount, 0).toFixed(2)}</span>
                      </div>
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <div>
                      <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <input type="radio" name="pay_method" checked={billPaymentMethod === 'BANK_TRANSFER'} onChange={() => setBillPaymentMethod('BANK_TRANSFER')} />
                        <span>Pay by ACH / Wire Transfer</span>
                      </label>
                    </div>
                    <div>
                      <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <input type="radio" name="pay_method" checked={billPaymentMethod === 'CARD'} onChange={() => setBillPaymentMethod('CARD')} />
                        <span>Pay by Corporate Credit Card</span>
                      </label>
                    </div>
                  </div>

                  <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Save Draft Bill</button>
                </form>
              )}
            </div>

            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Accounts Payable Bills Ledger</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Vendor</th>
                      <th style={{ padding: '0.75rem' }}>Department</th>
                      <th style={{ padding: '0.75rem' }}>Due Date</th>
                      <th style={{ padding: '0.75rem' }}>Payment Type</th>
                      <th style={{ padding: '0.75rem' }}>Total Amount</th>
                      <th style={{ padding: '0.75rem' }}>Status</th>
                      <th style={{ padding: '0.75rem' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bills.map(b => (
                      <tr key={b.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                        <td style={{ padding: '0.75rem', fontWeight: 600 }}>{b.vendor_name}</td>
                        <td style={{ padding: '0.75rem' }}>{b.department_name}</td>
                        <td style={{ padding: '0.75rem' }}>{b.due_date}</td>
                        <td style={{ padding: '0.75rem' }}>
                          <span className="badge badge-info">{b.payment_method}</span>
                        </td>
                        <td style={{ padding: '0.75rem', fontWeight: 700 }}>${b.total_amount.toFixed(2)}</td>
                        <td style={{ padding: '0.75rem' }}>
                          <span className={`badge ${b.status === 'PAID' ? 'badge-success' : b.status === 'APPROVED' ? 'badge-info' : b.status === 'PENDING_APPROVAL' ? 'badge-warning' : b.status === 'VOID' ? 'badge-danger' : 'badge-secondary'}`}>
                            {b.status}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            {b.status === 'DRAFT' && (
                              <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => handleSubmitBill(b.id)}>
                                Submit Approvals
                              </button>
                            )}
                            {b.status === 'APPROVED' && (user.roles.includes('ADMIN') || user.roles.includes('BOOKKEEPER')) && (
                              <button className="btn btn-primary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => handlePayBill(b.id)}>
                                Disburse Payment
                              </button>
                            )}
                            {b.status !== 'VOID' && b.status !== 'PAID' && (
                              <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', color: 'var(--color-danger)' }} onClick={() => handleVoidBill(b.id)}>
                                Void
                              </button>
                            )}
                            {b.status === 'PAID' && (user.roles.includes('ADMIN')) && (
                              <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', color: 'var(--color-danger)' }} onClick={() => handleVoidBill(b.id)}>
                                Refund / Void
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Reimburse */}
        {activeTab === 'reimbursements' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Submit Expense Claim</h3>
              <form onSubmit={handleSubmitReimbursement} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <div className="grid-3" style={{ gap: '1rem' }}>
                  <div>
                    <label>Claim Type</label>
                    <select value={reimbType} onChange={(e) => setReimbType(e.target.value as any)}>
                      <option value="OUT_OF_POCKET">Out-of-Pocket Expense</option>
                      <option value="MILEAGE">Mileage Trip Claim</option>
                    </select>
                  </div>
                  <div>
                    <label>Department Scope</label>
                    <select value={reimbDeptId} onChange={(e) => setReimbDeptId(e.target.value)}>
                      {departments.map(d => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {reimbType === 'OUT_OF_POCKET' ? (
                  <>
                    <div className="grid-3" style={{ gap: '1rem', alignItems: 'flex-end' }}>
                      <div style={{ gridColumn: 'span 2' }}>
                        <label>Receipt Description / merchant details</label>
                        <input type="text" value={reimbLineDesc} onChange={(e) => setReimbLineDesc(e.target.value)} placeholder="Uber to Airport, Business Lunch" />
                      </div>
                      <div>
                        <label>Select GL Code</label>
                        <select value={reimbGLAccountId} onChange={(e) => setReimbGLAccountId(e.target.value)}>
                          <option value="">No Mapping</option>
                          {glAccounts.map(g => (
                            <option key={g.id} value={g.id}>{g.code} - {g.name}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', justifyContent: 'space-between' }}>
                      <div style={{ width: '150px' }}>
                        <label>Expense Amount (USD)</label>
                        <input type="number" value={reimbLineAmount} onChange={(e) => setReimbLineAmount(Number(e.target.value))} placeholder="Amount" />
                      </div>
                      <button type="button" className="btn btn-secondary" onClick={handleAddReimbLine}>Add Line</button>
                    </div>

                    {reimbLineItems.length > 0 && (
                      <div style={{ background: '#0e1014', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                        <p style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem' }}>Out-of-Pocket Lines Added</p>
                        {reimbLineItems.map((li, idx) => (
                          <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', padding: '0.25rem 0' }}>
                            <span>{li.description}</span>
                            <span style={{ fontWeight: 700 }}>${li.amount.toFixed(2)}</span>
                          </div>
                        ))}
                        <div style={{ borderTop: '1px solid var(--border-color)', margin: '0.5rem 0', paddingTop: '0.5rem', display: 'flex', justifyContent: 'space-between', fontWeight: 700 }}>
                          <span>CLAIM TOTAL:</span>
                          <span>${reimbLineItems.reduce((acc, curr) => acc + curr.amount, 0).toFixed(2)}</span>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="grid-3" style={{ gap: '1rem' }}>
                      <div style={{ gridColumn: 'span 2' }}>
                        <label>Trip Purpose</label>
                        <input type="text" value={mileagePurpose} onChange={(e) => setMileagePurpose(e.target.value)} placeholder="Client visit at downtown office" />
                      </div>
                      <div>
                        <label>Total Miles Driven</label>
                        <input type="number" value={mileageMiles} onChange={(e) => setMileageMiles(Number(e.target.value))} placeholder="Miles" min="0.1" step="0.1" />
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      <label>Trip Waypoints Sequence</label>
                      {waypoints.map((address, idx) => (
                        <div key={idx} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <MapPin size={16} color="var(--color-primary)" />
                          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Waypoint #{idx+1}</span>
                          <input type="text" value={address} onChange={(e) => handleWaypointChange(idx, e.target.value)} required placeholder={idx === 0 ? "Start Address" : idx === waypoints.length-1 ? "Destination Address" : "Stop"} />
                        </div>
                      ))}
                      <button type="button" className="btn btn-secondary" style={{ alignSelf: 'flex-start', padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginTop: '0.5rem' }} onClick={handleAddWaypoint}>
                        + Add Waypoint Stop
                      </button>
                    </div>

                    {mileageMiles > 0 && (
                      <div style={{ background: '#0e1014', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Calculated Rate (IRS 2024 standard):</span>
                          <span>$0.67 / mile</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, marginTop: '0.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
                          <span>ESTIMATED PAYOUT:</span>
                          <span>${(mileageMiles * 0.67).toFixed(2)}</span>
                        </div>
                      </div>
                    )}
                  </>
                )}

                <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Submit Claim for Review</button>
              </form>
            </div>

            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Reimbursements Status Ledger</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Claimant</th>
                      <th style={{ padding: '0.75rem' }}>Department</th>
                      <th style={{ padding: '0.75rem' }}>Claim Type</th>
                      <th style={{ padding: '0.75rem' }}>Summary Details</th>
                      <th style={{ padding: '0.75rem' }}>Total Amount</th>
                      <th style={{ padding: '0.75rem' }}>Status</th>
                      <th style={{ padding: '0.75rem' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reimbursements.map(r => (
                      <tr key={r.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                        <td style={{ padding: '0.75rem', fontWeight: 600 }}>{r.requester_name}</td>
                        <td style={{ padding: '0.75rem' }}>{r.department_name}</td>
                        <td style={{ padding: '0.75rem' }}>{r.type}</td>
                        <td style={{ padding: '0.75rem', fontSize: '0.85rem' }}>
                          {r.type === 'MILEAGE' && r.trip ? (
                            <span>{r.trip.purpose} ({r.trip.total_miles} miles)</span>
                          ) : (
                            <span>{r.line_items.map(li => li.description).join(', ')}</span>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem', fontWeight: 700 }}>${r.total_amount.toFixed(2)}</td>
                        <td style={{ padding: '0.75rem' }}>
                          <span className={`badge ${r.status === 'REIMBURSED' ? 'badge-success' : r.status === 'APPROVED' ? 'badge-info' : r.status === 'SUBMITTED' ? 'badge-warning' : 'badge-danger'}`}>
                            {r.status}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          {r.status === 'APPROVED' && (user.roles.includes('ADMIN') || user.roles.includes('BOOKKEEPER')) && (
                            <button className="btn btn-primary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => handlePayoutReimbursement(r.id)}>
                              Payout (ACH)
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Accounting & ERP Sync (Admin only) */}
        {activeTab === 'accounting' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
            
            {/* Create GL account */}
            {user.roles.includes('ADMIN') && (
              <div className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem' }}>Add Chart of Accounts (GL) Account</h3>
                <form onSubmit={handleCreateGLAccount} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div style={{ width: '120px' }}>
                    <label>GL Code</label>
                    <input type="text" value={newGLCode} onChange={(e) => setNewGLCode(e.target.value)} required placeholder="e.g. 6100" />
                  </div>
                  <div style={{ flex: 1, minWidth: '200px' }}>
                    <label>Account Name</label>
                    <input type="text" value={newGLName} onChange={(e) => setNewGLName(e.target.value)} required placeholder="e.g. Software Subscriptions" />
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Account Type</label>
                    <select value={newGLType} onChange={(e) => setNewGLType(e.target.value)}>
                      <option value="ASSET">ASSET</option>
                      <option value="LIABILITY">LIABILITY</option>
                      <option value="EXPENSE">EXPENSE</option>
                      <option value="REVENUE">REVENUE</option>
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary">Add Account</button>
                </form>
              </div>
            )}

            {/* Create GL mappings */}
            {user.roles.includes('ADMIN') && (
              <div className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem' }}>Configure Auto-Coding Mapping Rules</h3>
                {glAccounts.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)' }}>Define a GL Account first before mapping rules.</p>
                ) : (
                  <form onSubmit={handleCreateGLMapping} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                    <div style={{ width: '180px' }}>
                      <label>Mapping Trigger</label>
                      <select value={newMapType} onChange={(e) => setNewMapType(e.target.value)}>
                        <option value="MCC">Merchant Category (MCC)</option>
                        <option value="VENDOR">Vendor</option>
                        <option value="DEPARTMENT">Department</option>
                      </select>
                    </div>
                    <div style={{ flex: 1, minWidth: '180px' }}>
                      <label>Source Match Value</label>
                      <input type="text" value={newMapSource} onChange={(e) => setNewMapSource(e.target.value)} required placeholder="e.g. 4816 (MCC) or Vendor ID" />
                    </div>
                    <div style={{ flex: 1, minWidth: '200px' }}>
                      <label>Map to GL Account</label>
                      <select value={newMapGLId} onChange={(e) => setNewMapGLId(e.target.value)}>
                        {glAccounts.map(g => (
                          <option key={g.id} value={g.id}>{g.code} - {g.name}</option>
                        ))}
                      </select>
                    </div>
                    <button type="submit" className="btn btn-primary">Save Mapping Rule</button>
                  </form>
                )}
              </div>
            )}

            {/* GL mapping list */}
            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Active Auto-Coding Mapping Rules</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Trigger Type</th>
                      <th style={{ padding: '0.75rem' }}>Source Match Value</th>
                      <th style={{ padding: '0.75rem' }}>Mapped GL Code</th>
                      <th style={{ padding: '0.75rem' }}>Mapped GL Account Name</th>
                    </tr>
                  </thead>
                  <tbody>
                    {glMappings.length === 0 ? (
                      <tr>
                        <td colSpan={4} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                          No mapping rules configured. Add rules above.
                        </td>
                      </tr>
                    ) : (
                      glMappings.map(m => (
                        <tr key={m.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                          <td style={{ padding: '0.75rem', fontWeight: 600 }}>{m.mapping_type}</td>
                          <td style={{ padding: '0.75rem' }}>{m.source_value}</td>
                          <td style={{ padding: '0.75rem', fontWeight: 700 }}>{m.gl_account_code}</td>
                          <td style={{ padding: '0.75rem' }}>{m.gl_account_name}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Custom fields configuration */}
            {user.roles.includes('ADMIN') && (
              <div className="card">
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem' }}>Define Accounting Custom Fields</h3>
                <form onSubmit={handleCreateCustomField} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div style={{ flex: 1, minWidth: '180px' }}>
                    <label>Field Name</label>
                    <input type="text" value={newFieldName} onChange={(e) => setNewFieldName(e.target.value)} required placeholder="e.g. Project Code, Cost Center" />
                  </div>
                  <div style={{ width: '150px' }}>
                    <label>Field Type</label>
                    <select value={newFieldType} onChange={(e) => setNewFieldType(e.target.value)}>
                      <option value="TEXT">TEXT (Freeform)</option>
                      <option value="SELECT">SELECT (Dropdown list)</option>
                    </select>
                  </div>
                  {newFieldType === 'SELECT' && (
                    <div style={{ flex: 1, minWidth: '200px' }}>
                      <label>Dropdown Options (comma separated)</label>
                      <input type="text" value={newFieldOptions} onChange={(e) => setNewFieldOptions(e.target.value)} placeholder="e.g. Project-A, Project-B" />
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <input type="checkbox" id="field_req" checked={newFieldRequired} onChange={(e) => setNewFieldRequired(e.target.checked)} />
                    <label htmlFor="field_req" style={{ marginBottom: 0 }}>Required Field</label>
                  </div>
                  <button type="submit" className="btn btn-primary">Define Field</button>
                </form>
              </div>
            )}

            {/* ERP Sync Queue Monitor */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '2.0rem' }}>
                <div>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Mock ERP Ledger Sync Queue</h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Pushes settled transactions, paid bills, and reimbursed claims to ERP general ledger books.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <label style={{ display: 'flex', gap: '0.25rem', alignItems: 'center', fontSize: '0.85rem' }}>
                    <input type="checkbox" checked={syncForceError} onChange={(e) => setSyncForceError(e.target.checked)} />
                    <span>Simulate push errors</span>
                  </label>
                  <button className="btn btn-primary" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }} onClick={handleProcessSync}>
                    <RefreshCw size={16} />
                    <span>Run Sync Engine</span>
                  </button>
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Record Type</th>
                      <th style={{ padding: '0.75rem' }}>Record ID</th>
                      <th style={{ padding: '0.75rem' }}>Mapped GL Code</th>
                      <th style={{ padding: '0.75rem' }}>Mapped GL Name</th>
                      <th style={{ padding: '0.75rem' }}>Sync State</th>
                      <th style={{ padding: '0.75rem' }}>Sync Timestamp / Error</th>
                      <th style={{ padding: '0.75rem' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {syncQueue.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                          Sync queue is empty. Settle transactions, pay bills, or payout reimbursements to populate queue.
                        </td>
                      </tr>
                    ) : (
                      syncQueue.map(item => (
                        <tr key={item.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                          <td style={{ padding: '0.75rem', fontWeight: 600 }}>{item.record_type}</td>
                          <td style={{ padding: '0.75rem', fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{item.record_id}</td>
                          <td style={{ padding: '0.75rem', fontWeight: 700 }}>{item.gl_account_code}</td>
                          <td style={{ padding: '0.75rem' }}>{item.gl_account_name}</td>
                          <td style={{ padding: '0.75rem' }}>
                            <span className={`badge ${item.status === 'SYNCED' ? 'badge-success' : item.status === 'SYNC_READY' ? 'badge-info' : item.status === 'SYNCING' ? 'badge-warning' : 'badge-danger'}`}>
                              {item.status}
                            </span>
                          </td>
                          <td style={{ padding: '0.75rem', fontSize: '0.85rem' }}>
                            {item.status === 'SYNCED' && item.synced_at ? (
                              <span style={{ color: 'var(--text-muted)' }}>{new Date(item.synced_at).toLocaleString()}</span>
                            ) : item.status === 'ERROR' ? (
                              <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>{item.error_message}</span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>Pending sync run...</span>
                            )}
                          </td>
                          <td style={{ padding: '0.75rem' }}>
                            {item.status === 'ERROR' && (
                              <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => handleRetrySync(item.id)}>
                                Retry
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Background Jobs Monitor */}
            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Async Background Jobs & Retries (DLQ)</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Job Type</th>
                      <th style={{ padding: '0.75rem' }}>Reference ID</th>
                      <th style={{ padding: '0.75rem' }}>Status</th>
                      <th style={{ padding: '0.75rem' }}>Retries / Max</th>
                      <th style={{ padding: '0.75rem' }}>Error details</th>
                      <th style={{ padding: '0.75rem' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backgroundJobs.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                          No background jobs processed.
                        </td>
                      </tr>
                    ) : (
                      backgroundJobs.map(job => (
                        <tr key={job.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                          <td style={{ padding: '0.75rem', fontWeight: 600 }}>{job.job_type}</td>
                          <td style={{ padding: '0.75rem', fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{job.source_event_id}</td>
                          <td style={{ padding: '0.75rem' }}>
                            <span className={`badge ${job.status === 'COMPLETED' ? 'badge-success' : job.status === 'FAILED' ? 'badge-danger' : 'badge-warning'}`}>
                              {job.status}
                            </span>
                          </td>
                          <td style={{ padding: '0.75rem' }}>{job.retries} / {job.max_retries}</td>
                          <td style={{ padding: '0.75rem', fontSize: '0.85rem', color: job.status === 'FAILED' ? 'var(--color-danger)' : 'var(--text-secondary)' }}>
                            {job.error_message || 'None'}
                          </td>
                          <td style={{ padding: '0.75rem' }}>
                            {job.status === 'FAILED' && (
                              <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => handleRetryJob(job.id)}>
                                Retry Job
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* System Audit Logs */}
            <div className="card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.5rem' }}>Apex Audit Trail Logs</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Timestamp</th>
                      <th style={{ padding: '0.75rem' }}>Action</th>
                      <th style={{ padding: '0.75rem' }}>Initiated By</th>
                      <th style={{ padding: '0.75rem' }}>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.length === 0 ? (
                      <tr>
                        <td colSpan={4} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                          No audit trail records exist.
                        </td>
                      </tr>
                    ) : (
                      auditLogs.map(log => (
                        <tr key={log.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                          <td style={{ padding: '0.75rem', color: 'var(--text-muted)' }}>{new Date(log.created_at).toLocaleString()}</td>
                          <td style={{ padding: '0.75rem', fontWeight: 600 }}>
                            <span style={{ color: 'var(--color-primary)' }}>{log.action}</span>
                          </td>
                          <td style={{ padding: '0.75rem' }}>{log.user_name}</td>
                          <td style={{ padding: '0.75rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                            {JSON.stringify(log.details)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        )}

        {/* Tab 6: Anomaly detection insights feed */}
        {activeTab === 'insights' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
            
            {/* Savings rollup header card */}
            <div className="card" style={{ background: 'linear-gradient(135deg, #101b22, #0d1e16)', border: '1px solid rgba(16,185,129,0.2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                <div>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>TOTAL SAVINGS IDENTIFIED (CONFIRMED)</p>
                  <h2 style={{ fontSize: '2.5rem', fontWeight: 800, color: 'var(--color-success)', fontFamily: 'Outfit', marginTop: '0.25rem' }}>
                    ${totalSavings.toFixed(2)}
                  </h2>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                    Savings rollup computed dynamically over confirmed waste-reduction/duplicate-subscription alerts.
                  </p>
                </div>
                
                <button className="btn btn-primary" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }} onClick={handleTriggerDetect}>
                  <RefreshCw size={16} />
                  <span>Run Spend Leakage Audit</span>
                </button>
              </div>
            </div>

            {/* Insights Feed list */}
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '1.25rem' }}>Active Spend Leakage & Anomaly Alerts</h3>
              {insights.length === 0 ? (
                <div className="card" style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No anomalies flagged. Run a spend leakage audit using the button above!
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  {insights.map(item => (
                    <div key={item.id} className="card" style={{ background: '#0e1014', borderLeft: `4px solid ${item.status === 'CONFIRMED' ? 'var(--color-success)' : item.severity === 'MEDIUM' ? 'var(--color-warning)' : 'var(--color-danger)'}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                      <div style={{ flex: 1, minWidth: '280px' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span className={`badge ${item.type === 'DUPLICATE_SUBSCRIPTION' ? 'badge-danger' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                            {item.type.replace('_', ' ')}
                          </span>
                          <span className="badge badge-info" style={{ fontSize: '0.7rem' }}>
                            SEVERITY: {item.severity}
                          </span>
                          <span className={`badge ${item.status === 'CONFIRMED' ? 'badge-success' : item.status === 'DISMISSED' ? 'badge-secondary' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                            {item.status}
                          </span>
                        </div>
                        <h4 style={{ fontSize: '1.05rem', fontWeight: 700 }}>{item.description}</h4>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                          Flagged on: {new Date(item.created_at).toLocaleString()} | Potential monthly savings: <strong>${item.potential_savings.toFixed(2)}</strong>
                        </p>
                      </div>

                      {item.status === 'OPEN' && (
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="btn btn-secondary" style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }} onClick={() => handleDismissInsight(item.id)}>
                            Dismiss
                          </button>
                          <button className="btn btn-primary" style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }} onClick={() => handleConfirmInsight(item.id)}>
                            Confirm Savings
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 7: Card Swipe Simulator */}
        {activeTab === 'transactions' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div className="card">
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1.5rem' }}>
                <Layers color="var(--color-primary)" />
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Simulated Card Swipe Terminal</h3>
              </div>

              {cards.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>You must issue an active card first.</p>
              ) : (
                <form onSubmit={handleSwipeSimulation} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div className="grid-3" style={{ gap: '1rem' }}>
                    <div>
                      <label>Select Corporate Card</label>
                      <select value={swipeCardId} onChange={(e) => setSwipeCardId(e.target.value)}>
                        {cards.map(c => (
                          <option key={c.id} value={c.id}>
                            {c.owner_name} - {c.masked_pan} (Limit: ${c.limit_amount})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label>Swipe Amount (USD)</label>
                      <input 
                        type="number" 
                        value={swipeAmount} 
                        onChange={(e) => setSwipeAmount(Number(e.target.value))} 
                        required 
                        min="1"
                      />
                    </div>
                  </div>

                  <div className="grid-2" style={{ gap: '1rem' }}>
                    <div>
                      <label>Merchant Name</label>
                      <input 
                        type="text" 
                        value={swipeMerchant} 
                        onChange={(e) => setSwipeMerchant(e.target.value)} 
                        required 
                        placeholder="e.g. Starbucks, Uber"
                      />
                    </div>
                    <div>
                      <label>Merchant Category (MCC)</label>
                      <select value={swipeMcc} onChange={(e) => setSwipeMcc(e.target.value)}>
                        <option value="4816">SaaS Services (MCC: 4816)</option>
                        <option value="5812">Dining / Restaurant (MCC: 5812)</option>
                        <option value="4121">Taxi / Uber (MCC: 4121)</option>
                        <option value="5411">Groceries (MCC: 5411)</option>
                        <option value="9999">General Spending (MCC: 9999)</option>
                      </select>
                    </div>
                  </div>
                  
                  <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
                    Swipe Simulated Card
                  </button>
                </form>
              )}

              {swipeResult && (
                <div style={{ marginTop: '1.5rem', padding: '1rem', borderRadius: '8px', background: swipeResult.status.includes('APPROVED') ? 'var(--color-success-glow)' : 'var(--color-danger-glow)', border: `1px solid ${swipeResult.status.includes('APPROVED') ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}` }}>
                  <h4 style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {swipeResult.status.includes('APPROVED') ? <Check color="var(--color-success)" /> : <X color="var(--color-danger)" />}
                    Transaction Status: {swipeResult.status}
                  </h4>
                  {swipeResult.decline_reason && (
                    <p style={{ marginTop: '0.25rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                      Reason: <strong style={{ color: 'var(--color-danger)' }}>{swipeResult.decline_reason}</strong>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Transactions table */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Real-time Transaction Audit Ledger</h3>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn btn-secondary" style={{ padding: '0.5rem 1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }} onClick={handleDownloadTransactionsCsv}>
                    <FileText size={16} />
                    <span>Export CSV</span>
                  </button>
                  <button className="btn btn-secondary" style={{ padding: '0.5rem 1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }} onClick={() => { fetchTransactions(); fetchMetrics(); }}>
                    <RefreshCw size={16} />
                    <span>Refresh Feed</span>
                  </button>
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.75rem' }}>Card Owner</th>
                      <th style={{ padding: '0.75rem' }}>Masked Card</th>
                      <th style={{ padding: '0.75rem' }}>Merchant</th>
                      <th style={{ padding: '0.75rem' }}>Category</th>
                      <th style={{ padding: '0.75rem' }}>Amount</th>
                      <th style={{ padding: '0.75rem' }}>Settlement State</th>
                      <th style={{ padding: '0.75rem' }}>Created At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map(tx => (
                      <tr key={tx.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.9rem' }}>
                        <td style={{ padding: '0.75rem', fontWeight: 500 }}>{tx.owner_name}</td>
                        <td style={{ padding: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{tx.masked_pan}</td>
                        <td style={{ padding: '0.75rem', fontWeight: 500 }}>{tx.merchant_name}</td>
                        <td style={{ padding: '0.75rem' }}>
                          <span className="badge badge-info">{tx.category || 'Categorizing...'}</span>
                        </td>
                        <td style={{ padding: '0.75rem', fontWeight: 700, color: tx.status === 'DECLINED' ? 'var(--color-danger)' : 'var(--text-primary)' }}>
                          {tx.currency} {tx.amount.toFixed(2)}
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          <span className={`badge ${tx.status === 'SETTLED' ? 'badge-success' : tx.status === 'HELD' ? 'badge-warning' : 'badge-danger'}`}>
                            {tx.status}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem', color: 'var(--text-muted)' }}>
                          {new Date(tx.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 8: Approvals Review Panel */}
        {activeTab === 'approvals' && (
          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="card">
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '1.5rem' }}>Approvals Inbox Review Panel</h3>
              {approvalSteps.length === 0 ? (
                <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  All caught up! No approvals waiting for review.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  {approvalSteps.map(step => (
                    <div key={step.id} className="card" style={{ background: '#0e1014', borderLeft: '4px solid var(--color-warning)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                      <div>
                        <span className="badge badge-warning" style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}>
                          STEP {step.step_number} OF {step.total_steps} ({step.approver_role})
                        </span>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginTop: '0.25rem' }}>
                          {step.approvable_type === 'CARD_REQUEST' ? 'Corporate Card Request' : step.approvable_type === 'BILL' ? 'Accounts Payable Vendor Bill' : 'Expense Reimbursement Payout'}
                        </h4>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                          Submitted for <strong>{step.department_name}</strong> Dept. Created: {new Date(step.created_at).toLocaleDateString()}
                        </p>
                      </div>

                      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                        <button className="btn btn-secondary" style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }} onClick={() => handleDecideApproval(step.id, 'REJECTED')}>
                          <X size={16} />
                          <span>Reject</span>
                        </button>
                        <button className="btn btn-primary" onClick={() => handleDecideApproval(step.id, 'APPROVED')}>
                          <Check size={16} />
                          <span>Approve & Sign</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'ops' && (
          <div className="animate-fade-in">
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '1.5rem' }}>Ops Center</h2>

            {opsSummary && (
              <div className="grid-3" style={{ marginBottom: '2rem' }}>
                <div className="card">
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Pending Approvals</p>
                  <p style={{ fontSize: '1.75rem', fontWeight: 800 }}>{opsSummary.pending_approvals}</p>
                </div>
                <div className="card">
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Open Disputes</p>
                  <p style={{ fontSize: '1.75rem', fontWeight: 800 }}>{opsSummary.open_disputes}</p>
                </div>
                <div className="card">
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Vendors w/ Sanctions Hits</p>
                  <p style={{ fontSize: '1.75rem', fontWeight: 800 }}>{opsSummary.vendors_sanctions_hit}</p>
                </div>
                <div className="card">
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Sync Errors</p>
                  <p style={{ fontSize: '1.75rem', fontWeight: 800 }}>{opsSummary.sync_errors}</p>
                </div>
                <div className="card">
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Open Reconciliation Discrepancies</p>
                  <p style={{ fontSize: '1.75rem', fontWeight: 800 }}>{opsSummary.open_reconciliation_discrepancies}</p>
                </div>
                <div className="card">
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Unread Admin Notifications</p>
                  <p style={{ fontSize: '1.75rem', fontWeight: 800 }}>{opsSummary.unread_admin_notifications}</p>
                </div>
              </div>
            )}

            {user.roles.includes('ADMIN') && (
              <div className="card" style={{ marginBottom: '2rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>
                  Pending User Approvals
                  {pendingUsers.length > 0 && (
                    <span className="badge badge-warning" style={{ marginLeft: '0.5rem', fontSize: '0.7rem' }}>{pendingUsers.length}</span>
                  )}
                </h3>
                {pendingUsers.length === 0 && (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No pending registration requests.</p>
                )}
                {pendingUsers.map(pu => (
                  <div key={pu.id} style={{ borderBottom: '1px solid var(--border-color)', padding: '0.75rem 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                    <div>
                      <p style={{ fontWeight: 600, fontSize: '0.9rem' }}>{pu.name} <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>({pu.email})</span></p>
                      <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Requested {pu.requested_role_id || 'EMPLOYEE'}
                        {pu.requested_department_id ? ` — ${departments.find(d => d.id === pu.requested_department_id)?.name || pu.requested_department_id}` : ''}
                        {pu.created_at ? ` — ${new Date(pu.created_at).toLocaleDateString()}` : ''}
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <select
                        value={pendingApproveRole[pu.id] ?? pu.requested_role_id ?? 'EMPLOYEE'}
                        onChange={(e) => setPendingApproveRole(prev => ({ ...prev, [pu.id]: e.target.value }))}
                        style={{ fontSize: '0.8rem', padding: '0.35rem' }}
                      >
                        {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                      </select>
                      <select
                        value={pendingApproveDept[pu.id] ?? pu.requested_department_id ?? ''}
                        onChange={(e) => setPendingApproveDept(prev => ({ ...prev, [pu.id]: e.target.value }))}
                        style={{ fontSize: '0.8rem', padding: '0.35rem' }}
                      >
                        <option value="">No department</option>
                        {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                      </select>
                      <button className="btn btn-primary" style={{ fontSize: '0.8rem' }} onClick={() => handleApproveUser(pu.id)}>Approve</button>
                      <button className="btn btn-secondary" style={{ fontSize: '0.8rem', color: 'var(--color-danger)' }} onClick={() => handleRejectUser(pu.id)}>Reject</button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Reconciliation */}
            <div className="card" style={{ marginBottom: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Payment-Rail Reconciliation</h3>
                <button className="btn btn-primary" onClick={handleRunReconciliation}>
                  <RefreshCw size={16} />
                  <span>Run Reconciliation</span>
                </button>
              </div>
              {reconciliationRuns.length === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No reconciliation runs yet.</p>
              )}
              {reconciliationRuns.map(run => (
                <div key={run.id} style={{ borderBottom: '1px solid var(--border-color)', padding: '0.75rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span className="badge badge-info" style={{ marginRight: '0.5rem' }}>{run.provider}</span>
                      <span className={`badge ${run.status === 'COMPLETED' ? 'badge-success' : run.status === 'FAILED' ? 'badge-danger' : 'badge-warning'}`}>{run.status}</span>
                      <span style={{ marginLeft: '0.75rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {run.checked_count} checked, {run.discrepancy_count} discrepancy(ies)
                      </span>
                    </div>
                    {run.discrepancy_count > 0 && (
                      <button className="btn btn-secondary" style={{ fontSize: '0.8rem' }} onClick={() => fetchReconciliationDiscrepancies(run.id)}>
                        View Discrepancies
                      </button>
                    )}
                  </div>
                  {reconciliationDiscrepancies[run.id] && reconciliationDiscrepancies[run.id].length > 0 && (
                    <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {reconciliationDiscrepancies[run.id].map(d => (
                        <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#0e1014', padding: '0.5rem 0.75rem', borderRadius: '8px' }}>
                          <div>
                            <p style={{ fontSize: '0.85rem', fontWeight: 600 }}>{d.subject_type} {d.transfer_ref}</p>
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              Local: {d.local_status} vs Provider: {d.provider_status}{d.amount != null ? ` — $${d.amount.toFixed(2)}` : ''}
                            </p>
                          </div>
                          {!d.resolved ? (
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button className="btn btn-secondary" style={{ fontSize: '0.75rem' }} onClick={() => handleResolveDiscrepancy(run.id, d.id, 'RETRY')}>Retry</button>
                              <button className="btn btn-secondary" style={{ fontSize: '0.75rem' }} onClick={() => handleResolveDiscrepancy(run.id, d.id, 'ACKNOWLEDGE')}>Acknowledge</button>
                            </div>
                          ) : (
                            <span className="badge badge-success">{d.resolved}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Sanctions Screening */}
            <div className="card" style={{ marginBottom: '2rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Sanctions Screening</h3>
              {screenings.length === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No screening records.</p>
              )}
              {screenings.map(s => (
                <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', padding: '0.5rem 0' }}>
                  <div>
                    <p style={{ fontWeight: 600, fontSize: '0.9rem' }}>{s.subject_name} <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>({s.subject_type})</span></p>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>via {s.provider} — {new Date(s.created_at).toLocaleString()}</p>
                  </div>
                  <span className={`badge ${s.status === 'CLEAR' ? 'badge-success' : s.status === 'HIT' ? 'badge-danger' : 'badge-warning'}`}>{s.status}</span>
                </div>
              ))}
            </div>

            {/* Card Disputes */}
            <div className="card" style={{ marginBottom: '2rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Card Disputes</h3>
              {disputes.length === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No disputes.</p>
              )}
              {disputes.map(d => (
                <div key={d.id} style={{ borderBottom: '1px solid var(--border-color)', padding: '0.75rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <p style={{ fontWeight: 600, fontSize: '0.9rem' }}>${d.amount.toFixed(2)} — {d.reason || 'No reason given'}</p>
                      <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{new Date(d.created_at).toLocaleString()}</p>
                    </div>
                    <span className={`badge ${d.status === 'WON' ? 'badge-success' : d.status === 'LOST' ? 'badge-danger' : 'badge-warning'}`}>{d.status}</span>
                  </div>
                  {(d.status === 'WARNING_NEEDS_RESPONSE' || d.status === 'UNDER_REVIEW') && (
                    <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                      <input
                        placeholder="Evidence / explanation..."
                        value={disputeEvidenceInput[d.id] || ''}
                        onChange={(e) => setDisputeEvidenceInput(prev => ({ ...prev, [d.id]: e.target.value }))}
                        style={{ flex: 1 }}
                      />
                      <button className="btn btn-primary" style={{ fontSize: '0.8rem' }} onClick={() => handleSubmitDisputeEvidence(d.id)}>
                        Submit Evidence
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* 1099-NEC Tax Reporting */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>1099-NEC Tax Reporting</h3>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <select value={necYear} onChange={(e) => setNecYear(Number(e.target.value))} style={{ fontSize: '0.85rem', padding: '0.4rem' }}>
                    {[0, 1, 2].map(offset => {
                      const y = new Date().getFullYear() - offset;
                      return <option key={y} value={y}>{y}</option>;
                    })}
                  </select>
                  <button className="btn btn-secondary" style={{ fontSize: '0.8rem' }} onClick={handleDownloadNecCsv}>Download CSV</button>
                </div>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <th style={{ padding: '0.5rem' }}>Vendor</th>
                      <th style={{ padding: '0.5rem' }}>Tax ID</th>
                      <th style={{ padding: '0.5rem' }}>Total Paid</th>
                      <th style={{ padding: '0.5rem' }}>Payments</th>
                      <th style={{ padding: '0.5rem' }}>Reportable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {necReport.map(row => (
                      <tr key={row.vendor_id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.85rem' }}>
                        <td style={{ padding: '0.5rem' }}>{row.vendor_name}</td>
                        <td style={{ padding: '0.5rem' }}>{row.tax_id || <em style={{ color: 'var(--color-warning)' }}>missing</em>}</td>
                        <td style={{ padding: '0.5rem' }}>${row.total_paid.toFixed(2)}</td>
                        <td style={{ padding: '0.5rem' }}>{row.payment_count}</td>
                        <td style={{ padding: '0.5rem' }}>
                          {row.reportable ? <span className="badge badge-warning">Yes</span> : <span className="badge badge-info">No</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <form onSubmit={handleUpdateVendorTaxInfo} style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div>
                  <label>Vendor</label>
                  <select value={taxInfoVendorId} onChange={(e) => setTaxInfoVendorId(e.target.value)} required>
                    <option value="">Select vendor...</option>
                    {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                  </select>
                </div>
                <div>
                  <label>Tax ID (EIN/SSN)</label>
                  <input value={vendorTaxIdInput} onChange={(e) => setVendorTaxIdInput(e.target.value)} required />
                </div>
                <div>
                  <label>Tax Address</label>
                  <input value={vendorTaxAddressInput} onChange={(e) => setVendorTaxAddressInput(e.target.value)} required />
                </div>
                <button type="submit" className="btn btn-primary">Save Tax Info</button>
              </form>
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="animate-fade-in">
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '1.5rem' }}>Settings</h2>

            <div className="card" style={{ marginBottom: '2rem', maxWidth: '480px' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Multi-Factor Authentication</h3>
              {mfaEnabled ? (
                <>
                  <p style={{ color: 'var(--color-success)', fontSize: '0.9rem', marginBottom: '1rem' }}>MFA is currently enabled on your account.</p>
                  <form onSubmit={handleMfaDisable} style={{ display: 'flex', gap: '0.5rem' }}>
                    <input placeholder="Enter code to disable" value={mfaCodeInput} onChange={(e) => setMfaCodeInput(e.target.value)} required />
                    <button type="submit" className="btn btn-danger">Disable</button>
                  </form>
                </>
              ) : mfaEnrollUrl ? (
                <>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    Scan this into your authenticator app, or enter the secret manually:
                  </p>
                  <p style={{ fontFamily: 'monospace', fontSize: '0.85rem', wordBreak: 'break-all', background: '#0e1014', padding: '0.5rem', borderRadius: '6px' }}>{mfaEnrollUrl}</p>
                  <p style={{ fontFamily: 'monospace', fontSize: '0.85rem', marginTop: '0.5rem' }}>Secret: {mfaEnrollSecret}</p>
                  <form onSubmit={handleMfaConfirm} style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                    <input placeholder="Enter code to confirm" value={mfaCodeInput} onChange={(e) => setMfaCodeInput(e.target.value)} required />
                    <button type="submit" className="btn btn-primary">Confirm</button>
                  </form>
                </>
              ) : (
                <button className="btn btn-primary" onClick={handleMfaEnroll}>Enable MFA</button>
              )}
            </div>

            {user.roles.includes('ADMIN') && (
              <div className="card" style={{ maxWidth: '640px' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Single Sign-On (SSO)</h3>
                <form onSubmit={handleCreateSsoConnection} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
                  <input placeholder="company-domain.com" value={ssoDomainInput} onChange={(e) => setSsoDomainInput(e.target.value)} style={{ flex: 1 }} required />
                  <button type="submit" className="btn btn-primary">Create Connection</button>
                </form>
                {ssoConnections.length === 0 && (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No SSO connections configured.</p>
                )}
                {ssoConnections.map(c => (
                  <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', padding: '0.5rem 0' }}>
                    <div>
                      <p style={{ fontWeight: 600, fontSize: '0.9rem' }}>{c.domain}</p>
                      <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{c.provider}</p>
                    </div>
                    <span className={`badge ${c.status === 'ACTIVE' ? 'badge-success' : 'badge-warning'}`}>{c.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
