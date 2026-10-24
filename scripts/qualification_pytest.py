"""Private Windows qualification collector/plugin; never an application import.

The PowerShell entry point owns presentation. This helper owns bounded test I/O,
pytest events, explicit selection, Windows Job Objects and isolated evidence.
Portable tests exercise these contracts; native Windows execution is separate.
"""
from __future__ import annotations

import argparse
import ast
import codecs
from collections import Counter
from contextlib import closing
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass, field
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback
import zipfile

SCOPES = ('MetadataProbe', 'Critical', 'Storage', 'Extended')
LIMITS = dict(collection=90, test=120, phase=900, warning=30, cleanup=5)
# Only this genuine-spill family has a reviewed longer per-node allowance.
LONG_TESTS = {'test_genuine_hot_journal_native_startup_preserves_all_committed_evidence': 240}
CALLBACKS = {
    'test_backup_ui.py::test_owned_callback_chooser_cancel_reentry_and_no_constructor_io':
        'Owned asksaveasfilename is locally doubled by this test to return empty/cancel; all other dialogs forbidden.',
    'test_backup_ui.py::test_backup_failure_retains_path_primary_diagnostic_stale_completion_and_explicit_validation':
        'No native dialog is requested; destinations are explicit callback drafts; all dialogs forbidden.',
}
SAFE_FIXTURES = frozenset(('request', 'tmp_path', 'tmp_path_factory', 'monkeypatch', 'capsys',
                          'store', 'service', 'task', 'make_request', 'registered', 'rich', 'image', 'hot_dataset'))
CRITICAL = {
    'test_file_observations.py': None,
    'test_schema.py': {'test_fresh_profile_and_reopen', 'test_unknown_normal_open_does_not_add_files',
                       'test_startup_rechecks_candidate_after_ownership_before_adoption'},
    'test_timesheet_files.py': {'test_fresh_status_exact_publication_matching_reuse_and_no_work_changes',
        'test_stable_content_conflict_requires_exact_single_call_observation',
        'test_final_reinspection_checks_bytes_when_all_target_metadata_is_unchanged',
        'test_final_reinspection_preserves_read_error_and_immediate_metadata_guard'},
    'test_backup_restore.py': {'test_minimal_backup_validate_restore_without_rich_report_fixture'},
    'test_interruptions.py': {'test_genuine_hot_journal_native_startup_preserves_all_committed_evidence'},
}
# Frozen, reviewable function allowlist below. New functions are NOT RUN until audited.
STORAGE = {'test_backup_restore.py': ('test_consistent_snapshot_full_evidence_restore_reopen_and_independent_future_work',
                            'test_minimal_backup_validate_restore_without_rich_report_fixture',
                            'test_backup_never_overwrites_objects_or_dataset_aliases',
                            'test_invalid_path_never_creates_output',
                            'test_missing_parent_and_unresolved_transaction_refuse',
                            'test_bounded_faults_keep_primary_do_not_roll_back_final_and_keep_source',
                            'test_cleanup_failure_is_secondary_not_primary',
                            'test_restore_existing_targets_never_change',
                            'test_invalid_source_is_read_only_and_target_not_reserved',
                            'test_changed_source_after_staging_refuses_restore',
                            'test_worker_backup_uses_existing_owner_serialization_and_shutdown',
                            'test_cli_verify_restore_no_display_source_unchanged_reopen',
                            'test_cli_invalid_combinations_before_root_worker_or_files',
                            'test_cli_invalid_source_nonzero_no_target',
                            'test_actual_staging_boundaries_abort_without_false_success',
                            'test_unowned_stage_and_unexpected_restore_objects_are_never_deleted',
                            'test_worker_refuses_backup_until_exact_unverified_mutation_reconciles',
                            'test_verification_and_restore_never_construct_root_app_or_worker',
                            'test_wal_rejection_does_not_create_sidecars',
                            'test_restore_refuses_explicit_network_target_before_reservation',
                            'test_backup_after_stop_switch_and_correction_preserves_all_receipts',
                            'test_real_sqlite_progress_interruption_has_no_published_partial_image',
                            'test_stage_changes_before_publication_and_source_stability_reject',
                            'test_unsuitable_source_does_not_reserve_restore_target',
                            'test_stage_name_collision_never_writes_or_cleans_final_destination'),
 'test_bootstrap.py': ('test_separate_process_second_owner_refused',
                       'test_directory_alias_second_owner_refused',
                       'test_normal_restart_and_crash_keep_same_active_identity',
                       'test_launcher_requires_explicit_path_without_touching_home'),
 'test_dataset_compatibility.py': ('test_real_images_classify_and_preserve_source_and_external_evidence',
                                   'test_source_launcher_headless_status_and_no_state_writes',
                                   'test_startup_backup_and_restore_refuse_before_adoption_or_target_reservation',
                                   'test_cli_invalid_combinations_cannot_start_or_create',
                                   'test_headless_inspection_constructs_no_tk_app_worker_or_lock',
                                   'test_unsafe_paths_never_open_sqlite_or_change_objects',
                                   'test_invalid_or_network_path_is_not_resolved_or_created',
                                   'test_outstanding_sidecar_is_retained_and_not_recovered',
                                   'test_wal_header_refuses_before_sqlite_connection_and_keeps_directory',
                                   'test_original_faults_never_claim_completion_or_mutate',
                                   'test_primary_validation_error_survives_failed_readonly_close_without_retry',
                                   'test_change_during_inspection_rejects_without_cleaning_changed_source',
                                   'test_inspection_uses_one_readonly_query_only_connection_and_full_gate',
                                   'test_cli_reporting_failure_is_nonzero_and_retains_original_diagnostic',
                                   'test_cli_unsuitable_explicit_path_fails_without_creation',
                                   'test_killed_inspection_leaves_no_transformation_and_next_owner_works',
                                   'test_crashed_transaction_journal_is_not_recovered_or_deleted_by_inspector',
                                   'test_rich_current_inspection_backup_restore_reopen_and_independent_work',
                                   'test_same_version_literal_change_is_not_normalized_into_supported_schema',
                                   'test_layout_refusal_keeps_original_diagnostic_when_close_also_fails',
                                   'test_busy_cold_image_returns_unavailable_without_writable_recovery'),
 'test_file_observations.py': ('test_raw_six_field_contract_and_unchanged_posix_observations',
                               'test_windows_creation_change_time_and_executable_synthesis_are_cross_domain_only',
                               'test_windows_cross_domain_unexplained_differences_reject',
                               'test_unusable_identity_never_establishes_ownership_even_if_equal',
                               'test_missing_identity_and_unsuitable_objects_cannot_bind',
                               'test_each_raw_field_remains_required_for_same_domain_stability',
                               'test_windows_birthtime_is_optional_but_not_allowed_to_disagree',
                               'test_report_read_requires_both_domains_stable_and_complete',
                               'test_synthetic_windows_binding_through_actual_report_startup_backup_and_restore',
                               'test_storage_paths_retain_complete_independent_domain_stability'),
 'test_interruptions.py': ('test_genuine_hot_journal_native_startup_preserves_all_committed_evidence',
                           'test_hot_journal_cold_inspector_never_opens_sqlite_or_owns_session',
                           'test_hot_journal_competing_owner_prevents_writable_recovery',
                           'test_hot_journal_admission_does_not_treat_raw_header_markers_as_committed',
                           'test_hot_journal_worker_ready_waits_for_owned_full_validation_and_profile',
                           'test_hot_journal_recovery_does_not_adopt_invalid_committed_state',
                           'test_hot_journal_startup_faults_preserve_primary_and_never_publish_ready',
                           'test_hot_recovery_failed_close_retains_lock_for_worker_cleanup_retry',
                           'test_process_interruption_atomic_facts_and_exact_receipt',
                           'test_active_owner_crash_and_repeated_reopen',
                           'test_interrupted_initial_schema_is_not_overwritten',
                           'test_interrupted_worker_shutdown_drains_accepted_request_truthfully',
                           'test_reminder_dismissal_process_death_never_confirms_or_partially_commits',
                           'test_worker_file_process_death_protects_facts_and_never_rolls_back_published_output'),
 'test_operational_lifecycle.py': ('test_reopened_active_calendar_boundaries_without_startup_or_tick_writes',
                                   'test_long_sleep_gap_explicit_action_and_stale_rejections',
                                   'test_multiple_corrections_reopen_then_stop_preserves_audits',
                                   'test_separate_owner_crash_stale_lock_and_orderly_release',
                                   'test_concurrent_first_creation_refused_before_overwrite',
                                   'test_create_race_preserves_file_appearing_after_initial_inspection',
                                   'test_initialization_failure_releases_os_ownership_without_deleting_partial',
                                   'test_damaged_dataset_refusal_preserves_main_file',
                                   'test_unknown_jsonl_and_file_parent_are_never_replaced',
                                   'test_native_permission_refusal_does_not_damage_dataset',
                                   'test_original_validation_error_survives_probe_cleanup_failure',
                                   'test_native_readonly_database_refuses_mutation_and_releases_lock'),
 'test_schema.py': ('test_ordinary_admission_reads_only_bounded_header_without_image_fingerprint',
                    'test_startup_rechecks_candidate_after_ownership_before_adoption',
                    'test_fresh_profile_and_reopen',
                    'test_unknown_or_partial_create_is_refused_without_changes',
                    'test_noncreating_open_and_invalid_zone',
                    'test_runtime_rejects_old_strict_version_with_actual_and_minimum',
                    'test_runtime_version_gate_accepts_strict_floor_and_later',
                    'test_profile_rejects_unfulfilled_settings',
                    'test_profile_never_reconfigures_inside_transaction',
                    'test_direct_strict_check_unique_fk_guards',
                    'test_final_orphan_postcondition_rolls_back',
                    'test_incomplete_guards_and_future_version_refused',
                    'test_timezone_conflict_refused',
                    'test_unknown_normal_open_does_not_add_files',
                    'test_both_active_closed_and_orphan_direct_sql_are_refused_on_open',
                    'test_existing_unsupported_journal_profile_is_refused_without_conversion'),
 'test_services.py': ('test_project_duplicate_names_independent_membership',
                      'test_exact_reuse_before_stale_check_and_collision',
                      'test_atomic_switch_and_bad_new_identity_roll_back',
                      'test_nonpositive_stop_switch_reject_without_work',
                      'test_invalid_integer_inputs',
                      'test_bad_id_owner_deleted_task_and_stale_version',
                      'test_active_start_audit_precision_noop_stale_and_stop',
                      'test_commit_ack_with_open_transaction_is_not_own_receipt_evidence',
                      'test_persistent_unreadable_reconcile_retains_exact_request',
                      'test_failed_rollback_close_preserves_diagnostics_and_no_poisoned_reuse',
                      'test_busy_transaction_is_bounded_and_does_not_begin',
                      'test_failed_begin_acknowledgement_cleans_open_transaction',
                      'test_uncommitted_same_connection_receipt_never_proves_commit',
                      'test_active_correction_gap_repeat_future_and_multiple_audits',
                      'test_rollback_journal_commit_busy_cannot_publish_own_receipt',
                      'test_reconciliation_probe_close_failure_retains_dataset_ownership'),
 'test_source_runtime.py': ('test_only_new_root_runtime_and_no_legacy_fallback',
                            'test_source_dependencies_and_offline_rules',
                            'test_source_launcher_needs_no_project_install_or_executable_builder',
                            'test_missing_tk_has_actionable_error',
                            'test_missing_tzdata_has_actionable_error'),
 'test_timesheet_files.py': ('test_fresh_status_exact_publication_matching_reuse_and_no_work_changes',
                             'test_strict_explicit_destination',
                             'test_overwrite_requires_actual_boolean',
                             'test_committed_evidence_gate_before_any_file_operation',
                             'test_stable_content_conflict_requires_exact_single_call_observation',
                             'test_unsuitable_objects_never_authorize_overwrite',
                             'test_inconclusive_file_inspection_has_no_consent',
                             'test_dataset_paths_protected_before_staging',
                             'test_resolved_parent_alias_into_dataset_is_protected',
                             'test_concurrent_exclusive_target_and_no_unsafe_hardlink_fallback',
                             'test_staging_faults_preserve_existing_target_and_original_error',
                             'test_final_target_recheck_deterministic_metadata_and_real_changes',
                             'test_final_reinspection_checks_bytes_when_all_target_metadata_is_unchanged',
                             'test_final_reinspection_preserves_read_error_and_immediate_metadata_guard',
                             'test_postpublication_uncertainty_retry_reuses_without_rewrite',
                             'test_final_verify_failure_and_owned_cleanup_diagnostics',
                             'test_verified_completion_survives_stage_cleanup_failure',
                             'test_changed_stage_is_not_deleted',
                             'test_reopen_frozen_bytes_ignore_current_renderer_and_later_actual',
                             'test_process_death_at_file_publication_boundary_keeps_registered_recovery',
                             'test_inspection_read_error_preserves_primary_when_close_also_fails'),
 'test_worker.py': ('test_connection_thread_operation_reconcile_and_shutdown',
                    'test_startup_failure_reports_and_stops_without_creating_dataset',
                    'test_cleanup_failure_stays_on_owner_thread_until_explicit_retry',
                    'test_exception_delivery_then_exact_absent_reconciliation_and_queued_reads',
                    'test_failed_startup_cleanup_remains_on_worker_until_explicit_retry',
                    'test_failed_validation_probe_cleanup_is_not_reported_stopped',
                    'test_mixed_work_history_revisions_and_week_change_use_same_worker')}

ADDITIONAL = {'test_accounting.py': ('test_dst_and_midnight_exact',
                        'test_own_tasks_deleted_work_and_no_project_double_count',
                        'test_sleep_forward_jump_capped_running_and_invalid_observation',
                        'test_local_week_and_utc_date_difference',
                        'test_non_hour_dst_and_closed_cutoff',
                        'test_detached_reads_cannot_mutate_work_or_metadata'),
 'test_history_reader.py': ('test_portions_keep_full_identity_offsets_precision_and_scope',
                            'test_running_cutoff_and_active_audit_never_save_a_stop',
                            'test_retained_task_deleted_effective_work_and_revision_details',
                            'test_invalid_history_requests_do_not_write',
                            'test_earlier_observation_clips_timed_but_never_dated_work',
                            'test_repeat_offsets_and_missing_identities',
                            'test_just_started_timer_is_observed_without_inventing_closed_work'),
 'test_manual_work.py': ('test_initial_mixed_records_are_typed_atomic_and_detached',
                         'test_bad_duration_rejects_without_any_facts',
                         'test_exact_duration_inputs',
                         'test_invalid_civil_dates_are_not_sql_string_validation',
                         'test_new_timed_validation_is_pure',
                         'test_explicit_repeat_and_non_hour_transition',
                         'test_initial_partial_writes_roll_back_and_retry_exactly',
                         'test_unknown_deleted_task_and_duplicate_uuid_do_not_create_orphans',
                         'test_date_only_identity_shape_constraints',
                         'test_bad_revision_shapes_and_successors_reject_direct_sql',
                         'test_active_date_only_wrong_owner_and_revision_kind_foreign_keys',
                         'test_unknown_schema_objects_refuse_without_recreation',
                         'test_duration_limit_has_no_arbitrary_hour_cap',
                         'test_backward_looking_repeated_wall_time_is_ordered_in_utc'),
 'test_mixed_work_accounting.py': ('test_mixed_precision_future_dates_and_independent_tasks',
                                   'test_dst_real_timer_plus_whole_date',
                                   'test_cross_midnight_redate_correction_deletion_and_read_purity'),
 'test_polr_allocation.py': ('test_mandatory_C_through_G',
                             'test_independent_expected_distributions',
                             'test_permutation_and_conservation_many_exact_integer_weeks',
                             'test_bad_units_and_converted_target_overflow',
                             'test_missing_extra_duplicate_invalid_dates',
                             'test_unrepresentable_or_noncanonical_week',
                             'test_seven_start_conventions_are_calendar_dates',
                             'test_exact_half_up_hundredths',
                             'test_cell_sum_differs_from_rerounded_raw_aggregate',
                             'test_display_rejects_bad_units'),
 'test_timekeeping.py': ('test_exact_microsecond_roundtrip',
                         'test_invalid_instant',
                         'test_naive_observation_rejected',
                         'test_minute_formats_and_unchanged_precision',
                         'test_seconds_and_invalid_clocks_rejected',
                         'test_gap_repeat_and_non_hour_transition',
                         'test_canonical_dates',
                         'test_type_distinctions_and_no_float_request_values',
                         'test_bundled_zone_does_not_depend_on_system_tzpath',
                         'test_zone_key_cannot_escape_bundled_resource'),
 'test_week_settings.py': ('test_seven_selected_weeks_reader_agreement_and_reopen',
                           'test_week_stale_noop_type_and_exact_historical_reuse'),
 'test_work_revisions.py': ('test_timed_precision_unchanged_changed_and_reverted_minute',
                            'test_date_redate_duration_noops_delete_and_reopen',
                            'test_entry_guards_never_retarget',
                            'test_timed_delete_retains_full_values_and_original_identity',
                            'test_revision_commit_failure_reconciles_exact_request',
                            'test_uncertain_initial_commit_retry_preserves_identity_and_newer_work',
                            'test_reopen_validates_revision_chains_and_dates',
                            'test_mixed_operations_process_death_keep_atomic_facts')}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


class Events:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
    def emit(self, event, **values):
        with self.lock, self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(event=event, monotonic=time.monotonic(), **values), ensure_ascii=False)+'\n')
            stream.flush()


def selection(scope, nodeid, fixtures, params=()):
    module, function = nodeid.split('::', 1)
    module = Path(module).name
    function = function.split('[', 1)[0]
    key = module+'::'+function
    callback = key in CALLBACKS and scope == 'Extended'
    if callback:
        allowed = SAFE_FIXTURES | {'root', 'connected'}
        category = 'audited-callback'
    else:
        allowed = SAFE_FIXTURES
        category = 'backend'
        choices = STORAGE if scope == 'Storage' else {**STORAGE, **ADDITIONAL} if scope == 'Extended' else CRITICAL
        functions = choices.get(module)
        if module not in choices or function not in (STORAGE.get(module, ()) if functions is None else functions):
            return False, 'Outside explicit bounded scope; supervised GUI/operator or unaudited case', 'deferred'
    unknown = set(fixtures)-set(params)-allowed
    if unknown:
        return False, 'Unaudited fixture closure: '+', '.join(sorted(unknown)), category
    return True, CALLBACKS[key] if callback else 'Audited backend function and fixture closure', category


class Obstructed(RuntimeError):
    pass


class DialogGuard:
    """No answers: original toolkit dialog paths fail before native presentation."""
    COMMANDS = {'tk_messageBox', 'tk_getOpenFile', 'tk_getSaveFile', 'tk_chooseDirectory', 'tk_dialog'}
    def __init__(self, events, callback_allowed=lambda: False):
        self.events, self.callback_allowed = events, callback_allowed
        self.originals = []
    def block(self, detail):
        self.events.emit('obstructed', detail=detail)
        raise Obstructed('Unexpected unattended UI request: '+detail)
    def install(self):
        import _tkinter
        import tkinter.filedialog as fd
        import tkinter.messagebox as mb
        import tkinter.simpledialog as sd
        guard = self
        create = _tkinter.create
        class TclProxy:
            def __init__(self, inner): self.inner = inner
            def __getattr__(self, name):
                if name == 'loadtk' and not guard.callback_allowed():
                    return lambda: guard.block('loadtk')
                return getattr(self.inner, name)
            def call(self, *args):
                flat = args[0] if len(args)==1 and isinstance(args[0], (tuple,list)) else args
                command = str(flat[0]) if flat else ''
                if command in guard.COMMANDS or (not guard.callback_allowed() and
                        command == 'package' and 'Tk' in flat):
                    guard.block('Tcl command '+command)
                if command in ('eval','uplevel') and any(re.search(r'\b(tk_messageBox|tk_getOpenFile|tk_getSaveFile|tk_chooseDirectory|tk_dialog)\b',str(arg)) for arg in flat[1:]):
                    guard.block('Tcl indirect dialog request')
                return self.inner.call(*args)
            def eval(self, script):
                if (re.search(r'\b(tk_messageBox|tk_getOpenFile|tk_getSaveFile|tk_chooseDirectory|tk_dialog)\b', script)
                        or (not guard.callback_allowed() and re.search(r'\bpackage\s+require\s+Tk\b', script))):
                    guard.block('Tcl eval dialog/Tk request')
                return self.inner.eval(script)
        def guarded_create(*args, **kwargs):
            want_tk = args[5] if len(args)>5 else kwargs.get('wantTk', True)
            if want_tk and not guard.callback_allowed(): guard.block('Tk root construction')
            return TclProxy(create(*args, **kwargs))
        replacements = [(_tkinter, 'create', guarded_create), (mb, '_show', lambda *a, **k: self.block('messagebox')),
                        (sd.Dialog, '__init__', lambda *a, **k: self.block('simpledialog'))]
        for name in ('askopenfilename','askopenfilenames','askopenfile','askopenfiles','asksaveasfilename','asksaveasfile','askdirectory'):
            replacements.append((fd, name, lambda *a, _name=name, **k: self.block('filedialog.'+_name)))
        for owner, name, replacement in replacements:
            self.originals.append((owner, name, getattr(owner,name)))
            setattr(owner,name,replacement)
    def restore(self):
        for owner,name,original in reversed(self.originals): setattr(owner,name,original)
        self.originals.clear()


class QualificationPlugin:
    def __init__(self, events, root, scope, *, enforce_manifest=True):
        self.events, self.root, self.scope = events, Path(root), scope
        self.enforce_manifest = enforce_manifest
        self.categories, self.reports, self.outcomes = {}, {}, Counter()
        self.manifest = []
        self.completed, self.finished = set(), False
        self.current = None
    def callback_allowed(self): return self.categories.get(self.current) == 'audited-callback'
    def pytest_sessionstart(self, session): self.events.emit('collection_start')
    def pytest_collection_modifyitems(self, session, config, items):
        kept, excluded, manifest = [], [], []
        for item in items:
            definitions = getattr(item, '_fixtureinfo').name2fixturedefs
            params = tuple(name for name in getattr(getattr(item,'callspec',None),'params',{})
                           if definitions.get(name) and definitions[name][-1].func.__name__=='get_direct_param_fixture_func'
                           and definitions[name][-1].func.__module__=='_pytest.python')
            accepted, reason, category = selection(self.scope,item.nodeid,item.fixturenames,params) if self.enforce_manifest else (True,'controlled helper fixture','backend')
            row = dict(nodeid=item.nodeid, fixtures=list(item.fixturenames), parameters=list(params),
                       selected=accepted, status='SELECTED' if accepted else 'NOT RUN', category=category, reason=reason)
            row['fixture_definitions'] = {name: [dict(module=d.func.__module__, function=d.func.__qualname__)
                                                 for d in values] for name,values in definitions.items() if values}
            manifest.append(row)
            (kept if accepted else excluded).append(item)
            self.categories[item.nodeid] = category
        self.manifest=manifest
        write_json(self.root/'manifest.json',manifest)
        if excluded: config.hook.pytest_deselected(items=excluded)
        items[:] = kept
        self.events.emit('selection', selected=len(kept), excluded=len(excluded))
    def pytest_collection_finish(self, session):
        selected={item.nodeid for item in session.items}
        for row in self.manifest:
            if row['selected'] and row['nodeid'] not in selected:
                row.update(selected=False,status='NOT RUN',reason='Deselected by pytest collection filter')
        write_json(self.root/'manifest.json',self.manifest)
        self.events.emit('collection_complete', selected=len(session.items))
    def pytest_collectreport(self, report):
        self.events.emit('collection_report',nodeid=report.nodeid,outcome=report.outcome,
                         diagnostic=str(report.longrepr) if report.failed else None)
    def pytest_runtest_logstart(self, nodeid, location):
        self.current=nodeid
        self.events.emit('node_start', nodeid=nodeid, category=self.categories.get(nodeid,'backend'))
    def pytest_runtest_setup(self, item): self.events.emit('phase', nodeid=item.nodeid, phase='setup')
    def pytest_runtest_call(self, item): self.events.emit('phase', nodeid=item.nodeid, phase='call')
    def pytest_runtest_teardown(self, item, nextitem): self.events.emit('phase', nodeid=item.nodeid, phase='teardown')
    def pytest_fixture_setup(self, fixturedef, request):
        # Dynamic getfixturevalue must not bypass the collected-closure audit.
        direct = (fixturedef.func.__name__ == 'get_direct_param_fixture_func'
                  and fixturedef.func.__module__ == '_pytest.python')
        allowed = SAFE_FIXTURES | ({'root','connected'} if self.callback_allowed() else set())
        if self.enforce_manifest and not direct and fixturedef.argname not in allowed:
            self.events.emit('obstructed',detail='Unaudited dynamic fixture '+fixturedef.argname)
            raise Obstructed('Unaudited fixture setup: '+fixturedef.argname)
    def pytest_runtest_logreport(self, report):
        self.reports.setdefault(report.nodeid,[]).append(dict(phase=report.when,outcome=report.outcome,
                                                            wasxfail=getattr(report,'wasxfail',None)))
        self.events.emit('report',nodeid=report.nodeid,phase=report.when,outcome=report.outcome,
                         wasxfail=getattr(report,'wasxfail',None),duration=report.duration,
                         diagnostic=str(report.longrepr) if report.failed or report.skipped else None)
    def pytest_runtest_logfinish(self, nodeid, location):
        if nodeid in self.completed: return
        self.completed.add(nodeid)
        result = node_outcome(self.reports.get(nodeid,[]))
        self.outcomes[result]+=1
        self.events.emit('node_finish',nodeid=nodeid,outcome=result,completed=len(self.completed),counts=dict(self.outcomes))
        self.current=None
    def pytest_sessionfinish(self, session, exitstatus):
        self.finished=True
        self.events.emit('session_finish',pytest_exit_code=int(exitstatus),completed=len(self.completed),counts=dict(self.outcomes))


def node_outcome(reports):
    if any(r['outcome']=='failed' and r['phase']!='call' for r in reports): return 'error'
    if any(r['outcome']=='failed' for r in reports): return 'failed'
    call=next((r for r in reports if r['phase']=='call'),None)
    if any(r['outcome']=='skipped' and r['wasxfail'] for r in reports): return 'xfailed'
    if call and call['wasxfail']: return 'xpassed'
    if any(r['outcome']=='skipped' for r in reports): return 'skipped'
    return 'passed' if call else 'error'


@dataclass
class Progress:
    started: float
    last_event: float
    phase: str = 'collection'
    node: str | None = None
    selected: int | None = None
    completed: int = 0
    counts: dict = field(default_factory=dict)
    node_started: float | None = None
    pytest_exit_code: int | None = None
    obstruction: str | None = None
    category: str = 'backend'
    last_payload: dict | None = None
    collection_errors: int = 0
    def accept(self, event, now):
        observed=min(now,event.get('monotonic',now))
        self.last_event=observed
        self.last_payload=event
        kind=event['event']
        if kind=='collection_complete': self.selected=event['selected'];self.phase='between tests'
        elif kind=='node_start': self.node=event['nodeid'];self.node_started=observed;self.phase='setup';self.category=event.get('category','backend')
        elif kind=='phase': self.phase=event['phase']
        elif kind=='node_finish':
            self.completed=event['completed'];self.counts=event['counts'];self.node_started=None;self.phase='between tests'
        elif kind=='session_finish': self.pytest_exit_code=event['pytest_exit_code'];self.phase='finished'
        elif kind=='obstructed': self.obstruction=event['detail']
        elif kind=='collection_report' and event['outcome']=='failed':self.collection_errors+=1
    def snapshot(self, now):
        return dict(qualification_phase='pytest', phase=self.phase,node=self.node,selected=self.selected,
                    completed=self.completed,counts=self.counts,elapsed=round(now-self.started,1),
                    collection_errors=self.collection_errors,
                    since_event=round(now-self.last_event,1),
                    percent=None if self.selected is None else (100*self.completed//self.selected if self.selected else 100))
    def deadline_reason(self, now, limits):
        if self.obstruction: return 'OBSTRUCTED: '+self.obstruction
        if now-self.started>=limits['phase']: return 'TIMEOUT: qualification phase'
        if self.selected is None and now-self.started>=limits['collection']: return 'TIMEOUT: collection'
        if self.node_started is not None:
            function=(self.node or '').split('::')[-1].split('[')[0]
            maximum=max(limits['test'],LONG_TESTS.get(function,0))
            if now-self.node_started>=maximum: return 'TIMEOUT: '+self.phase
        return None


def read_events(path, offset):
    if not Path(path).exists(): return [],offset
    with Path(path).open('rb') as stream:
        stream.seek(offset);data=stream.read()
    end=data.rfind(b'\n')+1
    return [json.loads(line) for line in data[:end].splitlines()], offset+end


def junit_status(path, completed=False):
    if not Path(path).exists(): return 'missing'
    from xml.etree import ElementTree
    try: ElementTree.parse(path)
    except (ElementTree.ParseError,OSError): return 'partial/unreadable'
    return 'complete' if completed else 'present but session incomplete'


def archive_evidence(root):
    """Enumerate owned files including hidden files, never follow reparse links."""
    root=Path(root).resolve();destination=Path(str(root)+'.zip')
    if destination.exists(): raise FileExistsError(destination)
    members=[];omitted=[]
    for directory, dirs, files in os.walk(root,followlinks=False):
        for name in list(dirs):
            path=Path(directory)/name
            if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:
                omitted.append(str(path.relative_to(root)));dirs.remove(name)
        for name in files:
            path=Path(directory)/name;info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
                omitted.append(str(path.relative_to(root)));continue
            members.append(path)
    write_json(root/'archive-members.json',dict(files=sorted([str(p.relative_to(root)) for p in members]+['archive-members.json']),omitted=omitted))
    members=[p for p in members if p!=root/'archive-members.json']+[root/'archive-members.json']
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(members): archive.write(path,path.relative_to(root))
    return destination


class WindowsChild:
    """Start suspended, assign KILL_ON_JOB_CLOSE, then resume. No unowned test code.

    The creation-time job attribute closes the suspended-before-assignment gap.
    Uses documented Win32 APIs. A restrictive outer Job Object may reject nested
    assignment: that is BLOCKED, never a reason to run without containment.
    """
    def __init__(self, args, cwd, env):
        if os.name!='nt': raise RuntimeError('BLOCKED: native Windows Job Objects unavailable')
        import msvcrt
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        k=self.k
        class STARTUPINFO(ctypes.Structure):
            _fields_=[('cb',w.DWORD),('lpReserved',w.LPWSTR),('lpDesktop',w.LPWSTR),('lpTitle',w.LPWSTR),
                      ('dwX',w.DWORD),('dwY',w.DWORD),('dwXSize',w.DWORD),('dwYSize',w.DWORD),
                      ('dwXCountChars',w.DWORD),('dwYCountChars',w.DWORD),('dwFillAttribute',w.DWORD),
                      ('dwFlags',w.DWORD),('wShowWindow',w.WORD),('cbReserved2',w.WORD),
                      ('lpReserved2',ctypes.c_void_p),('hStdInput',w.HANDLE),('hStdOutput',w.HANDLE),('hStdError',w.HANDLE)]
        class PROCESSINFO(ctypes.Structure):
            _fields_=[('process',w.HANDLE),('thread',w.HANDLE),('pid',w.DWORD),('tid',w.DWORD)]
        class STARTUPINFOEX(ctypes.Structure):
            _fields_=[('startup',STARTUPINFO),('attributes',ctypes.c_void_p)]
        class BASIC_LIMIT(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),
                      ('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),('active',w.DWORD),
                      ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class IO_COUNTERS(ctypes.Structure):
            _fields_=[(n,ctypes.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_=[('basic',BASIC_LIMIT),('io',IO_COUNTERS),('process_memory',ctypes.c_size_t),
                      ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        class ACCOUNTING(ctypes.Structure):
            _fields_=[('user',ctypes.c_longlong),('kernel',ctypes.c_longlong),('period_user',ctypes.c_longlong),
                      ('period_kernel',ctypes.c_longlong),('faults',w.DWORD),('total',w.DWORD),('active',w.DWORD),('terminated',w.DWORD)]
        self.ACCOUNTING=ACCOUNTING
        signatures={
            'CreateJobObjectW':([ctypes.c_void_p,w.LPCWSTR],w.HANDLE),
            'SetInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD],w.BOOL),
            'QueryInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p],w.BOOL),
            'IsProcessInJob':([w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)],w.BOOL),
            'InitializeProcThreadAttributeList':([ctypes.c_void_p,w.DWORD,w.DWORD,ctypes.POINTER(ctypes.c_size_t)],w.BOOL),
            'UpdateProcThreadAttribute':([ctypes.c_void_p,w.DWORD,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_void_p],w.BOOL),
            'DeleteProcThreadAttributeList':([ctypes.c_void_p],None),
            'CreateProcessW':([w.LPCWSTR,w.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,w.BOOL,w.DWORD,ctypes.c_void_p,w.LPCWSTR,ctypes.POINTER(STARTUPINFO),ctypes.POINTER(PROCESSINFO)],w.BOOL),
            'ResumeThread':([w.HANDLE],w.DWORD), 'CloseHandle':([w.HANDLE],w.BOOL),
            'TerminateProcess':([w.HANDLE,w.UINT],w.BOOL), 'TerminateJobObject':([w.HANDLE,w.UINT],w.BOOL),
            'WaitForSingleObject':([w.HANDLE,w.DWORD],w.DWORD),
            'GetExitCodeProcess':([w.HANDLE,ctypes.POINTER(w.DWORD)],w.BOOL),
        }
        for name,(arguments,result) in signatures.items():
            function=getattr(k,name);function.argtypes=arguments;function.restype=result
        self.job=self.process=None;self.stdout=self.stderr=None
        descriptors=[];thread=None;attributes=None
        def checked(ok):
            if not ok: raise ctypes.WinError(ctypes.get_last_error())
            return ok
        try:
            self.job=checked(k.CreateJobObjectW(None,None))
            limits=EXTENDED_LIMIT();limits.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            checked(k.SetInformationJobObject(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits)))
            out_r,out_w=os.pipe();descriptors.extend((out_r,out_w))
            err_r,err_w=os.pipe();descriptors.extend((err_r,err_w))
            null=os.open(os.devnull,os.O_RDONLY);descriptors.append(null)
            # Only these standard handles can be inherited. The job handle is
            # never inherited, so collector death triggers kill-on-close.
            for fd in (out_w,err_w,null): os.set_inheritable(fd,True)
            size=ctypes.c_size_t()
            k.InitializeProcThreadAttributeList(None,2,0,ctypes.byref(size))
            if not size.value:raise ctypes.WinError(ctypes.get_last_error())
            attribute_buffer=ctypes.create_string_buffer(size.value)
            checked(k.InitializeProcThreadAttributeList(attribute_buffer,2,0,ctypes.byref(size)))
            attributes=ctypes.cast(attribute_buffer,ctypes.c_void_p)
            job_handles=(w.HANDLE*1)(self.job)
            checked(k.UpdateProcThreadAttribute(attributes,0,0x2000D,job_handles,ctypes.sizeof(job_handles),None,None)) # JOB_LIST
            handles=(w.HANDLE*3)(*[msvcrt.get_osfhandle(fd) for fd in (null,out_w,err_w)])
            checked(k.UpdateProcThreadAttribute(attributes,0,0x20002,handles,ctypes.sizeof(handles),None,None)) # HANDLE_LIST
            si=STARTUPINFOEX();si.startup.cb=ctypes.sizeof(si);si.startup.dwFlags=0x100;si.attributes=attributes
            si.startup.hStdInput=handles[0];si.startup.hStdOutput=handles[1];si.startup.hStdError=handles[2]
            pi=PROCESSINFO();command=ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
            environment=ctypes.create_unicode_buffer('\0'.join(f'{key}={value}' for key,value in sorted(env.items(),key=lambda pair:pair[0].upper()))+'\0\0')
            checked(k.CreateProcessW(args[0],command,None,None,True,0x4|0x400|0x08000000|0x80000,environment,str(cwd),ctypes.cast(ctypes.byref(si),ctypes.POINTER(STARTUPINFO)),ctypes.byref(pi)))
            self.process=pi.process;thread=pi.thread;self.pid=pi.pid
            contained=w.BOOL()
            checked(k.IsProcessInJob(self.process,self.job,ctypes.byref(contained)))
            if not contained.value:raise RuntimeError('BLOCKED: creation-time Job Object containment was not established')
            if k.ResumeThread(thread)==0xFFFFFFFF: raise ctypes.WinError(ctypes.get_last_error())
            k.CloseHandle(thread);thread=None
            self.stdout=os.fdopen(out_r,'rb',buffering=0);descriptors.remove(out_r)
            self.stderr=os.fdopen(err_r,'rb',buffering=0);descriptors.remove(err_r)
        except BaseException as primary:
            if self.process:
                if not k.TerminateProcess(self.process,238): primary.add_note('Suspended process termination failed')
                if k.WaitForSingleObject(self.process,5000)!=0: primary.add_note('Suspended process cleanup unverified')
            if thread: k.CloseHandle(thread)
            try:self.close()
            except Exception as secondary:primary.add_note('Process reservation cleanup also failed: '+repr(secondary))
            raise
        finally:
            if attributes:k.DeleteProcThreadAttributeList(attributes)
            for fd in descriptors: os.close(fd)
    def poll(self):
        wait=self.k.WaitForSingleObject(self.process,0)
        if wait==258:return None
        if wait!=0:raise ctypes.WinError(ctypes.get_last_error())
        code=w.DWORD()
        if not self.k.GetExitCodeProcess(self.process,ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
        return code.value
    def terminate_owned(self):
        if not self.k.TerminateJobObject(self.job,238):raise ctypes.WinError(ctypes.get_last_error())
    def active_count(self):
        value=self.ACCOUNTING()
        if not self.k.QueryInformationJobObject(self.job,1,ctypes.byref(value),ctypes.sizeof(value),None):
            raise ctypes.WinError(ctypes.get_last_error())
        return value.active
    def visible_windows(self):
        # Observe only visible windows belonging to processes in this exact job.
        # External security/OS processes are not claimed to be universally detectable.
        class IDS(ctypes.Structure):
            _fields_=[('assigned',w.DWORD),('count',w.DWORD),('pids',ctypes.c_size_t*1024)]
        ids=IDS()
        if not self.k.QueryInformationJobObject(self.job,3,ctypes.byref(ids),ctypes.sizeof(ids),None):
            raise ctypes.WinError(ctypes.get_last_error())
        owned=set(ids.pids[:ids.count]);result=[]
        user=ctypes.WinDLL('user32',use_last_error=True)
        callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
        user.EnumWindows.argtypes=[callback_type,w.LPARAM];user.EnumWindows.restype=w.BOOL
        user.IsWindowVisible.argtypes=[w.HWND];user.IsWindowVisible.restype=w.BOOL
        user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
        user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
        user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
        @callback_type
        def visit(hwnd,unused):
            pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value in owned and user.IsWindowVisible(hwnd):
                name=ctypes.create_unicode_buffer(256);title=ctypes.create_unicode_buffer(512)
                user.GetClassNameW(hwnd,name,len(name));user.GetWindowTextW(hwnd,title,len(title))
                result.append(dict(pid=pid.value,window_class=name.value,title=title.value))
            return True
        if not user.EnumWindows(visit,0):raise ctypes.WinError(ctypes.get_last_error())
        return result
    def close(self):
        primary=None
        for name in ('job','process'):
            handle=getattr(self,name,None)
            if handle:
                if self.k.CloseHandle(handle):setattr(self,name,None)
                else:
                    error=ctypes.WinError(ctypes.get_last_error())
                    if primary:primary.add_note(name+' handle close also failed: '+repr(error))
                    else:primary=error
        for stream in (self.stdout,self.stderr):
            if stream:
                try:stream.close()
                except Exception as error:
                    if primary:primary.add_note('Stream close also failed: '+repr(error))
                    else:primary=error
        if primary:raise primary


def monitor(child, root, limits, *, clock=time.monotonic, sleep=time.sleep, display=print):
    """Portable watchdog logic; production child containment is Windows-only."""
    root=Path(root);events=root/'events.jsonl';offset=0;started=clock()
    progress=Progress(started,started);messages=queue.Queue(maxsize=128);stream_errors=queue.SimpleQueue();threads=[]
    live_truncated=threading.Event()
    def mirror(name,value):
        try:messages.put_nowait((name,value))
        except queue.Full:live_truncated.set() # Canonical byte logs remain complete.
    def drain(stream, name):
        try:
            with (root/name).open('wb') as log:
                decoder=codecs.getincrementaldecoder('utf-8')(errors='replace')
                while True:
                    chunk=stream.read(4096)
                    if not chunk:break
                    log.write(chunk);log.flush()
                    mirror(name,decoder.decode(chunk))
                tail=decoder.decode(b'',final=True)
                if tail:mirror(name,tail)
        except Exception as exc:stream_errors.put(repr(exc))
    for stream,name in ((child.stdout,'stdout.log'),(child.stderr,'stderr.log')):
        thread=threading.Thread(target=drain,args=(stream,name),daemon=True);thread.start();threads.append(thread)
    reason=None;last_display=started-1;last_warning=started;code=None;cleanup={};truncation_reported=False
    try:
        while True:
            now=clock()
            incoming,offset=read_events(events,offset)
            for event in incoming:progress.accept(event,now)
            reason=progress.deadline_reason(now,limits)
            if (root/'cancel.request').exists():reason='CANCELLED by operator'
            if now-last_display>=1:
                if hasattr(child,'visible_windows'):
                    windows=child.visible_windows()
                    forbidden=[window for window in windows if progress.category!='audited-callback'
                               or window['window_class']!='TkTopLevel']
                    if forbidden:
                        Events(root/'collector-events.jsonl').emit('obstructed',detail='Unexpected owned native window',windows=forbidden)
                        progress.accept(dict(event='obstructed',detail='Unexpected owned native window',windows=forbidden),now)
                        reason='OBSTRUCTED: Unexpected owned native window'
                display('CHRONICLE_PROGRESS '+json.dumps(progress.snapshot(now),ensure_ascii=False));last_display=now
            if now-progress.last_event>=limits['warning'] and now-last_warning>=limits['warning']:
                display(f'WARNING: no pytest progress for {now-progress.last_event:.1f}s; last node {progress.node}; phase {progress.phase}')
                last_warning=now
            if live_truncated.is_set() and not truncation_reported:
                display('Live console output exceeded its bounded queue; complete stdout/stderr remain in the byte logs.')
                truncation_reported=True
            try:stream_error=stream_errors.get_nowait()
            except queue.Empty:pass
            else:raise OSError(stream_error)
            for _ in range(100):
                try:name,value=messages.get_nowait()
                except queue.Empty:break
                display(value,end='')
            code=child.poll()
            if reason or code is not None:break
            sleep(0.1)
    except KeyboardInterrupt:reason='CANCELLED by operator'
    except Exception as exc:reason='COLLECTOR ERROR: '+repr(exc)
    finally:
        # Even normal pytest exit can leave test-owned descendants behind.
        try:
            cleanup['active_before']=child.active_count()
            child.terminate_owned()
            deadline=clock()+limits['cleanup']
            while child.active_count() and clock()<deadline:sleep(0.05)
            cleanup['active_after']=child.active_count()
            cleanup['verified']=cleanup['active_after']==0
            for thread in threads:thread.join(timeout=max(0,deadline-clock()))
            cleanup['streams_drained']=not any(t.is_alive() for t in threads)
            code=child.poll()
        except Exception as exc:cleanup['error']=repr(exc);cleanup['verified']=False
        finally:
            try:child.close()
            except Exception as exc:cleanup['close_error']=repr(exc);cleanup['verified']=False
    incoming,offset=read_events(events,offset)
    for event in incoming:progress.accept(event,clock())
    late_errors=[]
    while True:
        try:late_errors.append(stream_errors.get_nowait())
        except queue.Empty:break
    if late_errors:
        cleanup['stream_errors']=late_errors;cleanup['verified']=False
        if reason is None:reason='COLLECTOR ERROR: output capture failed'
    display('CHRONICLE_PROGRESS '+json.dumps(progress.snapshot(clock()),ensure_ascii=False))
    summary=dict(status=('OBSTRUCTED' if progress.obstruction else 'CANCELLED' if reason and reason.startswith('CANCELLED')
                         else 'TIMEOUT' if reason and reason.startswith('TIMEOUT') else 'ERROR' if reason
                         else 'PASS' if code==0 and progress.pytest_exit_code==0 and progress.selected is not None
                         and progress.selected>0 and progress.completed==progress.selected
                         and cleanup.get('verified') and cleanup.get('streams_drained') else 'FAIL'),
                 termination_reason=reason,process_exit_code=code,pytest_exit_code=progress.pytest_exit_code,
                 progress=progress.snapshot(clock()),cleanup=cleanup,last_event=progress.last_payload,
                 junit=junit_status(root/'junit.xml',progress.pytest_exit_code is not None))
    summary['manifest']='recorded' if (root/'manifest.json').exists() else 'missing/incomplete'
    summary['live_console_truncated']=live_truncated.is_set()
    write_json(root/'test-result.json',summary)
    return summary


def runtime_evidence():
    import platform
    value=dict(platform=platform.platform(),python=sys.version,executable=sys.executable,sqlite=sqlite3.sqlite_version,errors=[])
    try:
        with closing(sqlite3.connect(':memory:')) as connection:
            value['sqlite_source_id']=connection.execute('SELECT sqlite_source_id()').fetchone()[0]
            connection.execute('CREATE TABLE strict_probe(x INTEGER) STRICT')
            value['strict_supported']=True
    except Exception as exc:value['errors'].append('SQLite STRICT unavailable: '+repr(exc))
    try:
        import tkinter
        import _tkinter
        # Pure Tcl directly: Tk/Tcl() would also read user .Tk.py profiles.
        tcl=_tkinter.create(None,'ChronicleQualification','ChronicleQualification',False,True,False,False,None)
        value.update(tcl=tcl.call('info','patchlevel'),tk_compiled=tkinter.TkVersion,tk_desktop='NOT RUN: no root created by prerequisites')
    except Exception as exc:value['errors'].append('Tcl/Tk unavailable: '+repr(exc))
    try:
        value['tzdata']=importlib.metadata.version('tzdata')
        from importlib.resources import files
        from zoneinfo import ZoneInfo
        for key in ('America/Chicago','Australia/Lord_Howe'):
            with files('tzdata.zoneinfo').joinpath(*key.split('/')).open('rb') as stream:ZoneInfo.from_file(stream,key=key)
    except Exception as exc:value['errors'].append('Offline tzdata unavailable: '+repr(exc))
    return value


def ntfs_evidence(path):
    if os.name!='nt':raise RuntimeError('BLOCKED: genuine native Windows required')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetVolumePathNameW.argtypes=[w.LPCWSTR,w.LPWSTR,w.DWORD];kernel.GetVolumePathNameW.restype=w.BOOL
    kernel.GetVolumeInformationW.argtypes=[w.LPCWSTR,w.LPWSTR,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.POINTER(w.DWORD),ctypes.POINTER(w.DWORD),w.LPWSTR,w.DWORD]
    kernel.GetVolumeInformationW.restype=w.BOOL
    kernel.GetDriveTypeW.argtypes=[w.LPCWSTR];kernel.GetDriveTypeW.restype=w.UINT
    volume=ctypes.create_unicode_buffer(1024);fs=ctypes.create_unicode_buffer(128)
    serial=w.DWORD();length=w.DWORD();flags=w.DWORD()
    if not kernel.GetVolumePathNameW(str(path),volume,len(volume)):raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.GetVolumeInformationW(volume.value,None,0,ctypes.byref(serial),ctypes.byref(length),ctypes.byref(flags),fs,len(fs)):
        raise ctypes.WinError(ctypes.get_last_error())
    kind=kernel.GetDriveTypeW(volume.value)
    if fs.value!='NTFS' or kind!=3:raise RuntimeError('BLOCKED: fixed local NTFS required')
    return dict(volume=volume.value,filesystem=fs.value,drive_type=kind,volume_serial=str(serial.value))


def metadata_probe(root):
    """Only newly reserved files under the collector-owned evidence root."""
    directory=Path(root)/'metadata-probe';directory.mkdir()
    events=Events(Path(root)/'metadata.jsonl');path=directory/'sample.dat'
    for name in ('environment','filesystem'):
        source=Path(root)/(name+'.json')
        if source.exists():events.emit(name,values=json.loads(source.read_text(encoding='utf-8')))
    def fields(value):
        names=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns','st_birthtime_ns','st_file_attributes','st_reparse_tag')
        return {name:str(getattr(value,name)) if hasattr(value,name) else None for name in names}
    def capture(label,fd=None):
        values={'stat':fields(path.stat()),'lstat':fields(path.lstat())}
        if fd is not None:values['fstat']=fields(os.fstat(fd))
        differences={key:[values['lstat'][key],values['fstat'][key]] for key in values['lstat']
                     if 'fstat' in values and values['lstat'][key]!=values['fstat'][key]}
        events.emit('observation',label=label,observations=values,differences=differences,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with path.open('xb') as stream:stream.write(b'original');stream.flush();os.fsync(stream.fileno())
    for flags,label in ((os.O_RDONLY,'readonly'),(os.O_RDWR,'writable')):
        capture(label+' before open')
        fd=os.open(path,flags|getattr(os,'O_BINARY',0))
        try:
            capture(label+' open',fd)
            if flags==os.O_RDWR:os.fsync(fd);capture(label+' after fsync',fd)
        finally:os.close(fd)
        capture(label+' after close')
    alias=directory/'hardlink.dat'
    try:
        os.link(path,alias)
        a,b=path.lstat(),alias.lstat()
        events.emit('hardlink',status='OBSERVED',source=fields(a),link=fields(b),
                    usable_equal_identity=bool(a.st_dev and a.st_ino and (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)))
    except OSError as exc:events.emit('hardlink',status='BLOCKED',error=repr(exc))
    old=path.stat();capture('before same-size mutation')
    with path.open('r+b') as stream:stream.write(b'modified');stream.flush();os.fsync(stream.fileno())
    os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns));capture('same-size mutation restored mtime')
    return dict(status='OBSERVED',qualification='No compatibility acceptance inferred from observations')


def source_observation(repo):
    def git(*args):
        return subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,timeout=15,check=True).stdout.strip()
    return dict(revision=git('rev-parse','HEAD'),branch=git('branch','--show-current'),
                dirty=bool(git('status','--porcelain','--untracked-files=all')))


def checked_source(repo, expected=None, *, observed=None):
    observed=source_observation(repo) if observed is None else observed
    head=observed['revision']
    if observed['dirty']:raise RuntimeError('BLOCKED: dirty checkout; retain changes and use a reviewed clean source')
    if expected:
        if not re.fullmatch(r'[0-9a-fA-F]{7,40}',expected) or not head.lower().startswith(expected.lower()):
            raise RuntimeError('BLOCKED: expected source revision mismatch')
    return dict(revision=head,branch=observed['branch'])


def prepare(repo,root,scope,expected):
    repo=Path(repo).resolve();root=Path(root).resolve()
    if root.is_relative_to(repo):raise RuntimeError('BLOCKED: evidence must be outside repository')
    if not (repo/'run_chronicle.py').is_file() or not (repo/'tests/rewrite').is_dir():raise RuntimeError('BLOCKED: Chronicle source not found')
    for ancestor in (root,*root.parents):
        if (ancestor/'chronicle.sqlite3').exists():raise RuntimeError('BLOCKED: evidence cannot be inside a Chronicle dataset')
    observed=source_observation(repo)
    write_json(root/'source.json',dict(**observed,collector={p:hashlib.sha256((repo/p).read_bytes()).hexdigest()
        for p in ('scripts/qualify_windows.ps1','scripts/qualification_pytest.py')}))
    source=checked_source(repo,expected,observed=observed)
    runtime=runtime_evidence()
    write_json(root/'environment.json',runtime)
    if runtime['errors']:raise RuntimeError('BLOCKED: '+'; '.join(runtime['errors']))
    write_json(root/'filesystem.json',ntfs_evidence(root))
    if sys.version_info<(3,11) or sqlite3.sqlite_version_info<(3,37,0):raise RuntimeError('BLOCKED: Python 3.11+/SQLite 3.37+ required')
    if importlib.metadata.version('tzdata')!='2026.5':raise RuntimeError('BLOCKED: tzdata==2026.5 required')
    windows=sys.getwindowsversion()
    if windows.build<22000 or windows.product_type!=1:raise RuntimeError('BLOCKED: Windows 11 client required')
    if scope!='MetadataProbe':
        try:version=importlib.metadata.version('pytest')
        except importlib.metadata.PackageNotFoundError as exc:raise RuntimeError('BLOCKED: pytest is unavailable; no packages installed') from exc
        write_json(root/'pytest-version.json',dict(version=version))
        if int(version.split('.')[0])<8:raise RuntimeError('BLOCKED: pytest>=8 required')
    deferred=[]
    # Legacy suites are not collected; retain explicit source-level unexpanded
    # identities instead of pretending parameter instances were collected/run.
    for path in sorted((repo/'tests').glob('test_*.py')):
        for node in ast.parse(path.read_bytes()).body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                deferred.append(dict(nodeid=str(path.relative_to(repo))+'::'+node.name,status='NOT RUN',
                                     parameters='not collected',reason='Retained legacy suite outside native rewrite scope'))
    write_json(root/'deferred.json',dict(legacy=deferred,supervised='Every collected rewrite exclusion and fixture reason is recorded in manifest.json; native operator dialogs are supervised separately.'))
    if scope=='MetadataProbe':
        uncollected=[]
        for path in sorted((repo/'tests/rewrite').glob('test_*.py')):
            for node in ast.parse(path.read_bytes()).body:
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                    uncollected.append(dict(nodeid=str(path.relative_to(repo))+'::'+node.name,status='NOT RUN',
                                            parameters='not collected',reason='MetadataProbe does not request pytest'))
        write_json(root/'manifest.json',[])
        write_json(root/'deferred.json',dict(legacy=deferred,rewrite=uncollected))
    return source


def run_pytest(root,scope,arguments=None,*,enforce_manifest=True):
    import pytest
    root=Path(root)
    plugin=QualificationPlugin(Events(root/'events.jsonl'),root,scope,enforce_manifest=enforce_manifest)
    # Mark before pytest registers hooks, without requiring pytest for probe/setup.
    for name in ('pytest_runtest_setup','pytest_runtest_call','pytest_runtest_teardown'):
        pytest.hookimpl(tryfirst=True)(getattr(type(plugin),name))
    guard=DialogGuard(plugin.events,plugin.callback_allowed);guard.install()
    try:
        args=arguments
        if arguments is None:
            try:(root/'pytest-temp').lstat()
            except FileNotFoundError:pass
            else:
                plugin.events.emit('obstructed',detail='Existing pytest temporary path; refusing automatic deletion')
                raise Obstructed('Existing pytest temporary path must be preserved')
            args=['-vv','-rA','-p','no:cacheprovider','-o','addopts=','--basetemp',str(root/'pytest-temp'),
                  '--junitxml',str(root/'junit.xml'),'tests/rewrite/']
        write_json(root/'pytest-arguments.json',args)
        return int(pytest.main(args,plugins=[plugin]))
    finally:guard.restore()


def verify_output(root,repo,*,completed=False):
    """Refuse unsafe output before writing even a failure receipt into it."""
    from uuid import UUID
    root=Path(root).absolute();repo=Path(repo).resolve()
    if str(root).startswith(('\\\\','//')) or root.resolve()!=root or root.is_relative_to(repo) or not root.is_dir() or root.is_symlink():
        raise RuntimeError('BLOCKED: an isolated owned evidence directory is required')
    for parent in (root,*root.parents):
        if (parent/'chronicle.sqlite3').exists():raise RuntimeError('BLOCKED: output overlaps Chronicle storage')
    owner=json.loads((root/'collector-owner.json').read_text(encoding='utf-8-sig'))
    if owner.get('kind')!='Chronicle qualification' or Path(owner.get('root',''))!=root:
        raise RuntimeError('BLOCKED: output ownership marker mismatch')
    UUID(owner['id'])
    allowed={'collector-owner.json','launcher.json','windows.json','windows-details-error.json','launcher-command.json','launcher-stdout.log','launcher-stderr.log'}
    if not completed and any(p.name not in allowed or not p.is_file() or p.is_symlink() for p in root.iterdir()):
        raise RuntimeError('BLOCKED: unexpected objects in evidence reservation')
    return root


def collect(repo,root,scope,expected,limits,*,archive=True):
    try:root=verify_output(root,repo)
    except Exception as exc:
        print(str(exc),file=sys.stderr,flush=True)
        return 4 # No failure receipt is allowed to modify an unowned directory.
    root=Path(root);summary={'status':'BLOCKED','scope':scope,'pytest_exit_code':None,'junit':'missing'}
    try:
        print('CHRONICLE_PROGRESS '+json.dumps(dict(qualification_phase='prerequisites',phase='inspection',completed=0,selected=None,counts={})),flush=True)
        source=prepare(repo,root,scope,expected)
        print('CHRONICLE_PROGRESS '+json.dumps(dict(qualification_phase='MetadataProbe',phase='observation',completed=0,selected=None,counts={})),flush=True)
        summary['metadata']=metadata_probe(root)
        if scope=='MetadataProbe':summary.update(status='OBSERVED',source=source,junit='NOT APPLICABLE: no pytest requested')
        else:
            args=[sys.executable,'-u','-B',str(Path(__file__).resolve()),'--pytest-worker',str(root),'--scope',scope]
            temp=root/'child-temp';home=root/'child-home';temp.mkdir();home.mkdir()
            env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':'','PYTEST_PLUGINS':'','PYTHONPATH':'',
                 'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','PYTHONIOENCODING':'utf-8',
                 'HOME':str(home),'USERPROFILE':str(home),'TEMP':str(temp),'TMP':str(temp)}
            write_json(root/'command.json',dict(arguments=args,cwd=str(repo),limits=limits,long_tests=LONG_TESTS,
                         environment_overrides={k:env[k] for k in ('PYTEST_DISABLE_PLUGIN_AUTOLOAD','PYTEST_ADDOPTS','PYTEST_PLUGINS','HOME','USERPROFILE','TEMP','TMP')}))
            child=WindowsChild(args,repo,env)
            summary.update(monitor(child,root,limits),source=source,scope=scope)
            if checked_source(repo,expected)!=source:
                summary['status']='BLOCKED';summary['source_changed']=True
    except BaseException as exc:
        summary.update(status='CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED',error=repr(exc))
        (root/'collector-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        summary['qualification']='No independent Windows/Stage 4 acceptance follows from collector completion'
        summary.setdefault('manifest','recorded' if (root/'manifest.json').exists() else 'not collected: execution blocked before complete collection')
        write_json(root/'summary.json',summary)
        try:
            if archive:
                zip_path=archive_evidence(root)
                print('Evidence ZIP: '+str(zip_path),flush=True)
        except Exception as exc:
            write_json(root/'archive-error.json',dict(error=repr(exc),evidence_retained=str(root)))
            summary['archive_error']=repr(exc);summary['status']='ERROR';write_json(root/'summary.json',summary)
        print('Collector execution result: '+summary['status'],flush=True)
        if 'progress' in summary:
            print('Final pytest nodes: '+json.dumps(summary['progress'],ensure_ascii=False),flush=True)
            print('Process exit: '+str(summary.get('process_exit_code'))+'; pytest session exit: '+str(summary.get('pytest_exit_code')),flush=True)
    return 0 if summary['status'] in ('PASS','OBSERVED') else 4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--scope',choices=SCOPES,default='MetadataProbe')
    parser.add_argument('--expected-revision')
    parser.add_argument('--defer-archive',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--archive-evidence',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--pytest-worker',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--collection-seconds',type=int,default=90)
    parser.add_argument('--test-seconds',type=int,default=120)
    parser.add_argument('--phase-seconds',type=int,default=900)
    options=parser.parse_args()
    if options.archive_evidence:
        try:
            root=verify_output(options.archive_evidence,options.repo,completed=True)
            print(archive_evidence(root),flush=True)
            return 0
        except Exception:
            traceback.print_exc()
            return 4
    if options.pytest_worker:return run_pytest(options.pytest_worker,options.scope)
    if options.output is None:parser.error('Use scripts/qualify_windows.ps1 to reserve an isolated evidence directory')
    limits={**LIMITS,'collection':options.collection_seconds,'test':options.test_seconds,'phase':options.phase_seconds}
    if any(v<=0 for v in limits.values()):parser.error('Timeouts must be positive')
    return collect(options.repo,options.output,options.scope,options.expected_revision,limits,archive=not options.defer_archive)


if __name__=='__main__':raise SystemExit(main())
