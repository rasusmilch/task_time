# Changelog

## Unreleased

- Replace the multi-generation development tree with one schema-5 Chronicle
  application. Consolidate the accepted SQL, domain algorithms and independent
  semantic checks into current modules; remove task_timer, historical schema paths,
  test bridges/adapters, compatibility/backup/private-recovery machinery and obsolete
  qualification scripts. Integrate the existing worker/store/startup and nested Tk
  views directly, with explicit real-project New Task, inherited child ownership and
  no Unassigned destinations. Preserve recording, accounting, templates, immutable
  Timesheet/Save and absolute POL-R workflows, validated by current production-component
  and managed-Tk tests. No migration, automatic data deletion, Windows qualification,
  release or pilot authorization is implied.
