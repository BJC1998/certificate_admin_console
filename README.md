# Certificate Admin Console

Steps 1–7: FastAPI health endpoint, React/TypeScript/Vite dashboard, SQLAlchemy/SQLite schema, tenant-scoped certificate listing/details, reliable bulk issuance/revocation, filtered CSV export, repeatable demo data and automated backend/frontend tests. Certificate serial links open details with confirmed revocation; Bulk Issue supports individual outcomes and safe retries; Export CSV downloads all matching records.

## Prerequisites

- Python **3.15**, as requested for Step 1. Verify with `py -3.15 --version`.
- Node.js 22.12+ (including the Step 7 test tooling), npm, Windows PowerShell. Verified with Node.js 24.22.1 and npm 11.19.1.
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

Open http://127.0.0.1:5173. The dashboard requests http://127.0.0.1:8000/health directly and displays checking, connected or error status, with a manual recheck button. Navigation includes the Certificates register and Bulk Issue page. Use Ctrl+C in each terminal to stop.

Health contract: `GET /health` returns HTTP 200 and `{"status":"ok"}`. This checks application liveness only, not database connectivity. API documentation: http://127.0.0.1:8000/docs.

## Configuration

Backend variables are read from the process environment; backend `.env` files are not loaded automatically:

- `DATABASE_URL`: defaults to an absolute path to `backend/certificate_admin.db`, independent of the terminal's working directory. Only SQLite URLs are supported. The engine is lazy; startup does not create a database or any tables.
- `CORS_ORIGINS`: comma-separated origins, default `http://localhost:5173,http://127.0.0.1:5173`. GET and POST are allowed, including the `X-Tenant-ID` selector header; future endpoints must extend methods as needed.

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

At Step 3 completion, bulk issuance, details, revocation and export were deferred. Demo selection is not access authentication; SQLite's default case-insensitive substring behavior handles ASCII case folding, not full Unicode case folding. Offset pagination is not a snapshot across concurrent data changes. No Git commits were created.

## Step 4: bulk issuance API and transactions

- `GET /api/tenants/{tenant_id}/courses` returns `[{id, tenant_id, title}, ...]`, scoped to the selected tenant and sorted by title/id.
- `POST /api/tenants/{tenant_id}/courses/{course_id}/issue` accepts no body or `{}`. Extra body fields (including tenant_id and actor) return 422. An inaccessible course or a conflicting path/header tenant returns 404 before processing.
- A successful HTTP response is 200 even when some learner operations failed: inspect `issued`, `skipped`, `failed` and the individual `results`. Response also contains `tenant_id`, `course_id`, `total`. Each result contains `learner_id`, `learner_name`, `outcome`, `reason`, nullable `certificate_id` and `serial_number`.
- Outcomes cover every enrollment in the course, including incomplete learners as skipped. Within each learner transaction the current enrollment is checked again; only completed enrollments can receive a new certificate. Existing valid and revoked certificates are returned as skipped and remain unchanged.

Transaction sequence: validate tenant/course, materialize the tenant-scoped enrollment/learner snapshot, end that read transaction, then process each learner in an independent `session.begin()` transaction. Flush the certificate first, flush its issuance audit second, commit, then report issued. A failure in audit insertion rolls back that learner's certificate too; it does not affect committed learners. Transactions, not savepoints nested inside one batch transaction, provide the isolation between learner outcomes here.

The existing unique constraints on certificate identity, serial and certificate audit action are the final race protection. Check-before-insert is only an optimization. Following an IntegrityError, the transaction is rolled back and a new tenant-scoped read checks for a winning certificate: only an exact tenant/course/learner match can become skipped. Other integrity failures return failed rather than a false success. Serials use UUID4 values prefixed with `OCEAN-`; the global serial unique constraint is still enforced.

SQLite BUSY/LOCKED errors roll back and retry that learner in a new transaction, at most four attempts, with 25/50/100 ms backoffs in addition to SQLite's connection busy timeout. Persistent contention returns `database_busy_retry_safe`; other database failures return safe reason codes without SQL exception contents. The client can repeat the whole course operation to retry remaining learners.

Reason codes: `certificate_and_audit_committed`, `already_issued`, `previously_revoked`, `enrollment_incomplete`, `enrollment_no_longer_available`, `database_busy_retry_safe`, `database_error_retry_safe`, `database_integrity_error_retry_safe`.

Audit actor is assigned by the server as `demo-admin-{tenant_id}`. It represents demo context, not an authenticated administrator. No schema migration or new dependencies are needed for Step 4.

Example commands (these intentionally issue certificates in the configured database):

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/tenants/1/courses'
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/tenants/1/courses/1/issue'
# Safe repeat: previously committed certificates are skipped.
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/tenants/1/courses/1/issue'
```

## Step 4: frontend and verification

Open `http://127.0.0.1:5173/#bulk-issue`, select tenant/course and click Bulk Issue. A synchronous submission guard and disabled controls prevent duplicate clicks in flight. Processing text shows no invented percentage. Completion displays summary counts and per-learner reasons, refreshes the selected tenant's certificate register, and preserves tenant selection when opening Certificates. Failed learner outcomes offer Retry safely. An unconfirmed response explains that the server may already have committed some/all work and offers Safe retry. The browser has a 60-second issuance response timeout and a separate ten-second register-refresh timeout; leaving the page does not undo committed work.

Real automated verification uses separate temporary file-backed SQLite databases, independent connections and actual FastAPI HTTP requests. Run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_bulk_issuance.py -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests
.\backend\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend run build
```

Verified results:

- **50 backend tests passed**, including nine new bulk-issuance tests and all 41 previous regressions. Backend compilation and dependency checks passed; TypeScript/Vite build passed.
- Fresh seeded course: first request issued 6 / skipped 24 / failed 0; repeat issued 0 / skipped 30 / failed 0. The final database had 24 course certificates and exactly 24 issuance audits. Three revoked certificates and six incomplete learners were skipped.
- Two simultaneous HTTP requests used a barrier to force both to observe no certificate for the same new learner before inserting. Combined issuance was exactly six, final certificates/audits were 24/24, and the actual SQLite `SQLITE_CONSTRAINT_UNIQUE` code 2067 was observed. There is no application mutex serializing these requests.
- Dropping the entire response after the endpoint completed its commits left 24 certificates/audits. Retry issued zero and preserved 24/24.
- Injected audit failure: five learners committed, one certificate and its audit rolled back; retry issued only that missing one. A forced serial collision was reported failed rather than falsely skipped.
- A real held SQLite writer lock produced retryable failed outcomes without partial certificate/audit writes; retry after releasing the lock issued the six eligible certificates.
- Another tenant's course was denied; client ownership/actor injection was rejected. Empty courses and POST CORS preflight passed.
- Browser verification on temporary ports 5174/8001 used a separate seeded database, leaving the user's database untouched. During a delayed response the issue button and selectors were disabled; a second click was blocked and the server received only one POST. Result summary showed 6 issued / 24 skipped / 0 failed, individual outcomes were displayed and the register refreshed to 60 tenant records.
- The browser also received a simulated 503 replacing a successful committed response. It displayed the uncertain-outcome warning and Safe retry; retry showed 0 issued / 30 skipped / 0 failed and the refreshed register contained 66 Sydney records. Switching to Perth cleared the prior results and loaded only Perth courses. Issuing there showed 6/24/0, refreshed Perth to 60 records, and View certificates retained Perth and displayed those new records.

Limitations: issuance is synchronous and outcomes are returned at the end, not streamed. A process interruption can leave a partially completed batch; repeating it safely skips durable successes. There is no persistent operation/request ID or exact response replay, so a retry's counts describe that retry and can differ from the original. SQLite is a single-writer database; persistent lock contention can require another user retry, and a response timeout does not cancel server work. There are no emails, job queues, authenticated actor identity, details, revocation or export in Step 4. No Git commits were created.

## Step 5: certificate details and revocation

- `GET /api/tenants/{tenant_id}/certificates/{certificate_id}` returns the existing certificate record fields plus `learner_id`, `course_id`, `tenant_name`, `tenant_timezone`. The record includes `id`, `tenant_id`, `learner_name`, `course_title`, `serial_number`, tenant-local ISO `issued_at` with offset, and `status` (`valid` or `revoked`). All joins and lookups are scoped to the selected tenant. Stored UTC timestamps are untouched.
- `POST /api/tenants/{tenant_id}/certificates/{certificate_id}/revoke` accepts no body or `{}` and returns `{certificate: <detail>, changed: true|false}`. First revocation returns true; repeated/already-revoked requests return false. Extra ownership/actor body fields return 422.
- Missing and inaccessible records return the same generic 404. A conflicting optional `X-Tenant-ID` header also returns 404. Invalid certificate IDs return 422. Database errors that prevent confirmation return 503 with Retry-After; the client should reload status or retry safely.

The revoke transaction loads the owned certificate, changes valid to revoked, inserts its revoke audit, flushes, builds the response, commits, then returns success. It never deletes or replaces a certificate, updates its serial/issue time, or changes the lifetime unique constraint. The unique `(tenant_id, certificate_id, action)` audit constraint handles simultaneous revokes: a losing transaction rolls back and returns unchanged only after checking the committed revoked state and its audit. SQLite BUSY/LOCKED retries use up to four fresh transactions. Other integrity failures are not reported as success. Existing revoked records are returned unchanged without rewriting history.

In the Certificates table, click the serial link to open `#certificates/{tenant_id}/{certificate_id}`. Dates are explicitly rendered in the record's IANA timezone, with the ISO offset also visible. Only valid certificates show Revoke certificate. The native modal dialog identifies the serial and learner, initially focuses Cancel, and requires Confirm revocation to send the POST. Cancel/Escape before submission closes the dialog with no request. During submission, confirmation/cancellation controls are disabled to avoid duplicate requests. On success, the displayed status updates, the revoke action disappears, and the detail URL remains usable. After an unconfirmed mutation response, the page explains the possible committed result and offers Reload certificate; there is no optimistic revoked status before a confirmed response.

Verification commands (repository root):

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_certificate_details.py -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests
.\backend\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend run build
```

Verified results:

- **59 backend tests passed** (nine new detail/revoke tests plus all 50 earlier regressions); backend compilation, dependency checks, TypeScript checking and Vite production build passed.
- Valid details and known Sydney +10/+11 and Perth +08 timestamps matched expected values. Invalid/missing/cross-tenant detail and revoke requests were rejected.
- First revoke and repeat emitted exactly one certificate UPDATE and one UTC revoke audit, with unchanged id/serial/issue time and all 108 seeded certificates retained. An already-revoked seed record remained unchanged.
- Concurrent HTTP revokes used separate connections and a barrier forcing both to read valid state before writing. The test observed real SQLite unique conflict code 2067; responses had exactly one `changed: true` and one `changed: false`, with one audit.
- Injected revoke-audit failure returned 503 and left the certificate valid with no revoke audit. A subsequent retry succeeded. Discarding the response after a committed revocation was safe to repeat without duplicate audit entries.
- Bulk issuance after revocation returned skipped/previously_revoked for that learner and retained the original certificate. No replacement or reactivation occurred.
- Browser verification used temporary ports 5174/8001 and a separate demo database. Opening from the list displayed the correct learner/course/local issue date. Cancel sent no revoke POST; a direct database check confirmed valid status and zero revoke audits. Confirm updated the page to revoked, removed the action and preserved the original fields. A real repeated HTTP POST returned `changed: false`, and the isolated database still contained one revoke audit.
- A simulated detail GET 503 showed explicit error/Retry; restoring the API and retrying displayed the revoked detail again. A cross-tenant detail URL showed 404 without exposing the record. The browser also displayed a loading state during a delayed GET.

No schema migration or new dependencies were needed. Demo tenant selection and `demo-admin-{tenant_id}` remain unauthenticated context. The detail GET timeout is ten seconds; revoke response timeout is thirty seconds, and a timeout cannot undo committed server work. There is no restore/reactivation action or CSV export in Step 5. No candidate-only answers were modified and no Git commits were created.

## Step 6: filtered CSV export

`GET /api/tenants/{tenant_id}/certificates/export`

The static export route is registered before the integer detail route. It accepts the same applied search/status/sort conditions as listing:

| Parameter | Default | Values |
| --- | --- | --- |
| search | empty | Trimmed literal learner-name or serial substring, maximum 200 characters |
| status | omitted | valid or revoked; omit for all statuses |
| sort_by | issued_at | learner_name, course_title, serial_number, issued_at, issue_date, status |
| sort_order | desc | asc or desc |

List and export both use `services/certificate_queries.py` for joins, tenant filters, escaped search, optional status and stable ordering. The list additionally applies pagination; export never applies it (page/page_size query extras are ignored). Every sort has a certificate-id tie-breaker in the same direction.

`issued_at` sorts chronologically. `issue_date` sorts by the tenant-local calendar date, then id, so records on the same local day can intentionally differ from chronological order. Each application SQLite connection registers `tenant_local_date`, which converts stored UTC through the tenant's IANA zone. This function is application-side connection configuration, not a stored function available automatically in an external SQLite viewer. No schema migration is needed. The list UI offers a Status filter and Date ordering selector; its date column toggles direction using the chosen date basis.

CSV columns are exactly **Learner Name, Course Title, Serial Number, Issue Date**. Dates are tenant-local ISO 8601 timestamps including offset (and fractional seconds when present). Output uses UTF-8 with BOM for Windows spreadsheet compatibility and CRLF records. Standard csv.writer escaping preserves Unicode, commas, quotes and embedded newlines. Text cells beginning with formula triggers (=, +, -, @), including after leading whitespace/BOM, and cells beginning with tab/CR/LF are prefixed with an apostrophe. This intentionally changes those dangerous text representations to prevent formula interpretation; source records are unchanged.

## Step 6: export strategy and failure handling

The backend selects primitive scalar columns, opens one ordered cursor and consumes `yield_per=500` / 500-row partitions. It does not load ORM entities or use an OFFSET-based export loop. A single SQLite cursor provides a consistent data read for that SELECT, avoiding batch-boundary skips/duplicates caused by multiple independently paged queries.

Rows are encoded in batches into a `SpooledTemporaryFile`: at most 1 MiB remains in that in-memory spool; larger files roll to the OS temporary directory. Preparation completes before HTTP headers, then releases the database transaction and sends 64 KiB file chunks. This keeps Python application allocations bounded by the spool/batch/chunk sizes rather than all matching rows, and avoids holding the database read open for a slow network client. The response closes the file on completion, failure or disconnect.

Database/temporary-file preparation failures return 503 with Retry-After instead of a partial CSV attachment. Missing tenants return 404; malformed/out-of-range tenant ids, invalid sort/status or overlong search return 422; conflicting optional X-Tenant-ID returns 404. An empty result is a successful CSV containing only the header. Responses include an informative ASCII attachment filename with tenant name/id, all/filtered and tenant-local generation timestamp, Content-Length, no-store and nosniff. CORS exposes Content-Disposition so the frontend uses the server's filename.

In the list, Export CSV exports the **applied** search and status filter plus current sort/tenant, irrespective of the displayed page. Typing in the search box does not apply it until Search/Enter, matching the table behavior. The button disables during preparation/download, errors offer Retry CSV export, and successful responses trigger an informative filename download. Changing the selected tenant/search/status/sort cancels an obsolete in-flight export. The browser checks status, content type and expected byte length before starting a download; its message says Download started rather than claiming the user saved the file.

Example commands (PowerShell, no page parameters):

```powershell
Invoke-WebRequest 'http://127.0.0.1:8000/api/tenants/1/certificates/export' -OutFile certificates-sydney.csv
Invoke-WebRequest 'http://127.0.0.1:8000/api/tenants/1/certificates/export?search=Sydney%20Learner%2001&status=valid&sort_by=issue_date&sort_order=asc' -OutFile certificates-filtered.csv
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_certificate_export.py -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests
.\backend\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend run build
```

Verified results:

- **72 backend tests passed**, including 13 new export tests and all 59 prior regressions. Backend compilation, dependency checks, TypeScript checking and Vite production build passed; no dependencies were added.
- Unfiltered seeded export included all 54 certificates for the selected tenant even with page=2/page_size=1. Name search produced three rows, exact serial search one, and revoked filter nine. Shared list/export counts and serial order matched for combined filters and all six sort fields in both directions.
- CSV headers/byte length, UTF-8 BOM, Chinese text, quoted commas/newlines, formula protection, empty results, invalid inputs and cross-tenant isolation passed.
- Exact Sydney DST boundary values exported as `2026-10-04T01:59:00+10:00` and `2026-10-04T03:00:00+11:00`; Perth +08 and local-calendar-date/id ordering were verified separately from chronological ordering.
- A simulated database fetch error after a batch had been processed returned 503 without a CSV attachment and closed the spool. Failure during tenant lookup also returned 503. A simulated disconnected HTTP send closed the prepared file.
- **25,000 generated rows** exported to a **15,275,055-byte CSV** with 500-row reads and disk rollover. The full-suite run measured **3,067,756 bytes peak Python allocations** with tracemalloc (the focused run measured 3,079,750). This measures Python allocations during preparation, not total process RSS or SQLite's native sort/cache allocations. The resulting CSV was parsed row by row to confirm all 25,000 records.
- Browser verification used a separate seeded database and temporary ports 5174/8001. Export while viewing page 2 downloaded a real file with 54 rows and 54 unique serials. A combination of learner search, valid status and local calendar-date sorting was sent without pagination parameters. A simulated 503 displayed the download error; retry downloaded a real three-row filtered file in the expected order. The saved files' headers and contents were read back and checked.

Limitations: the backend deliberately prepares the complete temporary file before sending the first download byte, so preparation needs O(file size) temporary disk capacity and large exports can wait before downloading. The SQLite read cursor can delay concurrent writers during preparation, and derived local-date sorting can require database temporary sorting space. The frontend currently uses fetch/Blob and therefore buffers the completed file in browser memory; backend bounded-memory behavior does not imply bounded browser memory. A two-minute browser timeout may require retry for very large/slow exports. There is no background export queue, resumable download or production authentication. No source data was modified, no candidate-only answers were changed and no Git commits were created.

## Step 7: complete automated suite

See [TESTING.md](TESTING.md) for installation, isolation design, coverage mapping and result interpretation. Run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
.\backend\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

Verified: **82 pytest tests plus 48 additional unittest subtests passed; 28 frontend tests across five files passed; zero failed/errors and zero skipped.** Frontend TypeScript and production build also passed. Existing unittest tests are retained and collected by pytest; ten additional pytest cases cover cross-interface tenant isolation, forbidden mutation body fields, exact completed-learner issuance/audit correspondence and full filtered pagination/export equivalence. The frontend uses Vitest, React Testing Library, user-event, jest-dom and jsdom, including separate real API-client contract tests.

The first build identified redundant unsupported test query options; those test-only type errors were fixed and the frontend suite/build rerun successfully. No product/API implementation rewrite, new business feature, production data mutation or Git commit was made for Step 7. All requested automated tests executed. Native modal focus behavior, OS file saving and real-browser layout are outside jsdom's capabilities and are not claimed as automated end-to-end coverage.
