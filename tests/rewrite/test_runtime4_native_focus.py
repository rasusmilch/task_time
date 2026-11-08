"""Production schema-4 focus subjects; portable Tk is not native qualification."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import pytest

from chronicle.history_window import widget_live
from chronicle.worker import DatabaseWorker
from test_app import root, pump
from test_backup_restore import logical
from test_chronicle_history_ui import open_history
from test_chronicle_timesheet_ui import open_sheet
from test_main_explorer import select
from test_runtime4_ui import ordinary
from test_schema4_project_modal import task
from tk_observation import wait_observed


def production_readiness(ordinary, root, request):
    app, worker, places = ordinary
    assert type(worker) is DatabaseWorker and worker.is_alive()
    assert app.root is root and app.worker is worker
    assert Path(worker.directory) == places.folder
    assert app.presentation_profile == 'schema4'
    assert app.candidate_presentation is False and app.schema4_presentation is True
    assert type(app.state['schema_version']) is int and app.state['schema_version'] == 4
    assert app.state['semantic_verified'] is True
    assert app.state['ordinary_startup_permitted'] is True
    assert app.dataset_id == app.state['dataset_id']
    assert not root.test_errors
    ready = dict(dataset_id=app.dataset_id, schema_version=app.state['schema_version'],
        semantic_verified=app.state['semantic_verified'],
        ordinary_startup_permitted=app.state['ordinary_startup_permitted'],
        presentation_profile=app.presentation_profile, candidate_presentation=app.candidate_presentation,
        worker_type=type(worker).__name__, worker_alive=worker.is_alive())
    context = getattr(request.node, '_f2_control_context', None)
    if context is not None:
        assert context['root'] is root and context['driver'].node == request.node.nodeid
        context['production_readiness'] = ready.copy()
    return ready


def baseline(ordinary, selected=None):
    app, worker, places = ordinary
    return dict(dataset_id=app.dataset_id, selected_task_id=selected,
                worker_identity=id(worker), facts=logical(places.folder/'chronicle.sqlite3'))


def unchanged(ordinary, before, ready, tmp_path):
    app, worker, places = ordinary
    after = baseline(ordinary, app.selected_task_id())
    (tmp_path/'focus-subject.json').write_text(json.dumps(dict(
        readiness=ready, before=before, after=after,
        callback_diagnostics=[repr(e[1]) for e in app.root.test_errors]),
        indent=2, default=lambda value: dict(bytes_hex=value.hex()))+'\n')
    assert after == before
    assert worker.is_alive() and app.worker is worker
    assert app.state['dataset_id'] == before['dataset_id']


@pytest.mark.parametrize('mode', ['local', 'none', 'missing', 'reused'])
def test_ordinary_schema4_history_parent_grab_focus_return_identity_and_guard(ordinary, root, monkeypatch, mode, request, tmp_path):
    app, worker, places = ordinary
    ready = production_readiness(ordinary, root, request)
    key = task(app)
    select(app, app.task_row(key))
    assert app.selected_task_id() == key and not root.test_errors
    before = baseline(ordinary, key)
    saved = ttk.Entry(root, name='saved_focus')
    saved.grid(row=9, column=0)
    pump(root, lambda: saved.winfo_ismapped() and saved.winfo_viewable())
    assert root.nametowidget(str(saved)) is saved and widget_live(saved)
    saved.focus_set()
    wait_observed(root, lambda: root.focus_get() is saved,
        phase='PRECONDITION History origin focus', widgets=(saved,), foreground=True)
    if mode == 'local': root.grab_set()
    history = open_history(app)
    assert app.history is history and history.window.grab_current() is history.window
    replacement = None
    if mode in ('missing', 'reused'):
        saved.destroy()
        assert not widget_live(saved)
        if mode == 'reused':
            replacement = ttk.Entry(root, name='saved_focus')
            replacement.grid(row=9, column=0)
            assert replacement is not saved and str(replacement) == str(saved)
            assert root.nametowidget(str(saved)) is replacement and not widget_live(saved)
    expected = saved if mode in ('local', 'none') else root
    targets = []
    original = expected.focus_set
    def restore():
        targets.append(expected)
        assert app._history_opening and app.history is None
        assert not app.open_history()
        original()
    monkeypatch.setattr(expected, 'focus_set', restore)
    assert history.close()
    assert app.history is None and not app._history_opening and targets == [expected]
    wait_observed(root, lambda: root.focus_get() is expected,
        phase='History actual return focus', widgets=(expected,))
    if replacement is not None: assert root.focus_get() is not replacement
    assert root.grab_current() is (root if mode == 'local' else None)
    if mode == 'local': root.grab_release()
    unchanged(ordinary, before, ready, tmp_path)
    assert not root.test_errors


def test_ordinary_schema4_timesheet_origin_return_competing_grab_destroy_and_reentry(ordinary, root, monkeypatch, request, tmp_path):
    app, worker, places = ordinary
    ready = production_readiness(ordinary, root, request)
    before = baseline(ordinary)
    root.grab_set()
    app.tree.focus_set()
    wait_observed(root, lambda: root.focus_get() is app.tree,
        phase='PRECONDITION Timesheet origin focus', widgets=(app.tree,), foreground=True)
    sheet = open_sheet(app)
    assert app._timesheet_return == (root, root, app.tree)
    assert not app.open_timesheet() and app.timesheet is sheet
    assert sheet.candidate is None
    assert sheet.close() and root.grab_current() is root
    wait_observed(root, lambda: root.focus_get() is app.tree,
        phase='Timesheet actual return focus', widgets=(app.tree,))
    assert not root.test_errors
    sheet = open_sheet(app)
    other = tk.Toplevel(root)
    pump(root, lambda: other.winfo_viewable())
    other.grab_set()
    other.focus_set()
    assert sheet.close() and root.grab_current() is other
    assert not app.open_timesheet() and root.grab_current() is other
    # This direct, deliberately rejected API call reports its existing primary
    # diagnostic; it is not an unexpected exception from a Tk callback.
    assert len(root.test_errors) == 1
    assert type(root.test_errors[0][1]) is ValueError
    assert str(root.test_errors[0][1]) == 'Timesheet cannot replace an unrelated or global grab'
    other.destroy()
    root.grab_release()
    fresh = open_sheet(app)
    label = ttk.Label(fresh.window)
    label.destroy()
    assert app.timesheet is fresh
    app._timesheet_disposed(sheet)
    assert app.timesheet is fresh
    fresh.window.destroy()
    assert app.timesheet is None and not app._timesheet_opening
    assert root.grab_current() is None
    unchanged(ordinary, before, ready, tmp_path)
    assert len(root.test_errors) == 1


def test_ordinary_schema4_global_grab_and_deleted_focus_origin_are_not_replaced(ordinary, root, request, tmp_path):
    app, worker, places = ordinary
    ready = production_readiness(ordinary, root, request)
    before = baseline(ordinary)
    other = tk.Toplevel(root)
    other.deiconify()
    pump(root, lambda: other.winfo_viewable())
    assert not root.test_errors
    other.grab_set_global()
    assert not app.open_timesheet()
    assert app.timesheet is None and not app._timesheet_opening
    assert app._timesheet_return is None
    assert root.grab_current() is other and other.grab_status() == 'global'
    assert baseline(ordinary) == before
    assert len(root.test_errors) == 1
    refusal = root.test_errors[0]
    assert type(refusal[1]) is ValueError
    assert str(refusal[1]) == 'Timesheet cannot replace an unrelated or global grab'
    other.destroy()
    assert root.grab_current() is None
    field = ttk.Entry(root)
    field.grid(row=8, column=0)
    pump(root, lambda: field.winfo_ismapped() and field.winfo_viewable())
    field.focus_set()
    wait_observed(root, lambda: root.focus_get() is field,
        phase='PRECONDITION Timesheet destroyed origin', widgets=(field,), foreground=True)
    sheet = open_sheet(app)
    field.destroy()
    assert not widget_live(field)
    assert sheet.close()
    wait_observed(root, lambda: root.focus_get() is root,
        phase='Timesheet root fallback focus', widgets=(root,))
    assert app.timesheet is None and not app._timesheet_opening
    assert root.grab_current() is None
    unchanged(ordinary, before, ready, tmp_path)
    assert root.test_errors == [refusal] and root.test_errors[0] is refusal
