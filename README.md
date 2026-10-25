# Certificate Admin Console

A small Windows-friendly admin console for a multi-tenant training platform. The four core features are implemented: searchable certificate lists, retry-safe bulk issuance, certificate details with confirmed revocation, and complete filtered CSV export. Demo data, backend/frontend tests and a one-command development launcher are included.

## Quick start: one command

Open PowerShell in the repository folder and run:

```powershell
.\start.bat
```

The launcher checks Python/Node/npm, creates `backend/.venv` when missing, installs pinned backend and locked frontend dependencies when needed, initializes missing SQLite tables, and starts both development servers. It does **not** insert demo data. First use needs access to PyPI/npm or an appropriate local cache. Existing records, revoked certificates and issue history are preserved.

To load demo data separately (after environment preparation), run from the repository root:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m app.database.seed
Pop-Location
```

On a fresh checkout, run `.\start.bat --prepare-only` first to install dependencies. Without seeding, a new database has empty tables and no demo tenants.

Wait for `[READY]`, then open:

| Service | URL |
| --- | --- |
| Dashboard | http://127.0.0.1:5173/#dashboard |
| Certificates | http://127.0.0.1:5173/#certificates |
| Bulk Issue | http://127.0.0.1:5173/#bulk-issue |
| Backend health | http://127.0.0.1:8000/health |
| Interactive API docs | http://127.0.0.1:8000/docs |

Keep the terminal open. **Ctrl+C stops both services started by this launcher**, including the backend reload child. If Windows then asks `Terminate batch job (Y/N)?`, answer Y; service cleanup has already run. Service output is written to `tmp/dev/backend.log` and `tmp/dev/frontend.log`; the launcher reports early exits and prints log tails on startup failure. Occupied ports produce an error rather than terminating an existing process. The launcher is development tooling, not a production process manager.

## Prerequisites and supported versions

| Tool | Requirement / verified version |
| --- | --- |
| OS | Windows; verified on Windows 11 |
| Python | **3.15.x**, with the Windows `py` launcher; verified 3.15.1 |
| Node.js | **22.12+** for the installed frontend/test tooling; verified 24.22.1 |
| npm | Included with Node.js; verified 11.19.1 |
| SQLite | Included with Python; no separate database server required |
| Git | Used to clone and submit the repository |

Check the tools after installing them and reopening your terminal:

```powershell
py -3.15 --version
node --version
npm.cmd --version
```

Python 3.15 follows the final requested project version. Other Python versions are not the configured support target. The launcher does not install system tools or alter your global shell policy.

## Installation and alternative startup

1. Clone/download the repository and open a terminal in its root folder.
2. Install the prerequisite tools above.
3. Run `start.bat`; it performs environment preparation and startup in one command.

To prepare without starting services:

```powershell
.\start.bat --prepare-only
```

To install everything manually in a fresh checkout:

```powershell
py -3.15 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
Set-Location backend
.\.venv\Scripts\python.exe -m app.database.init_db
.\.venv\Scripts\python.exe -m app.database.seed
Set-Location ..
```

`requirements-dev.txt` includes the pinned runtime requirements plus pytest. For a runtime-only backend install, use `backend/requirements.txt`. The explicit virtual-environment Python path avoids activation-policy changes; `npm.cmd` avoids npm's PowerShell shim restrictions. Stop Vite before reinstalling node_modules on Windows because its native build module may be locked.

Manual startup uses two terminals, each starting from the repository root:

```powershell
# Terminal 1
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend/app
```

```powershell
# Terminal 2
npm.cmd --prefix frontend run dev
```

Stop both terminals with Ctrl+C. Do not run these alongside `start.bat` on the same ports.

## Implemented features

- Certificate register: learner-name/serial substring search, status filter, allowlisted server sorting, stable pagination, loading/empty/error/retry states and tenant switching with stale-response suppression.
- Bulk issuance: course selection, completed-enrollment eligibility, per-learner issued/skipped/failed reasons, honest processing text, duplicate-click protection, safe retry and refreshed certificate data.
- Details and revocation: original learner/course/serial/issue time, IANA tenant-local dates, explicit confirmation/cancellation, retained revoked details and transactional revoke audit.
- CSV: all matching records rather than the visible page, shared list/export filters and sorting, optional local-calendar-date order, UTF-8 escaping/formula protection, batched database reads and disk-spooled download preparation.
- Integrity: tenant/course/learner composite foreign keys, lifetime certificate uniqueness including revoked records, unique serials, preserved history, per-certificate/action audit uniqueness and UTC storage.

## Technology and architecture

Backend: Python 3.15, FastAPI 0.162.0, SQLAlchemy 2.1.6 and SQLite. Frontend: React 19.3.1, TypeScript 7.0.2 and Vite 8.3.5. Tests: pytest 9.1.1 with FastAPI TestClient and isolated SQLite databases; Vitest 5.0.5 with React Testing Library and jsdom. Exact Python versions are pinned in requirements files; frontend resolutions are in package-lock.json.

```text
start.bat                    Windows entry point
scripts/dev.py               Standard-library bootstrap and service supervisor
backend/
  app/
    main.py                  FastAPI composition and CORS
    core/                    Configuration, demo tenant context, IANA date helpers
    database/                Engine, tenant session, init and seed tools
    models/                  Tenant/Course/Learner/Enrollment/Certificate/AuditLog
    schemas/                 Validated API contracts
    routers/                 Thin HTTP handlers
    services/                Scoped queries, transactions and CSV preparation
  tests/                     SQLite and HTTP integration/workflow tests
  requirements.txt           Runtime dependency pins
  requirements-dev.txt       Runtime + pytest dependency pins
frontend/
  src/api/                   Typed HTTP clients
  src/components/            Tables, confirmation, export and status UI
  src/hooks/                 Request lifecycle and stale-response guards
  src/pages/                 Dashboard, list, bulk issue and details
  src/types/                 Shared TypeScript API types
  src/test/                  Component and API-client tests
AGENTS.md                    Engineering rules for AI tools
TESTING.md                   Commands, coverage map and test boundaries
```

Routers delegate business behavior to services. Tenant-owned request access uses a fixed-tenant SQLAlchemy session, explicit scoped predicates and composite database constraints. Maintenance tools use separate sessions. Tables are initialized explicitly rather than as an import side effect; the launcher invokes schema initialization only. Demo seed is a separate manual operation.

**Tenant selection is demo context, not authentication or authorization.** Users can choose either demo tenant. URL-scoped endpoints use the tenant path parameter; an optional `X-Tenant-ID` must agree or return 404. Request bodies cannot supply ownership or actor fields. The tenant directory exposes only root id/name/timezone metadata. Production must authenticate callers and verify membership; the demo actor `demo-admin-{tenant_id}` is not a verified identity.

## Demo data and database management

The default SQLite file is `backend/certificate_admin.db` (Git-ignored). A fresh seed creates:

| Data | Total | Per tenant |
| --- | ---: | ---: |
| Tenants | 2 | Sydney id 1 / Perth id 2 |
| Courses | 6 | 3 |
| Learners | 60 | 30 |
| Enrollments | 180 | 72 completed + 18 incomplete |
| Certificates | 108 | 45 valid + 9 revoked |
| Audit rows | 126 | 54 issued + 9 revoked |

Tenant zones are `Australia/Sydney` and `Australia/Perth` in `tenants.timezone`. Courses are Workplace Safety, Data Privacy and Leadership Essentials. Sample learners include Sydney Learner 01 and Perth Learner 01; serials include `OCEAN-DEMO-1-1-001` and `OCEAN-DEMO-2-1-001`. For each course, learners 19–24 are completed but initially unissued, and 25–30 are incomplete. Successful manual actions change counts, so the table is a **fresh-seed baseline**, not an expected result after every startup.

Initialize or rerun seed manually:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m app.database.init_db
.\.venv\Scripts\python.exe -m app.database.seed
.\.venv\Scripts\python.exe -m app.database.seed
Set-Location ..
```

Sequential seed reruns preserve existing records, serials, timestamps and revoked state. Conflicting tenant IDs belonging to non-demo data cause a visible failure rather than overwrite. Seed targets a dedicated demo database; it is not an import/synchronization service. `create_all` initializes missing tables and is not a schema migration mechanism.

To reset the **default** demo database, first stop both services. Keep a backup by moving the existing file, then initialize a new one:

```powershell
$backupName = 'certificate_admin.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.db'
Move-Item -LiteralPath '.\backend\certificate_admin.db' -Destination (Join-Path '.\backend' $backupName)
.\start.bat --prepare-only
```

This creates empty tables. To restore demo data, run the separate seed commands above. Run the move only when that file exists and no process is using it. This preserves the old database in the backup. For a custom DATABASE_URL, manage that explicitly selected file instead. Database/backup files are excluded from Git. Never remove `.git` or rewrite meaningful history as part of a reset.

For an isolated manual demo without resetting existing data:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
$env:DATABASE_URL = 'sqlite:///' + (Join-Path (Get-Location) 'tmp/manual-demo.db').Replace('\', '/')
.\start.bat --prepare-only
Push-Location backend
.\.venv\Scripts\python.exe -m app.database.seed
Pop-Location
.\start.bat
# After stopping, return this terminal to the default database:
Remove-Item Env:DATABASE_URL
```

SQLite can be inspected with a local database viewer or Python's sqlite3 module. Useful queries:

```sql
SELECT id, name, timezone FROM tenants;
SELECT tenant_id, status, COUNT(*) FROM certificates GROUP BY tenant_id, status;
SELECT tenant_id, action, COUNT(*) FROM audit_logs GROUP BY tenant_id, action;
PRAGMA foreign_key_check;  -- no rows means no violations
PRAGMA integrity_check;    -- expected: ok
```

## Configuration

Backend settings come from process environment variables; backend `.env` files are not automatically loaded.

| Variable | Default / meaning |
| --- | --- |
| DATABASE_URL | Absolute SQLite URL for backend/certificate_admin.db; custom parent directory must exist |
| CORS_ORIGINS | http://localhost:5173,http://127.0.0.1:5173; comma-separated allowed origins |
| VITE_API_BASE_URL | http://127.0.0.1:8000; frontend API base URL |

For frontend file configuration, copy `frontend/.env.example` to `frontend/.env.local` and restart Vite after editing it. Process VITE variables override file values. The one-command launcher uses fixed ports 8000/5173; its strict-port check prevents silently serving the app on another origin. Keep custom CORS/API settings consistent with those ports.

Timestamps are stored in UTC and restored as aware UTC datetimes by SQLAlchemy. API date rendering uses the tenant's IANA zone and includes the actual offset, including DST. The local-calendar-date SQLite function is registered by the application on each connection; it is not automatically available in an external SQLite viewer.

## Core API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /health | 200 with {"status":"ok"}; application liveness, not DB readiness |
| GET | /api/tenants | Demo id/name/timezone directory |
| GET | /api/tenants/{tenant_id}/courses | Owned course options |
| GET | /api/tenants/{tenant_id}/certificates | Search/filter/sort/page |
| GET | /api/tenants/{tenant_id}/certificates/export | Complete matching CSV |
| GET | /api/tenants/{tenant_id}/certificates/{certificate_id} | Owned detail, including revoked records |
| POST | /api/tenants/{tenant_id}/courses/{course_id}/issue | Retry-safe per-learner bulk results |
| POST | /api/tenants/{tenant_id}/certificates/{certificate_id}/revoke | Atomic status + audit; changed false on repeat |

List/export conditions: `search` (trimmed literal substring, max 200 characters), optional `status=valid|revoked`, `sort_by=learner_name|course_title|serial_number|issued_at|issue_date|status`, and `sort_order=asc|desc`. Defaults are empty search, all statuses and issued_at descending. Every sort uses id as a stable tie-breaker. `issued_at` sorts chronologically; `issue_date` sorts tenant-local calendar day then id.

List pagination defaults to `page=1&page_size=10`, with page 1–1,000,000 and page_size 1–100. Responses contain records, total, page, page_size, total_pages, tenant_id and tenant_timezone. An out-of-range valid page is empty while preserving total; no matches have total_pages 0. Export omits pagination and ignores page/page_size extras.

Bulk issue and revoke accept no body or `{}`. Extra body fields are rejected. Bulk results include total/issued/skipped/failed and a reason per learner. Only completed learners can get a new certificate. Existing and revoked records are skipped; lifetime tenant/course/learner uniqueness remains in force. Each new certificate and its issued audit commit together in an independent learner transaction. Earlier successes survive a later learner failure. Repeating after an uncertain response safely skips committed certificates; counts describe the current retry, not a replay of the original response.

Revoke returns `{certificate: <detail>, changed: true|false}`. State and its revoke audit commit atomically; repeating produces no additional state write/audit. Revocation preserves the serial, issue time, original certificate and uniqueness constraint. Missing/inaccessible resources return generic 404; invalid input returns 422. Recoverable export/revoke database errors return 503. Bulk learner failures appear in its 200 response summary, so callers must inspect failed outcomes.

CSV columns: **Learner Name, Course Title, Serial Number, Issue Date**. Output is UTF-8 BOM with standard quote/comma/newline escaping and tenant-local ISO timestamps. Formula-like text cells are apostrophe-prefixed; source data stays unchanged. The backend reads 500 rows at a time, spools beyond 1 MiB to disk, then streams 64 KiB chunks. Preparation errors return an error before attachment headers. Temp files close after completion/disconnect.

## Automated tests

The launcher installs test dependencies as well as runtime dependencies. From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\backend\.venv\Scripts\python.exe -m pip check
```

See [TESTING.md](TESTING.md) for the full coverage map, isolated-data design, report commands and limitations. The recorded suite has **82 pytest tests plus 48 additional subtests**, and **28 frontend tests**. Final delivery verification is recorded in [docs/VERIFICATION.md](docs/VERIFICATION.md). Earlier unittest cases are retained, but pytest is required to include the newer fixture-based tests.

Backend tests exercise real SQLite constraints, concurrent TestClient requests, lost responses after commits, atomic audit rollback, DST and a 25,000-row export. Frontend tests use Vitest/React Testing Library with mocked API boundaries plus actual client serialization tests. jsdom does not prove native browser focus trapping, layout or OS file saving; the manual walkthrough covers browser behavior separately. No line/branch coverage percentage is claimed.

## Manual verification walkthrough

Use a freshly seeded isolated database for these baseline expectations:

1. Open Dashboard and check Connected. On Certificates, select Sydney; its fresh register has 54 records. Change to Perth and verify Perth names, timezone and data, then return to Sydney.
2. Search Sydney Learner 01 (three records) and `OCEAN-DEMO-1-1-001` (one). Try an unmatched value, clear search, change sort direction/status/date basis and navigate to page 2.
3. Open Bulk Issue, choose Sydney / Workplace Safety. First request should issue six, skip 24 and fail zero. Repeat: zero issued, 30 skipped, zero failed. Processing must disable submission controls without invented progress percentages.
4. Open Certificates, search Sydney Learner 19, and open the Workplace Safety certificate serial. Check learner/course/tenant/local issue time. Click Revoke certificate, cancel and confirm it stays valid. Open confirmation again and confirm: status becomes revoked, the action disappears and the detail remains accessible.
5. Repeat Bulk Issue for the same course. The revoked certificate must be skipped, with its original serial and issue time preserved. It must not be recreated/reactivated.
6. On Certificates, apply a search/status filter and sort, then Export CSV. Confirm the filename identifies the tenant, the four headers are correct and all matching records are present, including records beyond the current page. Empty results export a header-only file. Open a cross-tenant detail URL and expect 404 without foreign record data.
7. Run the automated tests/build above and inspect final Git status before submission. Network failure, concurrency, audit fault and CSV injection/large-dataset cases are exercised automatically; do not add production debug switches to simulate them.

## Troubleshooting

- **Missing/wrong Python:** install Python 3.15 with the Windows launcher; check `py -3.15 --version`. A virtual environment using another version must be renamed/recreated deliberately; the launcher does not delete it.
- **Missing/old Node/npm:** install a compatible Node version and reopen the terminal. Check the version commands above.
- **Port in use:** stop the prior development terminal. Inspect `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen` and verify a process belongs to this project before stopping it. The launcher does not kill unrelated listeners.
- **Installation failure:** read the command and exit code printed by the launcher; check registry/network access and disk space, then rerun. Manifests/lockfiles trigger appropriate dependency refreshes. On Windows, stop Vite before npm ci.
- **Service not ready/crashed:** inspect `tmp/dev/backend.log` and `tmp/dev/frontend.log`. Startup failure stops the other child rather than leaving a partial launch.
- **Frontend connection error:** verify the health URL, VITE_API_BASE_URL and CORS origins; use Retry after correcting/restarting configuration.
- **SQLite locked:** close write transactions in database viewers and retry. Partial bulk successes are durable and safe to skip on retry. A response timeout does not cancel committed server work.
- **Seed conflict or stale schema:** use a dedicated demo database and back up/reset the selected file. Schema evolution needs a migration; startup does not destructively alter existing tables.

## Known limitations and future improvements

- Demo tenant/actor selection has no production login or membership authorization. Authentication and actor attribution are deployment prerequisites.
- SQLite is a single-writer database. Lock retries are bounded; persistent contention can require another attempt.
- Bulk issuance is synchronous, has no durable operation ID/job status and may stop after partial success if the process exits. Safe reruns recover remaining eligible learners.
- Export preparation needs temporary disk proportional to file size and delays the first download byte. The frontend fetch/Blob path buffers the file in browser memory, with a two-minute timeout. Derived local-date ordering can use SQLite temporary sort space, and preparation can delay writers.
- Substring case folding follows SQLite's ASCII behavior. List pagination is not a snapshot across separate requests during concurrent edits.
- create_all is initialization, not migration. Seed reruns are sequential developer tooling, not concurrent import jobs.
- No certificate PDF generation, email delivery, restore/reactivation action or production hosting is included. Potential follow-up work includes authenticated access, migrations, broader accessibility/browser automation and operational monitoring.

## Submission checklist

- [ ] Runnable repository link and meaningful Git history; review pending files and create the final commit yourself.
- [ ] README/start.bat/scripts, dependency pins/lockfile, seed tools, AGENTS.md and TESTING.md included.
- [ ] No virtual environments, node_modules, generated databases, caches, local secrets or temporary debug wrappers staged.
- [ ] Fresh startup, tests/build and tenant-to-export walkthrough checked; attach test evidence if useful.
- [ ] Full-session recording link and candidate-authored plan/instruction files supplied as required by the assessment.
- [ ] Candidate-only reflection and design answers completed independently and supplied by the candidate; this project documentation does not provide them.

Suggested final commit: `docs: finalize Windows startup and delivery guide`.
