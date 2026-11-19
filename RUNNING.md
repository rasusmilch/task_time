# Running Chronicle

## Environment

Use Python 3.11 or later with tkinter/Tcl/Tk, SQLite 3.37 or later and tzdata 2026.5.
The application runs from source; no executable build or Windows qualification
collector is required. The optional development test dependency is pytest 8+.

```sh
python -m pip install --only-binary=:all: tzdata==2026.5
python run_chronicle.py
```

On Windows, `scripts/run.ps1` selects the project-local `.venv\Scripts\python.exe`
when present, otherwise Python from PATH. It launches the same application.
It does not install dependencies or alter execution policy.

## Dataset setup

First run offers explicit folder and timezone selection, Create and Open, Open
Existing Dataset and Cancel. Creation requires a new or empty folder. Every new
file is schema 5; no project or task is created automatically. An opened location
is remembered only after actual worker readiness. Cancel creates no dataset.

The suggested Windows folder is under LOCALAPPDATA/Chronicle/Data, with the launcher
selection alongside it. Unix uses XDG_DATA_HOME/Chronicle or the user's local data
folder. Choose a test-owned location for development.

Engineering source commands use the same current application:

```sh
python run_chronicle.py --data-dir /absolute/new-folder --create --timezone America/Chicago
python run_chronicle.py --data-dir /absolute/new-folder
```

There is no schema-version option, migration/import, inspection classifier or
backup/restore CLI. Unsupported files are not converted. Choose a fresh folder
rather than editing a schema marker. A second writer to the same dataset refuses.
Chronicle never creates databases weekly or deletes old databases automatically.

## Projects and tasks

Create a real root project first; New child project nests it under the selected
project. Empty projects remain visible. Project depth does not consume task depth.
New Task opens one owned dialog. Selecting a project prefills that exact project;
the root-task destination remains editable. With no Main selection, choose a
project explicitly. Nothing is selected by first-name, recency or a hidden default.
Duplicate names are distinguished by the complete ancestry and UUID.

Selecting an eligible task creates its immediate child and shows its real project
read-only. Three task levels are allowed; a level-three or running parent cannot
gain a child. Cancel/X/Escape closes the draft without creating a Request. With no
eligible project, Create Project closes the task dialog before opening the normal
project creation action; it does not create or retry a task automatically.

## Recording and organization

Start and Stop operate on eligible leaf tasks. Switch is one atomic close/open
operation. Double-clicking a leaf uses the same Start/Stop/Switch actions. Mini
uses the same selected/active task and worker; Show Main returns to the main view.
Manual timed work has genuine UTC endpoints; date-only work has an explicit civil
date and amount. Corrections retain immutable revisions. History shows direct work.

Task Individual is direct work; Task Cumulative includes task descendants once.
Project Direct sums directly assigned tasks; Project Cumulative also includes child
projects. Application Actual counts each task's direct work once. Do not sum all
project cumulative rows as an application total.

Task Move reviews a complete branch and real-project/eligible-parent destination.
Project Move is separate; its Root destination means organizational root. Both
preserve UUIDs/work. Archive is reversible and inherits without rewriting child
flags. Archived Items keeps ancestry context. Delete requires typed DELETE and a
complete unused-only review; protected work/report/confirmation references block it.
Templates remain reusable definitions; Apply creates fresh tasks in an explicitly
reviewed real project or eligible parent, without copying work.

## Timesheet and POL-R

Fresh opening is This week/All tasks, with no automatic Preview. Reconciliation is
available immediately without Preview or Save. Date/scope drafts require Apply /
Refresh. Return from a temporary confirmation review refreshes the last applied
scope and preserves unapplied drafts and semantic task/date selection.

Preview reads current facts. Save registers immutable SQLite evidence before text
publication. Saved Reports loads an existing registered report without registering
or saving it again, including after restart or when its external file is missing.
Frozen identity, labels, full-week basis, suggestions and bytes remain unchanged by
later work, rename or movement. File conflicts require explicit reviewed overwrite.

Source confirmation uses frozen suggestions: positive cells default checked, zero
unchecked; explicit zero is permitted. Unchecked cells retain their prior values.
Stale conflicts require individual acknowledgements. Manual confirmation needs no
report: Review current, then enter a nonnegative absolute quarter-hour total. It
replaces the stated total rather than adding an amount. Unknown differs from zero.
A committed batch UUID remains visible until explicit Return. A new confirmation
requires renewed review. Confirmation History is read-only. Confirmation never
changes Actual, timers or frozen reports and does not contact an external system.

Editable reviews use explicit Cancel/Defer; Close/X/Escape cannot silently discard
them. Pending/unverified requests keep exact ownership. Retry/Reconcile retains the
original Request. Uncertain Delete is never retried; presence is not proof of its
historical outcome. Exit normally after resolving or explicitly abandoning an
uncertain operation through its existing guarded action.

## Validation boundary

Use only disposable test data. Native Windows GUI/filesystem behavior remains
unverified by Linux tests. No historical focus runner qualifies this application.
See [Testing](docs/TESTING_STRATEGY.md) for current commands and evidence scope.
