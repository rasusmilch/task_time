# Chronicle current testing strategy

## Applicability

Only the current schema-5 application is supported. The clean replacement removes
historical task_timer, schema-specific runtime fixtures, candidate transaction adapters,
compatibility/backup/recovery suites and obsolete native qualification collectors.
Prior counts, archives, node authorizations and filesystem skip ledgers are not
current acceptance evidence. Git history retains the removed implementations.

## Current behavior coverage

| Selection | Purpose |
| --- | --- |
| [test_store.py](../tests/test_store.py) | Fresh exact schema/profile, complete verification, ownership, reopen, invalid current evidence and no-overwrite behavior. |
| [test_services.py](../tests/test_services.py) | Real projects, mandatory task membership, nested depth, movement, lifecycle, templates, timer and immutable work corrections. |
| [test_reporting.py](../tests/test_reporting.py) | Independent C–G values, frozen registration/readback, text publication, movement, explicit source/manual/zero confirmation, Delta, mismatches and reminders. |
| [test_transactions.py](../tests/test_transactions.py) | BEGIN IMMEDIATE, receipt identity, atomic rollback, lost acknowledgement, explicit reconciliation and no-retry Delete. |
| [test_evidence.py](../tests/test_evidence.py) | Corruption refusal and independent current receipt reconstruction without mutation implementation calls. |
| [test_worker.py](../tests/test_worker.py) | Actual worker/store ownership, serialized requests, semantic readiness, unresolved isolation and cleanup. |
| [test_ui.py](../tests/test_ui.py) | Actual startup handoff, explicit-project task dialog, modal/focus lifecycle, Main/Mini/Move/Apply/Archived and Timesheet/POL-R behavior on real Tk. |
| [test_startup.py](../tests/test_startup.py) | Cancel/error handling and actual source-launch child processes with fresh roots/workers. |
| [test_timekeeping.py](../tests/test_timekeeping.py), [test_polr_allocation.py](../tests/test_polr_allocation.py) | Useful retained pure integer/time/DST/allocation controls, free of obsolete runtime dependencies. |

[conftest.py](../tests/conftest.py) builds Requests over actual SQLiteStore and
RuntimeService. It never implements a transaction coordinator or synthetic readiness.
SQL corruption controls operate only on disposable files, restoring guards when the
test intends complete semantic rather than structural refusal.

## Commands and evidence

Use the existing supported interpreter, with source imports from this checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -q -ra -p no:cacheprovider -o addopts='' tests/ --basetemp /tmp/chronicle-unique-run --junitxml /tmp/chronicle-unique-run.xml
```

Use a fresh basetemp/JUnit for each invocation and retain raw logs, command, environment,
source identity, exits, counts and hashes outside the repository. Report overlapping
selections separately. Preserve preliminary failures and diagnostics. Compilation/import
checks complement behavior tests; they never substitute for execution.

## Connected and platform evidence

GUI claims require executed real Tk tests. Use an isolated managed Xvfb/Openbox display
when available, record DISPLAY/WM/Tcl/Tk/scaling and reap owned processes. A display
skip does not establish GUI success. Source-launch tests use independent processes.
No historical native focus driver or runner is current schema-5 qualification. Linux
SQLite and X11 passes do not establish Windows GUI/NTFS, actual Sleep or employer POL-R
policy acceptance. Native validation requires separately reviewed current evidence.
No system configuration, personal desktop or user database is changed for tests.
