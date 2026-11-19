# Chronicle

A local Python/Tkinter task timer and Timesheet/POL-R application using one
transactional SQLite database format: **schema 5**.

- Real projects nest without a fixed project-depth limit; tasks have three levels.
- Every task belongs to an explicitly chosen real project. No default project or
  virtual Unassigned container exists.
- New Task reviews name, complete project path/UUID and root/child context. A
  selected task creates an immediate child in its inherited project.
- Start/Stop/Switch, manual timed/date-only work, immutable corrections, direct and
  cumulative accounting, Move, Archive/Unarchive, unused-only Delete and templates.
- One Timesheet/POL-R window: Timesheet, Reconciliation, Saved Reports and
  Confirmation History. Saved reports remain available in SQLite without their
  external text file. Confirmation is explicit and absolute, never automatic.

Run `python run_chronicle.py` or Windows `scripts/run.ps1`. See [Running](RUNNING.md).
Use fresh databases; there is no migration, compatibility mode, import, database
backup/restore command or automatic weekly database creation/deletion.

[Requirements](docs/TIMESHEET_REQUIREMENTS.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Evidence contract](docs/EXPORT_EVIDENCE_CONTRACT.md) ·
[Tests](docs/TESTING_STRATEGY.md) · [Roadmap](docs/ROADMAP.md)

This source is for independent review. Linux/X11 tests do not establish native
Windows acceptance. No merge, release or pilot deployment is authorized.
