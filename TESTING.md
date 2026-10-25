# Automated tests

Run these commands from the repository root in Windows PowerShell. Python 3.15 and Node.js >=22.12 are required by the configured toolchain; verification used Python 3.15.1, Node.js 24.22.1 and npm 11.19.1.

## Install test dependencies

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
```

The backend development requirements include the pinned runtime requirements plus pytest and its pinned dependencies. Frontend test packages are development dependencies recorded in package-lock.json. Stop Vite before reinstalling node_modules on Windows to avoid a native module file lock. Running tests does not require starting either application server.

## Execute

```powershell
# Backend: pytest collects existing unittest integration cases and native pytest workflows.
.\backend\.venv\Scripts\python.exe -m pytest -q

# Frontend: noninteractive Vitest run with React Testing Library and jsdom.
npm.cmd --prefix frontend test

# Typecheck all application/test sources and both Vite/Vitest configs, then build production assets.
npm.cmd --prefix frontend run build

# Optional backend source/dependency checks.
.\backend\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests
.\backend\.venv\Scripts\python.exe -m pip check
```

Use `npm.cmd --prefix frontend run test:watch` for interactive frontend development. Native pytest functions use fixtures, so the older unittest discovery command alone no longer runs the complete backend suite.

To reproduce machine-readable reports:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
.\backend\.venv\Scripts\python.exe -m pytest -q --junitxml=tmp/backend-step7.xml
npm.cmd --prefix frontend test -- --reporter=verbose --reporter=junit --outputFile=../tmp/frontend-step7.xml
```

`tmp/`, test databases, caches, reports and coverage output are ignored by Git. A failing test or typecheck must remain a failure; do not skip it or weaken assertions to obtain a passing result.

## Isolation

- Existing backend integration classes create fresh SQLite databases per test; the native pytest workflow fixture uses a file under pytest's `tmp_path`. Both patch tenant resolution and session creation to that isolated engine. Tests never seed, truncate or revoke certificates in the developer database.
- File-backed SQLite concurrency tests use independent connections and concurrent FastAPI TestClient requests. Barriers force competing operations to observe the same starting state before inserting/updating; actual SQLite unique constraint code 2067 is asserted. There is no application mutex standing in for database concurrency.
- Responses are deliberately discarded after actual endpoint commits for lost-response tests. Audit failures and writer locks are injected against real isolated databases. The CSV scale test generates 25,000 extra records and measures preparation allocations with tracemalloc.
- Frontend page tests render the real components, mock only their API boundary and interact through accessible labels/buttons. Separate API-client tests exercise real client code with mocked fetch Responses. An unexpected fetch rejects locally rather than contacting a developer service. Deferred promises let tests check pending, duplicate-click and stale-response behavior deterministically.
- jsdom lacks full native dialog and browser-download behavior. Setup shims only the dialog open/close DOM contract when missing; export tests observe anchor filename/click intent rather than saving files. These shims are test-only and never enter the application bundle.

## Behavioral coverage

| Feature | Backend evidence | Frontend evidence |
| --- | --- | --- |
| Tenant boundary | `test_database.py`, `test_core_workflows.py`: scoped reads/writes, both tenant directions, generic inaccessible 404, body ownership/actor rejection, unchanged foreign rows/audits, composite FK rejection | `CertificatesPage.test.tsx`: switching/stale response suppression; `ApiContracts.test.ts`: selected headers and rejection of foreign response records/courses |
| Certificate list | `test_certificate_list.py`: name/serial search, pagination, deterministic sorting, empty results, invalid parameters; export tests also verify shared filters/local-date ordering | `CertificatesPage.test.tsx`: loading/empty/error/retry, search/page reset, tenant switch, sorting/status/date parameters and detail links |
| Bulk issuance | `test_bulk_issuance.py`: completed eligibility, repeated/concurrent requests, actual unique conflicts, response loss, existing/revoked/incomplete skips, exact audit counts, atomic rollback, serial collisions and real writer locks; `test_core_workflows.py`: exact completed learner set and matching new audits | `BulkIssuePage.test.tsx`: disabled button/selectors, duplicate submission protection, issued/skipped/failed counts/reasons, unknown-response safe retry, selected course and register refresh |
| Details/revocation | `test_certificate_details.py`: required fields, Sydney/Perth/DST dates, repeated and concurrent revocation, immutable identity/history, atomic revoke audit, response loss, no reissuance and inaccessible 404 | `CertificateDetailPage.test.tsx`: required fields/local dates, confirmation/cancel without mutation, disabled in-flight controls, retained revoked details, read retry and status reload after uncertain mutation |
| CSV | `test_certificate_export.py`: tenant/filter scope, all rows rather than a page, all sort fields, headers/UTF-8/escaping/formula protection, DST/calendar dates, empty results, fetch failures/disconnect cleanup and 25,000-row bounded Python allocations; `test_core_workflows.py`: full multi-page list/export equivalence | `ExportCSV.test.tsx`: actual query serialization without pagination, filename/download intent, duplicate protection, error retry, obsolete export cancellation and corrupt response rejection; list test verifies applied conditions passed into export |
| Health/CORS | `test_health.py`: health contract, allowed/rejected origins and selector preflight | Existing dashboard manual checks from earlier steps; no extra browser claims are inferred from jsdom |

Tenant selection is a demo context, not authenticated access control. Tests validate isolation under a selected context and header/path agreement; they do not claim authentication or tenant-membership authorization.

## Step 7 recorded results

| Check | Passed | Failed/errors | Skipped |
| --- | ---: | ---: | ---: |
| pytest test functions/methods | 82 | 0 | 0 |
| pytest unittest subtests (additional) | 48 | 0 | 0 |
| Vitest / React Testing Library | 28 across 5 files | 0 | 0 |
| Frontend typecheck + production build | passed | 0 | 0 |

The pytest console reports `82 passed, 48 subtests passed`. Its JUnit suite counts both levels (130), while it contains 82 parent testcase elements; do not mistake this for 130 separate test functions. Frontend JUnit contains 28 testcase elements. Reports were actually generated at `tmp/backend-step7.xml` and `tmp/frontend-step7.xml`.

An initial frontend build found unsupported `exact` options in test-only getByRole calls. Those redundant options were removed, and the affected tests plus the production build passed afterward. No product/API implementation change was needed to make the suite pass.

A dependency recheck under the execution sandbox emitted temporary-directory cleanup warnings despite exit code 0. Repeating the pinned development-requirements check with TEMP/TMP pointed at the repository's ignored `tmp/install` directory completed without those warnings; pip check reported no broken requirements.

All requested automated checks executed; none were skipped or left unexecutable. This is behavioral coverage, not a measured line/branch coverage percentage. These suites are not a substitute for real-browser layout, focus trapping, browser save dialogs, physical network behavior or load testing. Real-browser download/confirmation checks from Steps 3–6 remain documented in README; Step 7 does not claim to have automated those OS/browser behaviors.
