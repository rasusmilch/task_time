"""Detached frozen Timesheet values, exact scoped preparation and deterministic text.

No persistence or clocks. Recovery validates stored text against its original
request, not a future renderer or current task/work facts.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timedelta
import hashlib
import unicodedata

from .accounting import calculate_daily
from .polr_allocation import (Q, allocate_week, amount, actual_hundredths, civil,
                              complete_week, decimal_text, quarter_text)
from .records import integer, uuid_text
from .timekeeping import from_us, instant, load_zone, to_us, week_dates

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class TaskLabel:
    task_id: str
    name: str
    project_id: str | None
    project_name: str
    is_deleted: bool
    ordinal: int


@dataclass(frozen=True)
class Basis:
    task_id: str
    week_start_date: str
    work_date: str
    actual_us: int
    suggested_quarters: int


@dataclass(frozen=True)
class Cell:
    task_id: str
    work_date: str
    week_start_date: str
    actual_us: int
    actual_hundredths: int
    suggested_quarters: int


@dataclass(frozen=True)
class Candidate:
    export_id: str
    dataset_id: str
    start_date: str
    end_date: str
    cutoff_utc_us: int
    timezone: str
    week_start: int
    scope_kind: str
    selected_task_ids: tuple[str, ...]
    tasks: tuple[TaskLabel, ...]
    basis: tuple[Basis, ...]
    cells: tuple[Cell, ...]
    report_text: str
    report_sha256: str
    preferred_destination: str | None = None

    @property
    def report_utf8(self):
        return self.report_text.encode("utf-8")

    def content(self):
        """Strict JSON representation for the existing immutable Request."""
        value = asdict(self)
        for key in ("selected_task_ids", "tasks", "basis", "cells"):
            value[key] = list(value[key])
        return value


def _text(value):
    if type(value) is not str:
        raise ValueError("Frozen labels/text must be strings")
    value.encode("utf-8")
    return value


def escaped(value):
    return ''.join((f"\\u{ord(c):04x}" if unicodedata.category(c).startswith('C') or c in '\u2028\u2029'
                    else '\\\\' if c == '\\' else c) for c in value)


def week_starts(first, last, weekday):
    start = first - timedelta(days=(first.weekday() - weekday) % 7)
    final = last - timedelta(days=(last.weekday() - weekday) % 7)
    result = []
    while start <= final:
        complete_week(start.isoformat())
        result.append(start.isoformat())
        start += timedelta(days=7)
    return tuple(result)


def resolve_period(period, start_date, end_date, cutoff, zone, weekday):
    if period in ("this_week", "last_week") and start_date is None and end_date is None:
        _, first, last = week_dates(cutoff, zone, weekday)
        if period == "last_week":
            first, last = first - timedelta(days=7), last - timedelta(days=7)
    elif period == "custom":
        from .timekeeping import parse_date
        first, last = parse_date(start_date), parse_date(end_date)
        if last < first:
            raise ValueError("Start must not follow End")
    else:
        raise ValueError("Use This week, Last week or inclusive Custom")
    weeks = week_starts(first, last, weekday)
    # Validate expanded local/UTC boundaries even for an empty report.
    to_us(datetime.combine(civil(weeks[0]), time(), zone))
    to_us(datetime.combine(civil(weeks[-1]) + timedelta(days=7), time(), zone))
    return first, last, weeks


def render(candidate):
    c = candidate
    lines = ["Chronicle Timesheet / POL-R", f"Report ID: {c.export_id}",
             f"Dates: {c.start_date} to {c.end_date} (inclusive)",
             f"As of UTC: {from_us(c.cutoff_utc_us).isoformat(timespec='microseconds')}",
             f"Timezone: {c.timezone}", f"Week starts: {WEEKDAYS[c.week_start]}",
             f"Scope: {'All tasks' if c.scope_kind == 'all' else 'Selected tasks'}",
             "Status: Suggested values only; not confirmed with POL-R",
             "Suggested values are absolute replacements, not Delta. Current-week suggestions may change.",
             "Preview is not a submitted report or verified external record.",
             "Actual HH:MM shows completed minutes; exact weekly microseconds retain residual precision."]
    for task in c.tasks:
        lines += ["", f"Project: {escaped(task.project_name)}", f"Task: {escaped(task.name)}",
                  f"Task UUID: {task.task_id}", f"Task status: {'Deleted' if task.is_deleted else 'Active'}",
                  "Date | Actual HH:MM | Actual decimal | Suggested POL-R"]
        for cell in c.cells:
            if cell.task_id == task.task_id:
                minutes = cell.actual_us // 60_000_000
                lines.append(f"{cell.work_date} | {minutes//60}:{minutes%60:02d} | "
                             f"{decimal_text(cell.actual_hundredths)} | {quarter_text(cell.suggested_quarters)}")
        for first in dict.fromkeys(b.week_start_date for b in c.basis if b.task_id == task.task_id):
            rows = [b for b in c.basis if b.task_id == task.task_id and b.week_start_date == first]
            total, target = sum(b.actual_us for b in rows), sum(b.suggested_quarters for b in rows)
            minutes = total // 60_000_000
            last = complete_week(first)[-1]
            lines += [f"Full week: {first} to {last}",
                      f"Exact weekly Actual: {minutes//60}:{minutes%60:02d} ({total} microseconds)",
                      f"POL-R weekly target: {quarter_text(target)}",
                      f"Exact upward adjustment: {target*Q-total} microseconds",
                      "Displayed scope: " + ("complete week" if c.start_date <= first and c.end_date >= last else "partial week")]
    if not c.tasks:
        lines += ["", "No tasks (valid empty All report)."]
    lines += ["", f"Displayed Actual total: {decimal_text(amount(sum(x.actual_hundredths for x in c.cells)))}",
              f"In-scope Suggested POL-R total: {quarter_text(amount(sum(x.suggested_quarters for x in c.cells)))}"]
    return '\n'.join(lines) + '\n'


def validate(candidate, *, check_render=True):
    c = candidate
    if type(c) is not Candidate:
        raise ValueError("Require a frozen Timesheet candidate")
    uuid_text(c.export_id); uuid_text(c.dataset_id); instant(c.cutoff_utc_us)
    zone = load_zone(c.timezone)
    integer(c.week_start, "Week start", 0, 6)
    first, last = civil(c.start_date), civil(c.end_date)
    if last < first:
        raise ValueError("Invalid report dates")
    weeks = week_starts(first, last, c.week_start)
    to_us(datetime.combine(civil(weeks[0]), time(), zone))
    to_us(datetime.combine(civil(weeks[-1]) + timedelta(days=7), time(), zone))
    if c.scope_kind not in ("all", "selected") or type(c.scope_kind) is not str:
        raise ValueError("Invalid scope")
    for value in (c.selected_task_ids, c.tasks, c.basis, c.cells):
        if type(value) is not tuple:
            raise ValueError("Candidate members must be immutable tuples")
    ids = []
    for i, task in enumerate(c.tasks):
        if type(task) is not TaskLabel:
            raise ValueError("Invalid frozen task")
        uuid_text(task.task_id)
        if task.project_id is not None:
            uuid_text(task.project_id)
        _text(task.name); _text(task.project_name)
        if not task.name.strip() or not task.project_name.strip() or type(task.is_deleted) is not bool:
            raise ValueError("Invalid task label/status")
        if task.project_id is None and task.project_name != 'Unassigned':
            raise ValueError("Invalid Unassigned label")
        if type(task.ordinal) is not int or task.ordinal != i:
            raise ValueError("Invalid display ordinal")
        ids.append(task.task_id)
    if len(set(ids)) != len(ids) or tuple(sorted(c.tasks, key=lambda t:(t.project_name,t.name,t.task_id))) != c.tasks:
        raise ValueError("Duplicate or unordered task scope")
    for task_id in c.selected_task_ids:
        uuid_text(task_id)
    if (tuple(sorted(set(c.selected_task_ids))) != c.selected_task_ids
            or (c.scope_kind == 'all' and c.selected_task_ids)
            or (c.scope_kind == 'selected' and (not ids or set(ids) != set(c.selected_task_ids)))):
        raise ValueError("Invalid Selected identity")
    expected_basis, expected_cells = [], []
    by_key = {}
    for row in c.basis:
        if type(row) is not Basis:
            raise ValueError("Invalid basis record")
        key = (row.task_id,row.week_start_date,row.work_date)
        if key in by_key:
            raise ValueError("Duplicate basis")
        by_key[key] = row
    for task_id in ids:
        for week in weeks:
            rows = []
            for day in complete_week(week):
                row = by_key.get((task_id,week,day))
                if row is None:
                    raise ValueError("Missing complete-week basis")
                amount(row.actual_us); amount(row.suggested_quarters)
                rows.append(row)
            allocated = allocate_week(week, tuple((r.work_date,r.actual_us) for r in rows))
            if tuple((r.work_date,r.suggested_quarters) for r in rows) != allocated:
                raise ValueError("Incorrect full-week allocation")
            expected_basis.extend(rows)
            expected_cells.extend(Cell(task_id,r.work_date,week,r.actual_us,actual_hundredths(r.actual_us),r.suggested_quarters)
                                  for r in rows if c.start_date <= r.work_date <= c.end_date)
    if tuple(expected_basis) != c.basis or tuple(expected_cells) != c.cells or any(type(r) is not Cell for r in c.cells):
        raise ValueError("Incomplete, extra, unordered or inconsistent frozen coverage")
    for cell in c.cells:
        amount(cell.actual_us); amount(cell.actual_hundredths); amount(cell.suggested_quarters)
    amount(sum(r.actual_us for r in c.cells), "Scoped Actual total")
    amount(sum(r.actual_hundredths for r in c.cells), "Displayed total")
    amount(sum(r.suggested_quarters for r in c.cells)*Q, "Scoped suggested duration")
    if c.preferred_destination is not None and (type(c.preferred_destination) is not str or not c.preferred_destination.strip() or '\x00' in c.preferred_destination):
        raise ValueError("Invalid preferred destination")
    _text(c.report_text)
    if type(c.report_sha256) is not str or hashlib.sha256(c.report_utf8).hexdigest() != c.report_sha256:
        raise ValueError("Frozen UTF-8 digest disagrees")
    if check_render and render(c) != c.report_text:
        raise ValueError("Frozen report disagrees with candidate")
    return c


def from_content(value, *, check_render=True):
    if type(value) is not dict or set(value) != set(Candidate.__dataclass_fields__):
        raise ValueError("Invalid complete candidate fields")
    data = dict(value)
    for key, cls in (("tasks",TaskLabel),("basis",Basis),("cells",Cell)):
        if type(data[key]) is not list:
            raise ValueError("Candidate request arrays must be lists")
        if any(type(row) is not dict or set(row) != set(cls.__dataclass_fields__) for row in data[key]):
            raise ValueError("Invalid candidate record fields")
        data[key] = tuple(cls(**row) for row in data[key])
    if type(data['selected_task_ids']) is not list:
        raise ValueError("Selected identities must be a list")
    data['selected_task_ids'] = tuple(data['selected_task_ids'])
    return validate(Candidate(**data), check_render=check_render)


def scope_labels(tasks, projects, scope_kind, task_ids):
    if type(task_ids) not in (tuple,list) or scope_kind not in ('all','selected'):
        raise ValueError("Explicit All/Selected scope required")
    for key in task_ids: uuid_text(key)
    if len(set(task_ids)) != len(task_ids) or (scope_kind=='all' and task_ids) or (scope_kind=='selected' and not task_ids):
        raise ValueError("Selected requires distinct nonempty UUIDs; All has no selected IDs")
    known = {t['task_id']:t for t in tasks}
    if not set(task_ids) <= set(known): raise ValueError("Unknown selected task")
    chosen = tasks if scope_kind=='all' else [known[k] for k in task_ids]
    project_names = {p['project_id']:p['name'] for p in projects}
    labels = [TaskLabel(t['task_id'],t['name'],t['project_id'],
                        project_names[t['project_id']] if t['project_id'] else 'Unassigned',False,0) for t in chosen]
    labels = tuple(replace(t,ordinal=i) for i,t in enumerate(sorted(labels,key=lambda t:(t.project_name,t.name,t.task_id))))
    return labels,chosen


def calculate_scope(*, cutoff_utc_us, timezone, week_start, tasks, projects, work, active,
            period="this_week", start_date=None, end_date=None, scope_kind="all", task_ids=()):
    instant(cutoff_utc_us)
    integer(week_start,"Week start",0,6)
    zone = load_zone(timezone)
    first,last,weeks = resolve_period(period,start_date,end_date,cutoff_utc_us,zone,week_start)
    labels,chosen = scope_labels(tasks,projects,scope_kind,task_ids)
    basis = scope_basis(labels,chosen,work,active,cutoff_utc_us,zone,weeks)
    cells = tuple(Cell(b.task_id,b.work_date,b.week_start_date,b.actual_us,actual_hundredths(b.actual_us),b.suggested_quarters)
                  for b in basis if first.isoformat()<=b.work_date<=last.isoformat())
    return first.isoformat(),last.isoformat(),labels,basis,cells


def scope_basis(labels, chosen, work, active, cutoff, zone, weeks):
    """Shared attribution once; allocate only the requested complete context weeks."""
    selected = {t.task_id for t in labels}
    daily = calculate_daily(chosen,[r for r in work if r['task_id'] in selected],
                            active if active and active['task_id'] in selected else None,
                            cutoff,zone,civil(weeks[0]),civil(weeks[-1])+timedelta(days=6))
    basis = []
    for task in labels:
        for week in weeks:
            values = tuple((d,daily[task.task_id].get(d,0)) for d in complete_week(week))
            for (day,actual),(d,quarters) in zip(values,allocate_week(week,values)):
                basis.append(Basis(task.task_id,week,day,actual,quarters))
    return tuple(basis)


def prepare(*, export_id, dataset_id, cutoff_utc_us, timezone, week_start, tasks, projects, work, active,
            period="this_week", start_date=None, end_date=None, scope_kind="all", task_ids=()):
    uuid_text(export_id); uuid_text(dataset_id)
    first,last,labels,basis,cells = calculate_scope(cutoff_utc_us=cutoff_utc_us,timezone=timezone,
        week_start=week_start,tasks=tasks,projects=projects,work=work,active=active,period=period,
        start_date=start_date,end_date=end_date,scope_kind=scope_kind,task_ids=task_ids)
    c = Candidate(export_id,dataset_id,first,last,cutoff_utc_us,timezone,week_start,
                  scope_kind,tuple(sorted(task_ids)),labels,basis,cells,'','')
    text = render(c)
    return validate(replace(c,report_text=text,report_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()))
