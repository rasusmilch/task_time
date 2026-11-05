"""Pure schema-4 project projection of one coordinated authoritative task report.

The existing accounting.calculate engine owns all time/calendar attribution and
task Individual/Cumulative calculation. This module never reads work or a clock.
"""
from copy import deepcopy

from .hierarchy import ProjectForest, candidate_task_observations
from .records import integer
from .timekeeping import instant

FIELDS = ('today_us', 'week_us')


def project_report(report, tasks, projects):
    """Preserve task/application facts and cutoff; add Direct/Cumulative projects.

    Requires complete coordinated observations and a successful accounting report.
    None/missing/invalid amounts refuse, never become zero. No runtime admission
    or frozen-export/POL-R calculation is supplied by this projection.
    """
    if type(report) is not dict:
        raise ValueError('Authoritative task accounting is unavailable')
    forest = ProjectForest(projects)
    candidate_task_observations(tasks, projects)
    try:
        instant(report['cutoff_utc_us'])
        keys = {t['task_id'] for t in tasks}
        for name in ('tasks', 'individual', 'cumulative'):
            if type(report[name]) is not dict or set(report[name]) != keys:
                raise ValueError('Accounting task coverage differs from current forest')
        totals = dict.fromkeys(FIELDS, 0)
        direct = {k: dict.fromkeys(FIELDS, 0) for k in (None, *forest.order)}
        for task in tasks:
            key, group = task['task_id'], task['project_id']
            for field in FIELDS:
                amount = integer(report['individual'][key][field], 'Task Individual', 0, 2**63-1)
                if integer(report['tasks'][key][field], 'Task amount', 0, 2**63-1) != amount:
                    raise ValueError('Accounting Individual differs from task report')
                integer(report['cumulative'][key][field], 'Task Cumulative', 0, 2**63-1)
                totals[field] = integer(totals[field]+amount, 'Application sum', 0, 2**63-1)
                direct[group][field] = integer(direct[group][field]+amount, 'Project Direct', 0, 2**63-1)
        for field in FIELDS:
            if integer(report['application'][field], 'Application amount', 0, 2**63-1) != totals[field]:
                raise ValueError('Application differs from task Individual sum')
        cumulative = deepcopy(direct)
        for key in forest.reverse_order:
            parent = forest.parents[key]
            if parent is not None:
                for field in FIELDS:
                    cumulative[parent][field] = integer(cumulative[parent][field]+cumulative[key][field],
                                                        'Project Cumulative', 0, 2**63-1)
    except (KeyError, TypeError) as error:
        raise ValueError('Incomplete or unavailable coordinated accounting report') from error
    result = deepcopy(report)
    result.update(project_direct=direct, projects=cumulative)
    return result
