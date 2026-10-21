"""Pure absolute-quarter proposals and whole-batch validation. No clocks or I/O."""
from dataclasses import dataclass
import re

from .polr_allocation import MAX_AMOUNT, civil
from .records import StaleState, canonical, integer, uuid_text

MAX_QUARTERS = MAX_AMOUNT // 25  # Decimal-hour hundredths must remain representable.
REQUEST_FIELDS = 'batch_id mode source_export_id source_metadata reviewed_rows selected_keys manual_cells acknowledgements'
ROW_FIELDS = 'task_id work_date task_name suggested_quarters prior_batch_id prior_quarters requires_stale_acknowledgement'
MANUAL_FIELDS = 'task_id work_date confirmed_quarters prior_batch_id prior_quarters'
ACK_FIELDS = 'task_id work_date suggested_quarters reviewed_prior_batch_id reviewed_prior_quarters'


@dataclass(frozen=True)
class ConfirmationCell:
    task_id: str
    work_date: str
    confirmed_quarters: int
    expected_prior_batch_id: str | None
    expected_prior_quarters: int | None
    stale_export_acknowledged: bool


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError(f'Expected exact confirmation fields: {names}')


def quarters(value):
    return integer(value,'Confirmed quarters',0,MAX_QUARTERS)


def parse_hours(value):
    if type(value) is not str or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',value.strip()):
        raise ValueError('Enter nonnegative decimal hours in exact 0.25 increments')
    whole,_,fraction=value.strip().partition('.')
    whole=whole.lstrip('0') or '0'
    if len(whole)>19: raise ValueError('POL-R hours overflow')
    hundredths=int(whole)*100+int(fraction.ljust(2,'0') or '0')
    if hundredths%25: raise ValueError('POL-R hours must be an exact multiple of 0.25')
    return quarters(hundredths//25)


def key(row):
    return uuid_text(row['task_id']),civil(row['work_date']).isoformat()


def prior(identity,value):
    if (identity is None)!=(value is None): raise ValueError('Prior identity and amount must both be present or Unknown')
    if identity is not None: uuid_text(identity);quarters(value)


def ordered(rows, names, *, nonempty=False):
    if type(rows) is not list or (nonempty and not rows): raise ValueError('Require a nonempty canonical cell list' if nonempty else 'Require a canonical cell list')
    keys=[]
    for row in rows: fields(row,names);keys.append(key(row))
    if keys!=sorted(set(keys)): raise ValueError('Cells must be distinct and in canonical task/date order')
    return keys


def source_metadata(source):
    return {**{k:getattr(source,k) for k in ('export_id','dataset_id','start_date','end_date','scope_kind','cutoff_utc_us','timezone','week_start','report_sha256')},
            'selected_task_ids':list(source.selected_task_ids),
            'source_tasks':[{'task_id':t.task_id,'name':t.name,'project_id':t.project_id,'project_name':t.project_name,'is_deleted':t.is_deleted}
                            for t in sorted(source.tasks,key=lambda t:t.task_id)]}


def stale(source_seq, value, proposed):
    return value is not None and value[2]>source_seq and value[1]!=proposed


def proposal(source, current, source_seq):
    names={t.task_id:t.name for t in source.tasks};rows=[];selected=[]
    for cell in sorted(source.cells,key=lambda c:(c.task_id,c.work_date)):
        k=(cell.task_id,cell.work_date);p=current.get(k)
        rows.append(dict(task_id=k[0],work_date=k[1],task_name=names[k[0]],suggested_quarters=cell.suggested_quarters,
                         prior_batch_id=p[0] if p else None,prior_quarters=p[1] if p else None,
                         requires_stale_acknowledgement=stale(source_seq,p,cell.suggested_quarters)))
        if cell.suggested_quarters>0:selected.append(dict(task_id=k[0],work_date=k[1]))
    return dict(source_metadata=source_metadata(source),reviewed_rows=rows,selected_keys=selected)


def validate_batch(arguments, *, source, source_seq, current, history, tasks):
    """Validate reviewed frozen coverage plus *selected* fresh priors, atomically."""
    fields(arguments,REQUEST_FIELDS);a=arguments;uuid_text(a['batch_id'])
    if type(a['mode']) is not str or a['mode'] not in ('source','manual'):raise ValueError('Invalid confirmation mode')
    ack_keys=ordered(a['acknowledgements'],ACK_FIELDS)
    for row in a['acknowledgements']:
        quarters(row['suggested_quarters']);prior(row['reviewed_prior_batch_id'],row['reviewed_prior_quarters'])
        if row['reviewed_prior_batch_id'] is None:raise ValueError('Acknowledgement requires a known reviewed prior')
    if a['mode']=='source':
        if source is None or uuid_text(a['source_export_id'])!=source.export_id:raise ValueError('Invalid source export')
        if canonical(a['source_metadata'])!=canonical(source_metadata(source)):raise ValueError('Reviewed frozen source metadata changed')
        if a['manual_cells']!=[] or type(a['manual_cells']) is not list:raise ValueError('Source mode has no manual cells')
        reviewed=ordered(a['reviewed_rows'],ROW_FIELDS)
        selected=ordered(a['selected_keys'],'task_id work_date',nonempty=True)
        expected={(c.task_id,c.work_date):(c.suggested_quarters,next(t.name for t in source.tasks if t.task_id==c.task_id)) for c in source.cells}
        if reviewed!=sorted(expected) or not set(selected)<=set(expected):raise ValueError('Complete in-scope frozen source coverage is required')
        cells=[];required=[]
        for row,k in zip(a['reviewed_rows'],reviewed):
            proposed,name=expected[k]
            if type(row['task_name']) is not str or row['task_name']!=name or quarters(row['suggested_quarters'])!=proposed:
                raise ValueError('Frozen source row differs')
            prior(row['prior_batch_id'],row['prior_quarters'])
            if type(row['requires_stale_acknowledgement']) is not bool:raise ValueError('Stale classification must be an actual boolean')
            p=None
            if row['prior_batch_id'] is not None:
                p=history.get((row['prior_batch_id'],*k))
                if p is None or p[0]!=row['prior_quarters']:raise ValueError('Reviewed prior evidence is invalid')
                p=(row['prior_batch_id'],p[0],p[1])
            if row['requires_stale_acknowledgement']!=stale(source_seq,p,proposed):raise ValueError('Forged stale-source classification')
            if k not in selected:continue
            actual=current.get(k)
            if (row['prior_batch_id'],row['prior_quarters'])!=((actual[0],actual[1]) if actual else (None,None)):
                raise StaleState('Reviewed confirmed prior changed; explicitly Refresh review')
            conflict=stale(source_seq,actual,proposed)
            if conflict:required.append(dict(task_id=k[0],work_date=k[1],suggested_quarters=proposed,
                                            reviewed_prior_batch_id=actual[0],reviewed_prior_quarters=actual[1]))
            cells.append(ConfirmationCell(*k,proposed,row['prior_batch_id'],row['prior_quarters'],conflict))
        if canonical(a['acknowledgements'])!=canonical(required):raise ValueError('Provide exactly the selected cell-specific stale acknowledgements')
    else:
        if a['source_export_id'] is not None or a['source_metadata'] is not None or a['reviewed_rows']!=[] or a['selected_keys']!=[] or a['acknowledgements']!=[]:
            raise ValueError('Manual mode has no source, selection or acknowledgement')
        for name in ('reviewed_rows','selected_keys','acknowledgements'):
            if type(a[name]) is not list:raise ValueError('Require canonical empty lists in manual mode')
        keys=ordered(a['manual_cells'],MANUAL_FIELDS,nonempty=True);cells=[]
        for row,k in zip(a['manual_cells'],keys):
            prior(row['prior_batch_id'],row['prior_quarters']);amount=quarters(row['confirmed_quarters']);actual=current.get(k)
            if (row['prior_batch_id'],row['prior_quarters'])!=((actual[0],actual[1]) if actual else (None,None)):
                raise StaleState('Reviewed confirmed prior changed; explicitly Refresh review')
            cells.append(ConfirmationCell(*k,amount,row['prior_batch_id'],row['prior_quarters'],False))
    if any(cell.task_id not in tasks for cell in cells):raise ValueError('Unknown confirmation task')
    return tuple(cells)
