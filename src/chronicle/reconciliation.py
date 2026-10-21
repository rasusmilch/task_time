"""Detached current reconciliation and calendar reminder eligibility; no I/O."""
from dataclasses import asdict
from datetime import timedelta

from .polr_allocation import Q, amount, actual_hundredths, civil, complete_week
from .records import uuid_text, integer
from .timesheet import resolve_period, scope_labels, scope_basis, week_starts
from .timekeeping import instant, load_zone, week_dates

CLASSIFICATIONS = ('NOT_APPLICABLE', 'UNKNOWN', 'MATCH', 'MISMATCH', 'UNAVAILABLE')


def classify(actual_us, suggested_quarters, confirmed_quarters):
    if actual_us is None or suggested_quarters is None:
        return 'UNAVAILABLE'
    amount(actual_us); amount(suggested_quarters)
    if confirmed_quarters is None:
        return 'UNKNOWN' if actual_us or suggested_quarters else 'NOT_APPLICABLE'
    amount(confirmed_quarters)
    return 'MATCH' if confirmed_quarters == suggested_quarters else 'MISMATCH'


def coverage(cells):
    counts = {name: 0 for name in CLASSIFICATIONS}
    for cell in cells:
        counts[cell['classification']] += 1
    applicable = sum(counts[k] for k in CLASSIFICATIONS if k != 'NOT_APPLICABLE')
    return dict(counts, applicable=applicable, outstanding=counts['UNKNOWN']+counts['MISMATCH'],
                complete=not (counts['UNKNOWN'] or counts['MISMATCH'] or counts['UNAVAILABLE']))


def adjustment_text(value):
    amount(value)
    minutes, rest = divmod(value, 60_000_000)
    seconds, micros = divmod(rest, 1_000_000)
    return f'{minutes} minutes, {seconds} seconds' + (f', {micros} microseconds' if micros else '')


def project(*, dataset_id, cutoff_utc_us, timezone, week_start, tasks, projects, work, active,
            current, period='this_week', start_date=None, end_date=None, scope_kind='all',
            task_ids=(), source=None, source_seq=None):
    """Compose shared attribution/allocation once, then join latest confirmed cells."""
    uuid_text(dataset_id); instant(cutoff_utc_us)
    integer(week_start,"Week start",0,6)
    zone=load_zone(timezone)
    first_day,last_day,visible_weeks=resolve_period(period,start_date,end_date,cutoff_utc_us,zone,week_start)
    first,last=first_day.isoformat(),last_day.isoformat()
    labels,_=scope_labels(tasks,projects,scope_kind,task_ids)
    for t in labels:
        uuid_text(t.task_id)
        if t.project_id is not None:uuid_text(t.project_id)
    requested={t.task_id for t in labels}
    union=requested | ({t.task_id for t in source.tasks} if source is not None else set())
    context_weeks=set(visible_weeks)
    if source is not None:
        context_weeks.update(week_starts(civil(source.start_date),civil(source.end_date),week_start))
    context_labels,chosen=scope_labels(tasks,projects,'selected' if union else 'all',tuple(sorted(union)))
    # One shared attribution pass; no duplicate or intervening unrequested week allocations.
    basis=scope_basis(context_labels,chosen,work,active,cutoff_utc_us,zone,tuple(sorted(context_weeks)))
    all_basis={(b.task_id,b.work_date):b for b in basis}
    basis=tuple(b for b in basis if b.task_id in requested and b.week_start_date in visible_weeks)
    by_task = {t.task_id: t for t in labels}
    daily, weeks = [], []
    grouped = {}
    for row in basis:
        prior = current.get((row.task_id,row.work_date))
        confirmed = prior['quarters'] if prior is not None else None
        batch = prior['batch_id'] if prior is not None else None
        value = asdict(by_task[row.task_id]); value.pop('ordinal')
        value['task_name'] = value.pop('name')
        value.update(work_date=row.work_date, exact_actual_us=row.actual_us,
            actual_hundredths=actual_hundredths(row.actual_us), suggested_quarters=row.suggested_quarters,
            confirmed_quarters=confirmed, current_batch_id=batch,
            daily_delta_hundredths=None if confirmed is None else actual_hundredths(row.actual_us)-25*confirmed,
            suggested_gap_quarters=None if confirmed is None else row.suggested_quarters-confirmed,
            classification=classify(row.actual_us,row.suggested_quarters,confirmed))
        grouped.setdefault((row.task_id,row.week_start_date),[]).append(value)
        if first <= row.work_date <= last:
            daily.append(value)
    for (task_id,start),cells in grouped.items():
        dates=complete_week(start)
        total=amount(sum(c['exact_actual_us'] for c in cells))
        target=amount(sum(c['suggested_quarters'] for c in cells))
        full=first<=start and last>=dates[-1]
        counts=coverage(cells)
        weeks.append(dict(task_id=task_id,task_name=by_task[task_id].name,
            project_id=by_task[task_id].project_id,project_name=by_task[task_id].project_name,
            week_start_date=start,week_end_date=dates[-1],exact_actual_us=total,
            actual_hundredths=amount(sum(c['actual_hundredths'] for c in cells)),
            weekly_target_quarters=target,weekly_adjustment_us=target*Q-total,
            allocation=[dict(work_date=c['work_date'],suggested_quarters=c['suggested_quarters']) for c in cells],
            known_confirmed_quarters=sum(c['confirmed_quarters'] or 0 for c in cells),
            confirmed_subtotal_is_complete=counts['UNKNOWN']==counts['UNAVAILABLE']==0,
            coverage=counts,visible_coverage=coverage(c for c in cells if first<=c['work_date']<=last),
            full_scope=full,review_complete=full and counts['complete']))
    cross=[]
    for start in visible_weeks:
        members=[w for w in weeks if w['week_start_date']==start]
        counts={k:sum(w['coverage'][k] for w in members) for k in (*CLASSIFICATIONS,'applicable','outstanding')}
        counts['complete']=all(w['coverage']['complete'] for w in members)
        cross.append(dict(week_start_date=start,week_end_date=complete_week(start)[-1],
            **{k:amount(sum(w[k] for w in members)) for k in ('exact_actual_us','actual_hundredths',
                'weekly_target_quarters','weekly_adjustment_us','known_confirmed_quarters')},
            coverage=counts,full_scope=first<=start and last>=complete_week(start)[-1],
            review_complete=first<=start and last>=complete_week(start)[-1] and all(w['review_complete'] for w in members),
            confirmed_subtotal_is_complete=all(w['confirmed_subtotal_is_complete'] for w in members)))
    comparison=None
    if source is not None:
        # Compare original in-scope cells under today's convention, even outside this view.
        if source.dataset_id!=dataset_id:raise ValueError('Wrong comparison dataset')
        compared=[]
        for old in source.cells:
            key=(old.task_id,old.work_date); now=all_basis[key]; prior=current.get(key)
            flags=[]
            if old.suggested_quarters!=now.suggested_quarters:flags.append('CURRENT_SUGGESTION_DIFFERS_FROM_FROZEN')
            if prior is not None and prior['seq']>source_seq and prior['quarters']!=old.suggested_quarters:
                flags.append('NEWER_DIFFERING_CONFIRMATION')
            compared.append(dict(task_id=old.task_id,work_date=old.work_date,
                frozen_suggested_quarters=old.suggested_quarters,current_suggested_quarters=now.suggested_quarters,
                confirmed_quarters=None if prior is None else prior['quarters'],current_batch_id=None if prior is None else prior['batch_id'],flags=flags))
        comparison=dict(export_id=source.export_id,frozen_week_start=source.week_start,
            current_week_start=week_start,start_date=source.start_date,end_date=source.end_date,cells=compared)
    counts=coverage(daily)
    return dict(dataset_id=dataset_id,cutoff_utc_us=cutoff_utc_us,timezone=timezone,week_start=week_start,
        period=period,start_date=first,end_date=last,scope_kind=scope_kind,selected_task_ids=sorted(task_ids),
        tasks=[asdict(t) for t in labels],daily_cells=daily,task_weeks=weeks,cross_task_weeks=cross,
        visible_totals=dict(exact_actual_us=amount(sum(c['exact_actual_us'] for c in daily)),
            actual_hundredths=amount(sum(c['actual_hundredths'] for c in daily)),
            suggested_quarters=amount(sum(c['suggested_quarters'] for c in daily)),
            known_confirmed_quarters=amount(sum(c['confirmed_quarters'] or 0 for c in daily))),
        coverage=counts,outstanding_counts={k:counts[k] for k in ('UNKNOWN','MISMATCH','outstanding')},
        source_comparison=comparison)


def reminder_periods(cutoff, zone, weekday):
    today,first,last=week_dates(cutoff,zone,weekday)
    return today,first-timedelta(days=7),last-timedelta(days=7),first,last,today.weekday() in (0,4)


def reminder_context(*, dataset_id, cutoff_utc_us, timezone, week_start, dismissed_local_date):
    """Readable metadata remains distinct from unavailable calculated coverage."""
    today,previous_start,previous_end,first,last,checked=reminder_periods(
        cutoff_utc_us,load_zone(timezone),week_start)
    return dict(dataset_id=dataset_id,cutoff_utc_us=cutoff_utc_us,local_today=today.isoformat(),
        timezone=timezone,week_start=week_start,previous_week_start=previous_start.isoformat(),
        previous_week_end=previous_end.isoformat(),previous_week_coverage_counts=None,
        previous_week_outstanding_counts=None,current_week_checked=checked,
        current_week_start=first.isoformat() if checked else None,current_week_end=last.isoformat() if checked else None,
        current_week_coverage_counts=None,current_week_outstanding_counts=None,
        dismissed_local_date=dismissed_local_date,evaluation_status='UNAVAILABLE',reminder_due=None,calculation_error=None)


def reminder_status(report, dismissed_local_date):
    result=reminder_context(dataset_id=report['dataset_id'],cutoff_utc_us=report['cutoff_utc_us'],
        timezone=report['timezone'],week_start=report['week_start'],dismissed_local_date=dismissed_local_date)
    def counts(start):
        end=(civil(start)+timedelta(days=6)).isoformat()
        return coverage(c for c in report['daily_cells'] if start<=c['work_date']<=end)
    previous=counts(result['previous_week_start'])
    current=counts(result['current_week_start']) if result['current_week_checked'] else None
    unavailable=previous['UNAVAILABLE'] or (current and current['UNAVAILABLE'])
    result.update(previous_week_coverage_counts=previous,
        previous_week_outstanding_counts={k:previous[k] for k in ('UNKNOWN','MISMATCH','outstanding')},
        current_week_coverage_counts=current,
        current_week_outstanding_counts=None if current is None else {k:current[k] for k in ('UNKNOWN','MISMATCH','outstanding')},
        evaluation_status='UNAVAILABLE' if unavailable else 'AVAILABLE',
        reminder_due=None if unavailable else dismissed_local_date!=result['local_today'] and bool(previous['outstanding'] or (current and current['outstanding'])))
    return result
