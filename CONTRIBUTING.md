# Contributing to ReliefStock

Thank you for contributing to ReliefStock! This document provides guidelines for local development, code quality standards, testing, and pull requests.

---

## 1. Development Setup

### 1.1 Prerequisites
* Python 3.12 or 3.13
* PostgreSQL 15+ (or Docker for running a local Postgres container)
* Git

### 1.2 Virtual Environment Setup
```powershell
# Clone the repository
git clone https://github.com/VidyavathiGK/reliefstock.git
cd reliefstock

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows
# source .venv/bin/activate    # On Linux/macOS

# Install all dependencies including dev tools
pip install -r requirements.txt
```

### 1.3 Local Database & Environment
```powershell
copy .env.example .env
python manage.py migrate
python manage.py collectstatic --no-input
```

---

## 2. Code Quality & Pre-commit Hooks

We use **[Ruff](https://docs.astral.sh/ruff/)** for extremely fast linting and code formatting, alongside **pre-commit** hooks to prevent issues from ever reaching the repository.

### 2.1 Setting Up Pre-Commit (One-Time)
Run this once inside your activated virtual environment:
```powershell
pre-commit install
```
This installs git pre-commit hooks that automatically verify linting, formatting, whitespace, and merge conflict markers on every `git commit`.

### 2.2 Running Pre-Commit Manually
To run all pre-commit checks against all files at any time:
```powershell
pre-commit run --all-files
```

### 2.3 Running Ruff Directly
```powershell
# Lint check
ruff check .

# Automatically apply safe lint fixes
ruff check --fix .

# Code formatting check
ruff format --check .

# Format all code files
ruff format .
```

---

## 3. Automated Testing & Coverage

We use **`pytest`** and **`pytest-django`** with **`pytest-cov`** for testing and coverage analysis.

### 3.1 Running Tests
```powershell
# Run the entire test suite with coverage report
pytest

# Run a specific test module
pytest tests/test_api_endpoints.py

# Run only tests matching a name pattern
pytest -k "test_donor"
```

The test runner will output a detailed terminal coverage summary highlighting any uncovered lines.

---

## 4. Continuous Integration (CI) Workflow

Every push to `main` and every Pull Request automatically triggers our **GitHub Actions CI Workflow** (`.github/workflows/ci.yml`).

### What CI Runs:
1. **PostgreSQL 16 Service Container:** Spins up a dedicated database for test execution.
2. **Dependency Installation:** Caches and installs dependencies from `requirements.txt`.
3. **Ruff Linter:** `ruff check .` (fails on any lint violations).
4. **Ruff Formatter Check:** `ruff format --check .` (fails on unformatted files).
5. **Full Test Suite & Coverage:** `pytest --cov=. --cov-report=term-missing:skip-covered` (fails if any test fails).

### Repository Secrets:
* No custom secrets are strictly required to run CI, as a safe default `SECRET_KEY` is provided for testing in `.github/workflows/ci.yml`.
* If desired, repository owners can set a custom `SECRET_KEY` in **Repository Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**.

---

## 5. Pull Request Standards
1. Create a descriptive feature branch from `main`:
   ```powershell
   git checkout -b feature/my-new-feature
   ```
2. Verify all checks pass locally before opening a PR:
   ```powershell
   ruff check .
   ruff format --check .
   pytest
   ```
3. Commit using conventional, clear commit messages.
4. Ensure all CI checks pass green before requesting review.
