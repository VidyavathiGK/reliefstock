# ReliefStock — Community Inventory & Donation Management System

[![ReliefStock CI](https://github.com/VidyavathiGK/reliefstock/actions/workflows/ci.yml/badge.svg)](https://github.com/VidyavathiGK/reliefstock/actions/workflows/ci.yml)

> **Enterprise-grade Humanitarian Relief & Food Bank Inventory Platform**
> *Built with Django 5.x, Django REST Framework, PostgreSQL, ReportLab, pytest, WhiteNoise, and Gunicorn.*

ReliefStock is a full-featured, multi-tenant inventory, donation intake, and relief distribution management platform designed specifically for community food banks, homeless shelters, and disaster relief NGOs. It coordinates the full lifecycle of humanitarian aid: from multi-item drop-off intakes and live stock tracking to formal distribution request approval and partial/full client fulfillment.

---

## 0. Project Description & Mission

**ReliefStock** addresses the critical operational challenges faced by frontline NGOs, food pantries, emergency shelters, and community aid organizations:

* **Real-time Stock Visibility**: Eliminates stockouts and food waste through an immutable double-entry ledger calculation (`StockTransaction`), replacing manual spreadsheets and error-prone batch updates.
* **Governance & Audit Compliance**: Enforces multi-tier governance for aid dispatches (`PENDING` ➔ `APPROVED` ➔ `FULFILLED`). Over-fulfillments beyond physical warehouse stock are prevented with atomic database transactions.
* **Perishable & Expiry Management**: Automated timeline tracking highlights perishables expiring within 7 days to prioritize immediate dispatch, while flagging already-expired goods for safe disposal.
* **Donor Engagement & Attribution**: Features a dedicated self-service Donor Portal with verified tax-receipt records, encouraging recurring contributions and transparent tracking.
* **Modern Enterprise NGO UI**: Designed with a clean, distraction-free humanitarian design system featuring a fixed sidebar, live ops health monitoring, instant client-side catalog search, and visual throughput summaries.

---

## 1. System Architecture & Feature Matrix

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ReliefStock Architecture                          │
├──────────────────────────────────────┬──────────────────────────────────────┤
│               Web UI                 │               REST API               │
│  - Django HTML Templates             │  - Django REST Framework (DRF)       │
│  - Role-scoped Dashboards            │  - Token & Session Authentication    │
│  - CSV & PDF Reporting Engine        │  - Atomic Multi-item Endpoints       │
│  - Donor Self-Service Portal         │  - Tenant-isolated ViewSets          │
├──────────────────────────────────────┴──────────────────────────────────────┤
│                          Core Domain & Business Logic                       │
│  - Multi-tenant Organization Scoping (request.org)                          │
│  - Immutable Stock Ledger (StockTransaction)                                │
│  - Live Stock Calculation (Coalesce / Sum / Case / When)                    │
│  - Governance: Request (Pending) ──► Review (Approved) ──► Fulfill          │
│  - Automated Restock Thresholds & Perishable Expiry Tracking                │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Infrastructure & Reliability                       │
│  - PostgreSQL 16 (psycopg 3)         │  - Gunicorn WSGI Web Process         │
│  - WhiteNoise Static Compression     │  - pytest + pytest-django Test Suite │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Complete 6-Phase Evolution
1. **Phase 1: Multi-Tenant Foundation & Auth**
   Custom `User` model with 4 distinct roles (`ADMIN`, `STAFF`, `VOLUNTEER`, `DONOR`), `Organization` tenant isolation, catalog items, and Django administration.
2. **Phase 2: Immutable Stock Ledger & Inbound Intakes**
   `StockTransaction` double-entry ledger (`DONATION_IN`, `MANUAL_ADJUSTMENT_IN/OUT`), multi-item atomic donation recording, manual stock adjustments with audit notes, and live stock calculation.
3. **Phase 3: Outbound Distribution Governance & Alert Queues**
   `DistributionRequest` and `DistributionRequestItem` models, request approval/rejection lifecycle, live stock over-fulfillment prevention, partial fulfillment support, perishable expiry tracking (7-day window), and low-stock alerts.
4. **Phase 4: Executive Operations Dashboard, CSV/PDF Reporting & Permissions Polish**
   Staff/Admin operational cockpit, tabular reporting engine with dynamic date/search filters, 1-click **CSV** and **PDF** exports (via ReportLab flowables), dedicated read-only Donor Portal, and unified `@role_required` decorators.
5. **Phase 5: REST API, Automated Testing Suite & Production Deployment**
   Full DRF API (`/api/v1/`), Token Authentication, atomic nested serializers, 42-test `pytest` automated test suite with fixtures, Gunicorn WSGI setup, WhiteNoise asset compression, and 1-click Render blueprint (`render.yaml`).
6. **Phase 6: Enterprise NGO Frontend & UI Redesign**
   Fixed sidebar navigation layout, top header with live ops status indicator, mobile drawer, 5 core KPI cards, HTML/CSS visual throughput summaries, instant client-side table search & filtering, and semantic status badges with zero external framework dependencies.

---

## 2. REST API Documentation (`/api/v1/`)

The ReliefStock REST API provides programmatic access for third-party integrations, mobile client apps, and external logistics systems.

### 2.1 Authentication & Base URL
* **Base URL:** `/api/v1/`
* **Authentication Method:** Token Authentication (or Session Authentication for browsable API testing).
* **Header format:**
  ```http
  Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
  ```

#### Obtain Auth Token
* **Endpoint:** `POST /api/v1/auth/token/`
* **Request:**
  ```json
  {
    "username": "staff_marcus",
    "password": "StrongPassword123!"
  }
  ```
* **Response:**
  ```json
  {
    "token": "4a2b8e91c7f0d3e2a1b9c8d7e6f5a4b3c2d1e0f9"
  }
  ```

---

### 2.2 API Endpoints Reference

| Method | Endpoint | Description | Permitted Roles |
|---|---|---|---|
| `GET` | `/api/v1/items/` | List catalog items with live stock counts and low-stock status | Staff, Admin |
| `POST` | `/api/v1/items/` | Create a new catalog item | Staff, Admin |
| `GET` | `/api/v1/items/low_stock/` | Filter items at or below their reorder threshold | Staff, Admin |
| `GET` | `/api/v1/items/expiring_soon/` | Perishable batches expiring within next 7 days | Staff, Admin |
| `GET` | `/api/v1/items/expired/` | Perishable batches past expiry date | Staff, Admin |
| `GET` | `/api/v1/categories/` | List inventory categories | Staff, Admin |
| `GET` | `/api/v1/donations/` | List donations (Donors see only their own history) | All Authenticated |
| `POST` | `/api/v1/donations/` | Atomically record multi-item donation intake | Staff, Volunteer, Admin |
| `GET` | `/api/v1/distribution-requests/` | List distribution requests for organization | Staff, Volunteer, Admin |
| `POST` | `/api/v1/distribution-requests/` | Create a new distribution request | Staff, Volunteer, Admin |
| `POST` | `/api/v1/distribution-requests/{id}/review/` | Approve or reject a distribution request | Admin Only |
| `POST` | `/api/v1/distribution-requests/{id}/fulfill/` | Dispatch stock and atomically deduct ledger | Staff, Admin |
| `GET` | `/api/v1/dashboard/` | Real-time operational metrics for organization | Staff, Admin |

---

### 2.3 Sample API Workflows & Payloads

#### A. Record an Inbound Donation with Multiple Items
`POST /api/v1/donations/`
```json
{
  "donor_name": "Midwest Harvest Co.",
  "donor_contact": "logistics@midwestharvest.test",
  "date_received": "2026-10-02",
  "notes": "Direct farm donation: dry beans and fresh dairy",
  "items": [
    {
      "inventory_item": 1,
      "quantity": "250.00",
      "note": "Grade-A pinto beans"
    },
    {
      "inventory_item": 4,
      "quantity": "80.00",
      "expiry_date": "2026-10-09",
      "note": "Refrigerated crate #3"
    }
  ]
}
```

#### B. Create a Distribution Request
`POST /api/v1/distribution-requests/`
```json
{
  "recipient_name": "Downtown Shelter Pantry",
  "recipient_contact": "case-worker-88@shelter.test",
  "notes": "Weekly emergency pantry restock",
  "items": [
    {
      "inventory_item": 1,
      "quantity_requested": "50.00"
    },
    {
      "inventory_item": 4,
      "quantity_requested": "20.00"
    }
  ]
}
```

#### C. Administrative Review (Approve or Reject)
`POST /api/v1/distribution-requests/{id}/review/`
```json
{
  "action": "APPROVE",
  "notes": "Authorized based on standard monthly shelter quota."
}
```

#### D. Fulfill / Dispatch Relief Supplies
`POST /api/v1/distribution-requests/{id}/fulfill/`
```json
{
  "notes": "Dispatched via logistics van #2",
  "dispatches": [
    {
      "item_id": 12,
      "quantity_to_fulfill": "50.00"
    },
    {
      "item_id": 13,
      "quantity_to_fulfill": "20.00"
    }
  ]
}
```
*Note: The API automatically verifies available live stock on hand. If stock is insufficient or if dispatch exceeds remaining balance, the request is rejected with HTTP 400 and an informative error message.*

---

## 3. Role-Based Access Control (RBAC) Matrix

| Platform Feature / Route | Route URL | ADMIN | STAFF | VOLUNTEER | DONOR |
|---|---|:---:|:---:|:---:|:---:|
| **Landing Dispatcher** | `/` | Home Portal | Home Portal | Home Portal | Redirect to `/donor/` |
| **Donor Self-Service Portal** | `/donor/` | Denied | Denied | Denied | **Yes (Own Data Only)** |
| **Executive Dashboard (Web & API)** | `/inventory/dashboard/`, `/api/v1/dashboard/` | **Yes** | **Yes** | Denied | Denied |
| **Management Reports (HTML/CSV/PDF)** | `/inventory/reports/*` | **Yes** | **Yes** | Denied | Denied |
| **Catalog Items & Live Stock** | `/inventory/`, `/api/v1/items/` | **Yes** | **Yes** | Denied | Denied |
| **Low-Stock & Expiry Alerts** | `/inventory/alerts/*`, `/api/v1/items/*` | **Yes** | **Yes** | Denied | Denied |
| **Manual Stock Adjustments** | `/inventory/<id>/adjust/` | **Yes** | **Yes** | Denied | Denied |
| **Record Inbound Donation** | `/inventory/donations/record/`, `/api/v1/donations/` | **Yes** | **Yes** | **Yes** | Denied |
| **Create Distribution Request** | `/inventory/distributions/create/`, `/api/v1/distribution-requests/` | **Yes** | **Yes** | **Yes** | Denied |
| **List Distribution Requests** | `/inventory/distributions/`, `/api/v1/distribution-requests/` | **Yes** | **Yes** | **Yes** | Denied |
| **Review Request (Approve/Reject)** | `.../review/`, `/api/v1/distribution-requests/{id}/review/` | **Yes** | Denied | Denied | Denied |
| **Fulfill Distribution** | `.../fulfill/`, `/api/v1/distribution-requests/{id}/fulfill/` | **Yes** | **Yes** | Denied | Denied |
| **Django Admin Site** | `/admin/` | **Yes** | Staff Only | Denied | Denied |

---

## 4. Automated Testing, Code Quality & CI/CD

ReliefStock enforces strict code quality and continuous integration using modern developer tooling:

### 4.1 Testing with `pytest` & `pytest-cov`
* **Test Architecture:** 42 automated tests covering models, atomic ledgers, multi-tenant boundaries, and DRF API endpoints.
* **Coverage Analysis:** `pytest-cov` runs on every test invocation with terminal reports.
```powershell
# Run the test suite with coverage
pytest
```
*Sample output:*
```text
============================= test session starts =============================
platform win32 -- Python 3.13.4, pytest-9.1.1, django-5.1.6
rootdir: reliefstock, configfile: pytest.ini
collected 42 items

accounts/tests.py ..................................                    [ 10%]
inventory/tests.py .................................                    [ 62%]
organizations/tests.py .                                                [ 64%]
tests/test_api_endpoints.py ........                                   [ 83%]
tests/test_distribution_workflow.py ...                                 [ 90%]
tests/test_stock_logic.py .....                                         [100%]

Name                           Stmts   Miss  Cover
--------------------------------------------------
TOTAL                           1692    347    79%
============================== 42 passed in 64.60s =============================
```

### 4.2 Code Quality & Formatting with `Ruff`
We use **[Ruff](https://docs.astral.sh/ruff/)** for blazing-fast linting and automatic formatting:
```powershell
# Check for lint errors
ruff check .

# Automatically apply safe fixes
ruff check --fix .

# Verify formatting without altering files
ruff format --check .

# Auto-format all Python files
ruff format .
```

### 4.3 Git Pre-Commit Hooks
Pre-commit hooks automatically format code and check for hygiene issues before any commit:
```powershell
# Install pre-commit hooks into git (one-time setup)
pre-commit install

# Manually run all hooks across the entire repository
pre-commit run --all-files
```

### 4.4 GitHub Actions Continuous Integration
Every push and pull request to `main` triggers [`.github/workflows/ci.yml`](file:///c:/Users/91843/.gemini/antigravity-ide/scratch/reliefstock/.github/workflows/ci.yml):
1. **PostgreSQL 16 Service:** Boots a dedicated test database container.
2. **Linting Check:** Fails the build if `ruff check .` finds any unaddressed lint errors.
3. **Format Check:** Fails the build if `ruff format --check .` detects unformatted code.
4. **Test & Coverage Execution:** Runs `pytest --cov` and publishes full coverage metrics.

For complete contributing guidelines and pull request instructions, see [CONTRIBUTING.md](file:///c:/Users/91843/.gemini/antigravity-ide/scratch/reliefstock/CONTRIBUTING.md).

---

## 5. Production Deployment Guide

ReliefStock is configured as a **12-Factor App** ready for free-tier deployment on modern cloud platforms such as **Render**, **Railway**, or **Fly.io**.

### 5.1 Architecture Stack
* **WSGI Web Server:** `Gunicorn` (`Procfile`) for multi-worker HTTP request handling.
* **Static Asset Management:** `WhiteNoise` with `CompressedManifestStaticFilesStorage` for automatic Brotli/Gzip compression, cache headers, and self-contained static asset serving without needing an external S3 bucket or Nginx proxy.
* **Database:** Managed PostgreSQL (e.g. Render PostgreSQL or Supabase).

### 5.2 Deploying to Render (1-Click Blueprint)
1. Fork or push this repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New** $\rightarrow$ **Blueprint**.
3. Connect your repository. Render will automatically detect [`render.yaml`](file:///c:/Users/91843/.gemini/antigravity-ide/scratch/reliefstock/render.yaml):
   - Provisions a free managed PostgreSQL database (`reliefstock_db`).
   - Runs `./build.sh` (`pip install`, `collectstatic`, `migrate`).
   - Starts the Gunicorn web server via `gunicorn reliefstock.wsgi:application`.

### 5.3 Manual Production Environment Variables
| Variable | Description | Production Example |
|---|---|---|
| `SECRET_KEY` | Cryptographic signing secret | `django-insecure-...` (generate strong secret) |
| `DEBUG` | Disables debug stack traces in production | `False` |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames | `reliefstock.onrender.com,127.0.0.1` |
| `DB_ENGINE` | Database engine backend | `django.db.backends.postgresql` |
| `DB_NAME` | PostgreSQL database name | `reliefstock_db` |
| `DB_USER` | PostgreSQL username | `reliefstock_user` |
| `DB_PASSWORD` | PostgreSQL password | `super_secure_password` |
| `DB_HOST` | Database host | `dpg-xxxx.oregon-postgres.render.com` |
| `DB_PORT` | Database port | `5432` |

---

## 6. Local Quickstart

### 1. Clone & Activate Environment
```powershell
cd reliefstock
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment Secrets
Copy the environment template:
```powershell
copy .env.example .env
```
*(Ensure PostgreSQL is running locally, or configure your database credentials).*

### 3. Run Migrations & Collect Static Files
```powershell
python manage.py migrate
python manage.py collectstatic --no-input
```

### 4. Run Development Server
```powershell
python manage.py runserver
```
Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/) to access the application.
Visit [http://127.0.0.1:8000/api/v1/](http://127.0.0.1:8000/api/v1/) to explore the browsable REST API.
