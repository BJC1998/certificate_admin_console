# Certificate Admin Console

Steps 1–3: FastAPI health endpoint, React/TypeScript/Vite dashboard, SQLAlchemy/SQLite schema, tenant-scoped certificate listing and repeatable demo data. The Certificates page supports tenant selection, search, sorting and pagination. Bulk issuance, details, revocation and export are not implemented yet.

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

Open http://127.0.0.1:5173. The dashboard requests http://127.0.0.1:8000/health directly and displays checking, connected or error status, with a manual recheck button. Navigation includes the Certificates register and a Bulk Issue placeholder. Use Ctrl+C in each terminal to stop.

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
    models/          # Six domain models and shared UTC type
    routers/         # HTTP endpoints
    schemas/         # Request and response contracts
    services/        # Reserved for business operations
  tests/             # Health and CORS contract tests
  requirements.txt
frontend/
  src/
    api/             # HTTP clients
    components/      # Shared UI and health status
    hooks/           # Certificate request lifecycle and stale-response guards
    pages/           # Dashboard and navigation placeholders
    types/           # Typed API contracts
```

Tenant-owned request operations must use the fixed-tenant session dependency. Health accesses no tenant data. See the Step 2 schema and boundary below.

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

At Step 1 completion, health indicated application liveness only and business features were deferred. Existing candidate documents were left unchanged. No Git commits were created.

## Step 2: initialize and seed (PowerShell)

From the repository root, with the existing virtual environment installed:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m app.database.init_db
.\.venv\Scripts\python.exe -m app.database.seed
.\.venv\Scripts\python.exe -m app.database.seed
Set-Location ..
```

The seed command also initializes missing tables. Initialization is explicit; application imports/startup do not create tables. The default file is `backend/certificate_admin.db` and is Git-ignored. Set `DATABASE_URL` before starting the process to target another SQLite database.

Expected counts after either seed run:

| Table | Total | Per tenant |
| --- | ---: | ---: |
| tenants | 2 | — |
| courses | 6 | 3 |
| learners | 60 | 30 |
| enrollments | 180 | 90 (72 completed, 18 incomplete) |
| certificates | 108 | 54 (45 valid, 9 revoked) |
| audit_logs | 126 | 63 (54 issued, 9 revoked) |

Demo tenants: **1 = Sydney / Australia/Sydney**, **2 = Perth / Australia/Perth**. Each tenant has three courses and completed-but-unissued enrollments for later issuance tests. Certificate timestamps include UTC times around tenant-local midnight and Sydney's daylight-saving transition. A repeat seed preserves existing records, revoked status and timestamps. The seed is a sequential development fixture, not an import/synchronization service; use a dedicated demo database. It refuses to overwrite conflicting tenant IDs.

## Step 2: model relationships and constraints

| Model | Relationships / database guarantees |
| --- | --- |
| Tenant | Root record; nonempty name/timezone, IANA timezone validated by ORM. |
| Course | Belongs to Tenant; unique `(tenant_id, id)` supports composite references. |
| Learner | Belongs to Tenant; unique `(tenant_id, id)` supports composite references. |
| Enrollment | Belongs to a Course and Learner in the same Tenant via composite FKs; unique `(tenant_id, course_id, learner_id)`; status `incomplete` or `completed`. |
| Certificate | Composite FKs to Course, Learner and the matching Enrollment; globally unique serial; unique `(tenant_id, course_id, learner_id)` includes revoked records; status `valid` or `revoked`. |
| AuditLog | Composite FK to the exact Certificate's tenant/id/course/learner tuple; one entry per `(tenant_id, certificate_id, action)`; action `issued` or `revoked`; nonempty actor. |

All owned records have a non-null tenant FK. SQLite foreign keys are enabled on every connection, use RESTRICT deletion, and are verified with `PRAGMA foreign_key_check`. Indexes support tenant/course/status enrollment lookup, tenant/learner names, course titles, certificate tenant/date/id ordering, tenant/status and tenant/learner filters, and tenant/audit date ordering. Uniqueness constraints also create SQLite indexes for the certificate/enrollment identities, serials and certificate audit actions.

`UTCDateTime` requires aware inputs, normalizes them to UTC for SQLite storage, and restores UTC tzinfo on reads. Tenant timezone names use `zoneinfo` and the pinned `tzdata` dependency; fixed offset strings such as `UTC+10` are rejected. Enum CHECK constraints also reject invalid statuses in direct SQL.

Relationships are read-only navigation attributes with implicit lazy loading disabled. Load explicitly (e.g. `selectinload(Certificate.course)`); write explicit FK fields so composite constraints remain clear. Certificates and audits are preserved by request-session write guards, and references use RESTRICT rather than cascading deletion. Eligibility is defined by `Enrollment.is_eligible` (`completed` only); the actual issuance service is deferred to Step 4.

## Step 2: demo tenant boundary and limitations

- Future tenant-owned endpoints depend on `get_session`, which resolves an existing positive `X-Tenant-ID` and creates one immutable-context `TenantSession`. Missing/malformed headers return 422; an unknown tenant returns 404. `/health` remains tenant-free and unchanged. CORS permits the selector header.
- **The header is a demo selector, not authentication or authorization. Anyone can select either demo tenant.** Production must authenticate the caller and verify tenant membership before resolving context. There is no claim of authenticated access isolation.
- ORM SELECTs automatically receive tenant criteria, including aliases, projections and explicitly loaded relationships. The shared `get_tenant_record` returns the same generic 404 for inaccessible and nonexistent resources.
- Writes take ownership from the session; body schemas reject `tenant_id`. Cross-tenant attachments and foreign references return 404 before flush; SQLite composite constraints provide a second integrity boundary.
- Request sessions disallow raw SQL, Core queries, `from_statement`, bulk DML and legacy bulk mapping APIs, which could bypass ORM ownership checks. No bypass execution option is provided. Business code must not use the engine or a plain Session directly.
- SQLite has no row-level access security here. The ORM boundary protects supported application access, not a database administrator, direct SQL or intentionally bypassing Python code. Plain Sessions and engine access exist only for explicit maintenance/test tasks.
- Request sessions forbid certificate deletion/identity changes and audit modification/deletion. A uniqueness constraint prevents duplicate audit actions, but a future issuance service must still create the certificate and its issuance audit in one transaction; the schema alone does not create an audit automatically.
- `create_all` initializes a new schema; it is not a migration tool. Concurrent seed processes and existing modified schemas are outside the demo seed contract. No tenant selector UI or business endpoints were added in Step 2.

## Step 2 verification

Run the backend check commands above; the test suite uses isolated in-memory SQLite databases and test-only HTTP routes, never the user's development data.

Verified on Python 3.15.1:

- Explicit SQLite initialization and two seed runs succeeded with identical counts shown above. A seed regression also compared every row before/after, including timestamps and revoked state.
- **29 backend tests passed** (25 database/tenant tests and the four existing health/CORS tests).
- Database rejected duplicate certificate identities (valid and revoked), global serials, enrollments and issuance audits; it also rejected cross-tenant course/learner/certificate references and mismatched audit references.
- Request-scoped reads, aliases, projected columns, counts and explicit relationship loads stayed in the selected tenant. Test-only HTTP reads and mutations returned 404 for another tenant's resource; injected body ownership returned 422; the foreign record remained unchanged.
- A failing audit insert rolled back the certificate in the same transaction. UTC normalization, naive timestamp rejection, IANA timezone validation, status CHECK constraints and history-preservation guards passed.
- Inspected all six tables, eight explicit indexes, seven unique constraints and eleven foreign keys (including the composite constraints). Actual development database: `PRAGMA foreign_key_check` returned no violations; `PRAGMA integrity_check` returned `ok`.
- Backend imports, `compileall`, `pip check`, frontend TypeScript check and Vite production build passed. No dependencies changed in Step 2.

No Step 2 test failures or blockers remain. No Git commits were created, no development servers were started/stopped for this step, and no candidate-only answers or frontend source files were modified.

## Step 3: certificate list API

`GET /api/tenants/{tenant_id}/certificates`

| Query parameter | Default | Accepted values |
| --- | --- | --- |
| search | empty | Up to 200 characters; trimmed literal substring of learner name or serial number |
| page | 1 | Integer 1–1,000,000 |
| page_size | 10 | Integer 1–100 |
| sort_by | issued_at | learner_name, course_title, serial_number, issued_at, status |
| sort_order | desc | asc, desc |

Response fields: `records`, `total`, `page`, `page_size`, `total_pages`, `tenant_id`, `tenant_timezone`. Each record contains `id`, `tenant_id`, `learner_name`, `course_title`, `serial_number`, `issued_at`, and `status` (`valid`/`revoked`). `issued_at` is a tenant-local ISO 8601 datetime with an explicit UTC offset; `tenant_timezone` is the IANA zone. Stored UTC timestamps are never mutated by a read. Date sorting follows chronological issue timestamps; ties on any sort field use certificate id in the same direction.

No matches return `records: []`, `total: 0`, `total_pages: 0`. A valid page beyond the last page returns empty records while preserving total and the requested page. Invalid query/path values return 422. Unknown tenants and conflicting path/header tenant selection return the same generic 404.

The URL selects the demo tenant. `X-Tenant-ID` is optional on this endpoint, but when present must match the URL. Existing header-only session callers remain supported. Certificate records, joined learners/courses and counts are all tenant scoped.

`GET /api/tenants` returns a list of `{id, name, timezone}` objects for the dropdown. This deliberate root-metadata directory is unauthenticated demo functionality and exposes no business records or counts. Neither URL selection nor the header authenticates the caller or proves tenant membership.

Example requests (PowerShell):

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/tenants'
Invoke-RestMethod 'http://127.0.0.1:8000/api/tenants/1/certificates?search=Sydney%20Learner%2001&page=1&page_size=10&sort_by=serial_number&sort_order=asc'
Invoke-RestMethod 'http://127.0.0.1:8000/api/tenants/2/certificates?page=2&page_size=10'
```

## Step 3: browser behavior and verification

Open `http://127.0.0.1:5173/#certificates`. The tenant dropdown loads actual metadata. Search submits using the Search button or Enter, and Clear removes the applied search. Changing tenant, submitted search, page size or sort resets to page 1. Click column headers to toggle sorting; Previous/Next use server-side pagination. Dates explicitly use the selected tenant's zone rather than the browser's zone.

Loading, no tenants, no results, fetch errors and retry are explicit. Requests have a ten-second timeout. Obsolete requests are aborted, their callbacks are ignored after cleanup, and rows from a different query key are hidden immediately. The table scrolls horizontally on narrow layouts, with labelled inputs, keyboard controls and accessible sort states. No frontend dependencies were added.

Verification completed:

- **41 backend tests passed**, including 12 new list API tests and all 29 earlier regressions. All five sort fields were checked in both directions, stable ties across page boundaries, complete non-overlapping pagination, learner/serial search, literal wildcard escaping, empty results, invalid parameters, tenant isolation, header/path conflicts and known Sydney/Perth local timestamps.
- Browser checks passed for learner search, serial search, sorting in both directions, moving to page 2, search resetting pagination, no-result UI, tenant switching, local dates and loading without stale rows.
- An ignored temporary ASGI wrapper returned HTTP 503; the page displayed the error and Retry. Restoring the API and clicking Retry recovered the requested page. Delaying Perth requests while switching back to Sydney did not replace Sydney's records with the late response.
- Browser verification used temporary ports 5174/8001 because the user's development servers already occupied 5173/8000. Production code contains no failure/delay controls. The user's servers were left untouched.
- A read-only request to the existing production backend on port 8000 returned 200, 54 Sydney records total, ten records on page 1 and the expected CORS origin.
- Backend imports/compilation and `pip check` passed. TypeScript checking and Vite production build passed. Run the Checks commands above to reproduce the automated checks.

Limitations: demo selection is not access authentication; SQLite's default case-insensitive substring behavior handles ASCII case folding, not full Unicode case folding. Offset pagination is intended for this assessment and is not a snapshot across concurrent data changes. Bulk issuance, details, revocation and export remain deferred. No Git commits were created.
