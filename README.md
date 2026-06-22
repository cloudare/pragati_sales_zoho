# Pragati Sales — Distributor Operations App

End-to-end Tally → FastAPI → Zoho Books integration with a React PWA frontend.

## What's in this repo

```
pragati-app/
├── backend/        FastAPI app, Postgres models, mock Zoho server, tests
├── frontend/       Vite + React PWA (mobile-first)
├── tdl/            Tally Definition Language add-on for sync
├── docker-compose.yml   For all-in-one local dev
└── README.md       This file
```

## Quickstart (local dev, 10 minutes)

```bash
# 1. Postgres
sudo -u postgres psql <<EOSQL
CREATE USER pragati WITH PASSWORD 'pragati';
CREATE DATABASE pragati_sales OWNER pragati;
EOSQL

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit
alembic upgrade head   # OR set AUTO_CREATE_TABLES=true for dev
uvicorn app.main:app --reload
# Backend on http://localhost:8000

# 3. Mock Zoho server (only for dev/staging without Zoho creds)
# In another terminal, in backend/:
ZOHO_DC=local-mock python3 tools/mock_zoho.py
# Then set ZOHO_DC=local-mock in your backend .env

# 4. Frontend
cd ../frontend
npm install
npm run dev
# Frontend on http://localhost:5173
```

Default seeded admin: `admin / admin123` — you will be forced to change it on first login.

## Security features (v1.1.0)

The backend ships with production-grade security:

- **Bcrypt password hashing** (random per-user salt)
- **Strong password policy** — minimum 10 chars, requires upper/lower/digit/symbol, common-password denylist
- **Forced password change on first login** — default admin and admin-created users
- **JWT access tokens** — 30-minute lifetime (configurable)
- **Refresh tokens** — 7 days, server-side revocable, rotated on every use
- **2FA / TOTP** — Google Authenticator-compatible. Required for admin and accounts roles (configurable)
- **Account lockout** — 10 failed attempts → 15-min lock
- **Login rate limit** — 5/min/IP (configurable)
- **Login audit log** — every attempt (success/failure) recorded with IP + user-agent
- **Session revocation** — logout revokes refresh token; password change revokes all sessions
- **Role-based access control** — 6 roles enforced on every endpoint
- **CORS** — explicit allowlist, no wildcards
- **Tally endpoints** — additional X-API-Key header required

See **Pragati_Sales_Deployment_Guide.docx** for full production hardening checklist and operational runbook.

## Tests

```bash
cd backend
export DATABASE_URL="postgresql://pragati:pragati@localhost:5432/pragati_sales_test"
export APP_SECRET_KEY="test"
export ZOHO_DC="local-mock"
pytest -v
```

Coverage: 31 tests (scheme engine, Tally parser, full E2E, security flows).

## Architecture overview

```
┌──────────────┐         ┌──────────────────┐         ┌────────────────┐
│   Tally      │         │     Backend      │         │   Zoho Books   │
│   ERP/Prime  │ XML/HTTP│  FastAPI         │ REST    │   Cloud        │
│   + TDL      ├────────►│  + Postgres      ├────────►│   Books API    │
│   addon      │         │                  │         │                │
└──────────────┘         └────────▲─────────┘         └────────────────┘
                                  │
                                  │ HTTPS/JWT
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   React PWA      │
                         │   (Vercel)       │
                         └──────────────────┘
```

**Data ownership rule**: Postgres holds only data Zoho cannot natively store (users, gate entries + photos, GRN photos, schemes, audit log, sync log). Everything else (items, contacts, invoices, bills, payments) lives in Zoho via Zoho IDs.

## Deployment

See **Pragati_Sales_Deployment_Guide.docx** in the project outputs.

Quick summary:
- **Frontend** → Vercel (free, automatic HTTPS, deploys on git push)
- **Backend** → VPS with Postgres + Nginx + Let's Encrypt. Recommended: AWS Lightsail Mumbai Micro plan (~₹420/month) or Nano (~₹295/month if tight on budget).

## Documentation

The companion documents (in `/mnt/user-data/outputs` when generated):

- **Pragati_Sales_SOW_Custom_WebApp.docx** — original Statement of Work
- **Pragati_Sales_Technical_Documentation.docx** — module-by-module technical reference
- **Pragati_Sales_Developer_Book.docx** — code walkthrough for new developers (setup, every file explained, run book)
- **Pragati_Sales_Deployment_Guide.docx** — production deployment, hardening checklist, ops runbook
