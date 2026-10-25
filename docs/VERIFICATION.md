# Final delivery verification

Historical Step 8 evidence below reflects the original auto-seeding launcher. The subsequent requested change separates seeding from startup: `start.bat` now initializes tables only. The follow-up checks are recorded at the end of this file.

This record describes checks actually executed after Step 8 documentation/launcher cleanup. It is not a candidate reflection or an answer to the assessment's individual design questions.

## Environment and automated checks

Windows 11; Python 3.15.1; Node.js 24.22.1; npm 11.19.1. Runtime/test dependency versions were checked against the committed requirements and frontend lockfile.

| Check | Observed result |
| --- | --- |
| Backend pytest | 82 passed, 48 additional subtests passed; 0 failed/errors, 0 skipped |
| Frontend Vitest/RTL | 28 passed across 5 files; 0 failed, 0 skipped |
| TypeScript + Vite production build | Passed; application/test sources checked |
| Python compileall for scripts/backend/tests | Passed |
| pip check | No broken requirements |
| SQLite final workflow database | foreign_key_check: no violations; integrity_check: ok |

Commands run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q --junitxml=tmp/backend-final.xml
npm.cmd --prefix frontend test -- --reporter=verbose --reporter=junit --outputFile=../tmp/frontend-final.xml
npm.cmd --prefix frontend run build
.\backend\.venv\Scripts\python.exe -m compileall -q scripts backend/app backend/tests
.\backend\.venv\Scripts\python.exe -m pip check
```

The generated XML reports are in the ignored `tmp/` folder. Pytest's JUnit aggregate includes parent tests and subtests (130); its console reports 82 parent tests plus 48 subtests. See TESTING.md for interpretation and coverage boundaries.

## Launcher/installation checks

1. Inspected the development ports before starting; no existing development listeners needed termination.
2. Ran `start.bat --prepare-only` in the existing project. It verified Python/Node/npm, checked backend pins/imports, installed frontend dependencies from the lockfile, and ran idempotent initialization/seed. Existing developer data was preserved rather than reset.
3. Created a disposable source-only copy without `.venv` or node_modules. Ran its `start.bat --prepare-only`: a new Python 3.15 environment and all backend/frontend dependencies were installed successfully, then a fresh SQLite demo was created with 2 tenants, 6 courses, 60 learners, 180 enrollments, 108 certificates and 126 audit rows.
4. In that disposable copy, backed up its SQLite file with Move-Item and ran preparation again. Both the backup and the new database existed; the new database returned the fresh seed counts. No developer database was moved/deleted.
5. Ran the documented `start.bat` in the actual repository, with `DATABASE_URL` set to `tmp/final-delivery-check.db` for a clean, isolated manual walkthrough. No HTTP fault-injection wrapper was used. The launcher reached READY on ports 8000/5173; health returned ok, frontend returned HTTP 200, both demo tenants were present and Sydney initially had 54 certificates.
6. Ran a second launcher while those ports were occupied. It returned exit code 1 with an explicit port error and left the original services running. This was an intentional negative test, not an unresolved startup failure.
7. After completing the browser walkthrough, intentionally stopped only the launcher's verified frontend PID. The supervisor printed log tails, returned exit code 1 and stopped its backend tree. This confirmed that unexpected service failure is visible and does not leave a partial launch.
8. Restarted with the same isolated database. Preparation retained the resulting 114 certificates/133 audits and reached READY without reinstalling unchanged dependencies. Pressed Ctrl+C: cleanup ran, both ports were released, then the Windows batch confirmation was answered Y. The interrupted batch exit is expected, not a test failure. README documents that prompt.

## Actual browser workflow

Used the app started by start.bat on its normal documented ports, with the separate verification database above:

- Dashboard displayed Connected.
- Selected Perth and observed its metadata/data, then selected Sydney. Name search for Sydney Learner 01 returned three original certificates.
- Chose Sydney / Workplace Safety in Bulk Issue. First request returned 6 issued, 24 skipped, 0 failed; immediate repeat returned 0 issued, 30 skipped, 0 failed.
- Searched Sydney Learner 19 and opened the newly issued certificate (id 109) from its serial link. Its local issue time was shown in Australia/Sydney with +11:00.
- Opened revocation confirmation and canceled: the UI remained valid. Reopened and confirmed: the UI changed to revoked, retained the original fields and removed the action.
- Repeated bulk issuance for the same course: 0 issued, 30 skipped, 0 failed, including the revoked certificate. No replacement/reactivation occurred.
- Filtered Certificates by Sydney Learner 19 / revoked, then downloaded an actual CSV through the browser. Read the saved file back with Python csv.DictReader: exactly one row, the four required headers, correct learner/course, the original serial and the tenant-local issue timestamp.
- Queried the isolated SQLite database afterward: certificate 109 remained revoked with that serial, the original issue timestamp remained UTC, and exactly one revoke audit existed. Foreign-key/integrity checks passed.

The manual workflow wrote only the separate verification database; automated tests used their isolated databases. The user's existing development database was not reset or used for the mutating walkthrough.

## Cleanup and delivery status

- Removed the unused placeholder page and the old ignored browser fault-injection wrappers/mode files from previous verification work.
- Reviewed ignore rules for virtual environments, node_modules, caches, generated databases/backups/logs, local environment files and key material. Seed scripts, AGENTS.md and frontend/.env.example remain included.
- Retained useful verification reports/screenshots in ignored temporary storage. Temporary bootstrap source copies are disposable; they are not submission files.
- No new business feature, schema migration, dependency-version change or automatic Git commit was introduced in Step 8. Meaningful existing history and the candidate's design document were preserved.
- Final services were stopped after verification to release the ports. Start the application with `.\start.bat` when ready to review.

## Remaining limitations

Demo tenant/actor context is not authenticated membership access. SQLite concurrency and synchronous batch work remain bounded by the implemented retry behavior. CSV preparation uses temporary disk, and the browser Blob path buffers the file. The test suite's jsdom shims do not replace real-browser layout/focus/download checks. Complete technical limits and submission checklist are in README.md; candidate-only personal answers and the recording link must be supplied by the candidate.

## Follow-up: separate seed from startup

Changed scripts/dev.py to call initialize_database() only; both normal startup and --prepare-only leave data insertion to the explicit app.database.seed command. README and AGENTS.md now document this separation. Existing databases are not reset.

Executed start.bat --prepare-only with DATABASE_URL pointing at an isolated tmp/start-no-seed-check.db. All six tables existed and each had zero rows. Executed the documented seed module twice from backend/: both runs returned 2 tenants, 6 courses, 60 learners, 180 enrollments, 108 certificates and 126 audits. Repeated launcher preparation and checked those same counts remained unchanged. Python compileall for scripts and git diff --check passed. These follow-up checks exercise preparation/data separation; the services were not restarted and the full frontend suite/build was not repeated for this launcher-only change.

Database regression command: `python -m pytest backend/tests/test_database.py -q` using backend/.venv. The initial restricted run stalled and was interrupted; rerunning outside that restricted context with local TEMP/TMP completed: 25 passed and 10 subtests passed in 4.80s, no failures or skips.
