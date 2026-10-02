# ReliefStock — Community Inventory & Donation Management System

> **Phase 1: Project Skeleton, Custom User/Auth System & Domain Schema**

ReliefStock is a full-stack Django platform designed to coordinate inventory, relief supplies, and volunteer operations for emergency shelters, food banks, and humanitarian NGOs.

---

## 1. Project Overview & Architecture

### Phase 1 Scope
- **Skeleton & Config:** Twelve-Factor environment configuration using `python-decouple`.
- **Authentication & Roles:** Custom `accounts.User` extending Django's `AbstractUser` with role tiers (`ADMIN`, `STAFF`, `VOLUNTEER`, `DONOR`) and optional organization affiliation.
- **Organizations App:** `organizations.Organization` model supporting Shelters, Food Banks, and NGOs.
- **Inventory App (Schema Only):** `Category` and `InventoryItem` catalog definitions (quantities and transaction logic will be added in Phase 2).
- **Admin Interface:** Fully customized Django Admin with role filters, organization search, and inline custom user creation.
- **Auth Views:** Built-in Django auth views with post-login redirect displaying username and role.

### Why a Single `settings.py` with Environment Variables?
We chose a unified `settings.py` powered by `python-decouple` rather than split `base.py`/`dev.py`/`prod.py` files.
- **Twelve-Factor Alignment:** Code remains identical across environments; only environment variables change.
- **Maintainability:** Eliminates wildcard import confusion (`from .base import *`), duplicate settings definitions, and circular import traps.
- **Readability for Code Reviews:** Clear, centralized configuration that is easy to navigate and explain during technical interviews.

---

## 2. Project Directory Structure

```text
reliefstock/
├── .env                     # Local environment secrets (ignored by git)
├── .env.example             # Template for required environment variables
├── .gitignore               # Standard Django and Python exclusions
├── README.md                # Project documentation and quickstart
├── requirements.txt         # Pinned production and development dependencies
├── manage.py
├── reliefstock/             # Core project package
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py          # Unified 12-factor settings
│   ├── urls.py              # Root routing (Admin, Login/Logout, Dashboard)
│   └── wsgi.py
├── accounts/                # Custom User and Authentication app
│   ├── migrations/          # Migration 0001_initial.py
│   ├── admin.py             # UserAdmin with role and organization fieldsets
│   ├── apps.py
│   ├── models.py            # User model extending AbstractUser
│   ├── tests.py             # Unit & integration tests for auth
│   └── views.py             # Home dashboard view
├── organizations/           # Relief Organizations app
│   ├── migrations/          # Migration 0001_initial.py
│   ├── admin.py             # OrganizationAdmin configuration
│   ├── apps.py
│   ├── models.py            # Organization model (SHELTER, FOOD_BANK, NGO)
│   └── tests.py             # Unit tests for Organization model
├── inventory/               # Inventory Catalog domain app
│   ├── migrations/          # Migration 0001_initial.py
│   ├── admin.py             # CategoryAdmin and InventoryItemAdmin
│   ├── apps.py
│   ├── models.py            # Category and InventoryItem models
│   └── tests.py             # Unit tests for catalog models
└── templates/               # Plain Django HTML templates
    ├── base.html            # Semantic HTML base layout
    ├── home.html            # Post-login redirect placeholder
    └── registration/
        └── login.html       # Standard Django authentication login form
```

---

## 3. Setup and Installation Guide

### Prerequisites
- Python 3.12+ (tested with Python 3.13)
- PostgreSQL database instance (local service, Docker, or managed cloud like Supabase/Neon/Render)

### Step 1: Clone & Setup Virtual Environment
```bash
# Navigate to the project directory
cd reliefstock

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 4. Configuring `.env`

Copy `.env.example` to `.env`:
```bash
# Windows:
copy .env.example .env
# Linux / macOS:
cp .env.example .env
```

Open `.env` and verify your settings:
```ini
SECRET_KEY=your-secure-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL Configuration
DB_ENGINE=django.db.backends.postgresql
DB_NAME=reliefstock_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
DB_CONNECT_TIMEOUT=3
```

> **Note on Quick Local Testing:** If your PostgreSQL server is not currently running, you can temporarily set `DB_ENGINE=django.db.backends.sqlite3` in `.env` to test with SQLite.

---

## 5. Running Database Migrations

Before running migrations, make sure your PostgreSQL database exists:
```sql
CREATE DATABASE reliefstock_db;
```

Then run the migration command:
```bash
python manage.py migrate
```

This applies all initial schema migrations in order:
1. `organizations.0001_initial`
2. `accounts.0001_initial` (creates custom `accounts_user` table)
3. `inventory.0001_initial` (creates `inventory_category` and `inventory_inventoryitem` tables)
4. Standard Django admin, auth permissions, and session tables.

---

## 6. Creating a Superuser

To access the Django Admin panel and provision your initial users and organizations, run the following command interactively:

```bash
python manage.py createsuperuser
```

You will be prompted to enter:
1. **Username** (e.g. `admin`)
2. **Email address** (e.g. `admin@reliefstock.org`)
3. **Password** (enter your own secure password)
4. **Password confirmation**

---

## 7. Starting the Development Server

Start the local server:
```bash
python manage.py runserver
```

Open your browser to:
- **Application Dashboard:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/) *(redirects to login if unauthenticated)*
- **User Login:** [http://127.0.0.1:8000/accounts/login/](http://127.0.0.1:8000/accounts/login/)
- **Django Admin Portal:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 8. Verifying Admin & Model Relationships

1. Log into `/admin/` with your superuser credentials.
2. Under **ORGANIZATIONS**, click **Add** to create an organization (e.g., `City Hope Shelter`, `Org Type: Emergency Shelter`).
3. Under **ACCOUNTS**, click **Add** to create a user and assign them:
   - Role: `STAFF` or `VOLUNTEER`
   - Organization: Select `City Hope Shelter`
4. Under **INVENTORY**, create a **Category** (e.g., `Non-Perishable Food`) and an **Inventory Item** (e.g., `Canned Tuna 150g`, linked to `City Hope Shelter`).
5. Log out of Admin and log into `/accounts/login/` with the staff user to verify the dashboard displays:
   `Logged in as <username> (<ROLE>)`.

---

## 9. Running Automated Tests

Run the test suite to ensure all models and auth flows are operating as expected:
```bash
python manage.py test
```
