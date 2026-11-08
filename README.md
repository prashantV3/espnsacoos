# Financial Ledger & Loan Management System (SACCOS)

A robust, enterprise-grade centralized financial tracking and lending application designed for Savings and Credit Cooperative Organizations (SACCOS). Built with **Python (Django)**, **Django REST Framework (DRF)**, and configured for **Supabase (PostgreSQL)** with an immutable **Double-Entry Bookkeeping Ledger**.

---

## 1. Core Architecture & Highlights

* **Backend Framework:** Django 5.1 + Django REST Framework (DRF).
* **Database:** Supabase (PostgreSQL) supported out of the box via `DATABASE_URL` (with seamless local SQLite fallback).
* **Dual Authentication Strategy:**
  * **Web Client:** JWT access & refresh tokens stored in **HttpOnly, Secure, SameSite** cookies to protect against Cross-Site Scripting (XSS).
  * **Mobile Client:** Standard `Authorization: Bearer <token>` header support for React Native, Flutter, Swift, or Kotlin clients.
* **Codebase Pattern:** **"Fat Models, Skinny Views"**:
  * Mathematical reducing-balance EMI calculations ($E = P \cdot r \cdot \frac{(1+r)^n}{(1+r)^n - 1}$) implemented directly on `PrimaryLoan`.
  * Month-by-month amortization schedule generation.
  * Interest-free emergency advance grace period and overdue penalty calculations on `EmergencyAdvance`.
* **Double-Entry Accounting System:**
  * Strict immutability: Historical `Transaction` and `LedgerEntry` records cannot be altered or deleted.
  * Balanced journal entries ($\sum \text{Debits} = \sum \text{Credits}$) generated atomically for every financial event.
  * Dynamically calculated balances guarantee a perfect zero-difference **Trial Balance**.
* **Role-Based Access Control (RBAC):**
  * `SUPERUSER`: Global financial settings (base interest rates, grace days, penalty rates), user management, role assignments.
  * `ADMIN`: Financial operator. Records transactions (EMIs, deposits, disbursements), approves loans, grants emergency advances. Cannot edit historical ledgers.
  * `MEMBER`: Read-only access to their personal dashboard, active loans, amortization schedules, and financial standing.

---

## 2. Project Structure

```
d:\Personal Project\ESPN sacoos
├── apps/
│   ├── users/                 # Custom User, RBAC permissions, Dual JWT Auth, Global Settings
│   │   ├── models.py          # User (SUPERUSER, ADMIN, MEMBER), GlobalSettings
│   │   ├── authentication.py  # CookieOrHeaderJWTAuthentication (Mobile Header + Web Cookie)
│   │   ├── permissions.py     # IsSuperUser, IsAdminOrSuperUser, IsMember, IsOwnerOrAdmin
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── loans/                 # Primary Loans & Emergency Advances
│   │   ├── models.py          # Fat Models: EMI formula, Amortization Schedule, Grace Period checks
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   └── ledger/                # Double-Entry Ledger, Transactions, Trial Balance Reporting
│       ├── models.py          # Account (Chart of Accounts), Transaction, LedgerEntry
│       ├── reports.py         # TrialBalanceReport, MemberFinancialSummary
│       ├── dashboard_views.py # GET /api/v1/dashboard/me/
│       ├── serializers.py
│       ├── views.py
│       └── urls.py
├── config/                    # Django project configuration (settings, urls, wsgi)
├── .env.example               # Environment template for Supabase & JWT configuration
├── manage.py
├── requirements.txt
└── README.md
```

---

## 3. Setup & Installation

### Step 1: Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Configure Environment (.env)
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

To connect your **Supabase PostgreSQL** database, set `DATABASE_URL` in `.env`:
```env
DATABASE_URL=postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
```
*(If `DATABASE_URL` is left blank, the application will automatically fall back to local `db.sqlite3`.)*

### Step 4: Run Migrations
```powershell
python manage.py migrate
```

### Step 5: Seed Initial Data
Run the custom seeder command to create the standard Chart of Accounts, default settings, test users, and verified double-entry transactions:
```powershell
python manage.py seed_data
```

**Pre-seeded Credentials:**
| Role | Username | Password |
|---|---|---|
| **Superuser** | `superuser` | `Admin@123` |
| **Admin Operator** | `admin_operator` | `Operator@123` |
| **Member 1** | `member_john` | `Member@123` |
| **Member 2** | `member_jane` | `Member@123` |

---

## 4. API Reference

All endpoints are prefixed with `/api/v1/`.

### Authentication & Profiles
* `POST /api/v1/auth/login/`: Authenticates credentials. Returns JWT tokens in JSON (for mobile) and sets HttpOnly cookies (for web).
* `POST /api/v1/auth/refresh/`: Refreshes access token from request body or HttpOnly cookie.
* `POST /api/v1/auth/logout/`: Clears HttpOnly cookies.
* `GET /api/v1/auth/me/`: Returns logged-in user details.

### Roadmap Endpoints
#### 1. Member Mobile & Web Dashboard
* `GET /api/v1/dashboard/me/`
  * **Permissions:** Authenticated Member.
  * **Description:** Returns aggregated loan health, next EMI due date and amount, remaining principal balances, emergency advance status with remaining grace days, deposit savings balance, and personal trial balance summary.

#### 2. Transactions (Double-Entry Ledger)
* `POST /api/v1/transactions/`
  * **Permissions:** Admin / Superuser only.
  * **Description:** Records a new financial payment (`DEPOSIT`, `WITHDRAWAL`, `LOAN_DISBURSEMENT`, `LOAN_REPAYMENT`, `EMERGENCY_DISBURSEMENT`, `EMERGENCY_REPAYMENT`, `PENALTY_PAYMENT`).
  * **Ledger Automation:** Automatically generates balancing Debit and Credit `LedgerEntry` records atomically and updates loan status.
* `GET /api/v1/transactions/`
  * **Permissions:** Admins see all organization transactions; Members view only their own.
* `PUT / PATCH / DELETE /api/v1/transactions/<id>/`
  * **Result:** `405 Method Not Allowed`. Enforces historical immutability.

#### 3. Organization Trial Balance
* `GET /api/v1/reports/trial-balance/`
  * **Permissions:** Admin / Superuser only.
  * **Description:** Returns organization-wide double-entry Trial Balance. Verifies $\sum \text{Debits} == \sum \text{Credits}$ with `is_balanced: true` and `net_difference: 0.00`.
  * **Query Params:** `start_date=YYYY-MM-DD`, `end_date=YYYY-MM-DD`.

### Loans & Advances
* `GET /api/v1/loans/` - List loans (Admins see all, Members see own).
* `POST /api/v1/loans/` - Admin creates/approves a primary loan.
* `GET /api/v1/loans/<id>/amortization-schedule/` - Full month-by-month EMI schedule with interest, principal, and ending balance.
* `GET /api/v1/emergency-advances/` - List emergency advances.
* `POST /api/v1/emergency-advances/` - Admin grants an emergency advance with strict `interest_free_until` grace date.

### Global Configuration & Chart of Accounts
* `GET /api/v1/settings/` - View organization base interest rates & grace days.
* `PUT /api/v1/settings/` - Superuser updates global financial parameters.
* `GET /api/v1/accounts/` - Chart of accounts (Cash & Bank, Loans Receivable, Member Deposits, Interest Income, etc.).

---

## 5. Running Automated Tests

A comprehensive test suite is included covering:
1. **Mathematical EMI formula** & Amortization Schedule generation.
2. **Emergency advance grace period** checks and penalty calculations.
3. **Double-entry balance** and **Trial Balance reconciliation**.
4. **Ledger immutability** (prevention of update or deletion).
5. **Dual JWT authentication** (HttpOnly cookies + Authorization Bearer header).
6. **Role-Based Access Control (RBAC)** across all endpoints.

Execute tests using:
```powershell
python manage.py test
```
*(All 15 tests pass out of the box).*

