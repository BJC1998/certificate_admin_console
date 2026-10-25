# Certificate Admin Console

Step 1 foundation: FastAPI health endpoint, SQLAlchemy/SQLite connection infrastructure, and a React/TypeScript/Vite dashboard. Certificate pages are navigation placeholders. No business models, tables, issuance, revocation or export are implemented yet.

## Prerequisites

- Python **3.15**, as requested for Step 1. Verify with `py -3.15 --version`.
- Node.js 20.19+ or 22.12+, npm, Windows PowerShell. Verified with Node.js 24.22.1 and npm 11.19.1.
- Git is already initialized. No commits are created automatically.

## Install (PowerShell, repository root)

```powershell
py -3.15 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm.cmd --prefix frontend ci
```

The explicit Python path avoids PowerShell activation-policy changes. Use `npm.cmd` to avoid restrictions on npm's PowerShell shim.

Stop Vite before reinstalling frontend dependencies: Windows locks its loaded native build module while the dev server is running.

## Start

Run each command from the repository root in a separate terminal:

```powershell
# Terminal 1: backend
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend/app
```

```powershell
# Terminal 2: frontend
npm.cmd --prefix frontend run dev
```

Open http://127.0.0.1:5173. The dashboard requests http://127.0.0.1:8000/health directly and displays checking, connected or error status, with a manual recheck button. Navigation supports Certificates and Bulk Issue placeholders. Use Ctrl+C in each terminal to stop.

Health contract: `GET /health` returns HTTP 200 and `{"status":"ok"}`. This checks application liveness only, not database connectivity. API documentation: http://127.0.0.1:8000/docs.

## Configuration

Backend variables are read from the process environment; backend `.env` files are not loaded automatically:

- `DATABASE_URL`: defaults to an absolute path to `backend/certificate_admin.db`, independent of the terminal's working directory. Only SQLite URLs are supported. The engine is lazy; startup does not create a database or any tables.
- `CORS_ORIGINS`: comma-separated origins, default `http://localhost:5173,http://127.0.0.1:5173`. Only GET is currently allowed; future steps must extend methods alongside new endpoints.

Frontend: copy `frontend/.env.example` to `frontend/.env.local` to customize `VITE_API_BASE_URL`. Vite loads frontend environment files; restart the dev server after changes. The dev server uses a strict port so it cannot silently move away from the allowed CORS origins.

## Architecture

```text
backend/
  app/
    main.py          # FastAPI composition and middleware
    core/            # Settings
    database/        # SQLite engine and session lifecycle
    models/          # Reserved for Step 2, no models yet
    routers/         # HTTP endpoints
    schemas/         # Request and response contracts
    services/        # Reserved for business operations
  tests/             # Health and CORS contract tests
  requirements.txt
frontend/
  src/
    api/             # HTTP clients
    components/      # Shared UI and health status
    pages/           # Dashboard and navigation placeholders
    types/           # Typed API contracts
```

Future tenant-owned operations must be tenant scoped on the backend. Health accesses no tenant data. Store timestamps in UTC and tenant timezones as IANA identifiers. Transactions and database unique constraints must enforce one certificate per tenant/course/learner, even after revocation, and prevent duplicate issuance audit entries. These business rules are reserved for later steps.

## Checks

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe -m compileall -q backend/app
.\backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); import app.main, app.database.session, app.models, app.schemas, app.services; print('Backend imports OK')"
.\backend\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend run build
Invoke-WebRequest http://127.0.0.1:8000/health
```

Browser smoke check: open the dashboard, confirm Connected, click both placeholders, return to the dashboard, then stop the backend and recheck to confirm an error is shown. Restart the backend and recheck to confirm recovery.

## Step 1 verification

Verified on Windows with Python 3.15.1, Node.js 24.22.1 and npm 11.19.1:

- Backend dependencies installed and pinned in `requirements.txt`; reinstall from the final file passed. `pip check` passed.
- `npm ci` from `package-lock.json` passed; npm reported zero known vulnerabilities at installation time.
- Four unittest checks passed: health contract, both allowed local CORS origins, unapproved-origin CORS rejection, and GET preflight.
- Backend compilation and explicit application/database/package imports passed.
- An isolated in-memory SQLite connection confirmed foreign keys are enabled and no tables exist. IANA timezone data loaded for `Australia/Sydney`.
- Live `GET /health`: HTTP 200, body `{"status":"ok"}`, expected frontend CORS origin.
- Browser dashboard displayed Connected; Certificates and Bulk Issue navigated to their placeholders.
- Stopping the backend and rechecking displayed Connection unavailable. After restart, Connected and manual recheck worked again.
- Frontend TypeScript checking and Vite production build passed, including after the clean dependency installation.

Environment issues encountered and resolved: the execution sandbox blocked package downloads and local sockets, so installation and socket-based verification ran with elevated tool permission. Its default temporary directory also blocked pip initialization; a repository-local temporary directory resolved that. The first clean npm reinstall hit Windows' native module lock while Vite was running; stopping Vite and rerunning succeeded. An initial test-client deprecation warning was resolved by installing and pinning `httpx2` and removing the unused legacy HTTP client.

No Step 1 blockers remain. Health indicates application liveness only. Business models, authentication/authorized tenant context, tenant data isolation checks, certificate operations and their tests belong to subsequent approved steps. Existing candidate documents were left unchanged. No Git commits were created.
