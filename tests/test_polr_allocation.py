"""Independent exact examples and bounds for the selected full-week algorithm."""
from datetime import date,timedelta
import random

import pytest

from chronicle.polr_allocation import (Q,MAX_AMOUNT,allocate_week,actual_hundredths,
                                      complete_week,decimal_text,quarter_text)

FIRST='2026-10-18'
DAYS=complete_week(FIRST)
M=60_000_000


def week(values):
    return tuple((d,values[i] if i<len(values) else 0) for i,d in enumerate(DAYS))


@pytest.mark.parametrize('mon,tue,target,expected,adjustment',[
    (68,67,9,(5,4),0), (68,68,10,(5,5),14), (70,20,6,(5,1),0),
    (3,3,1,(1,0),9),(15,30,3,(1,2),0)])
def test_mandatory_C_through_G(mon,tue,target,expected,adjustment):
    result=dict(allocate_week(FIRST,week([0,mon*M,tue*M])))
    assert (result[DAYS[1]],result[DAYS[2]])==expected
    assert sum(result.values())==target
    assert target*Q-(mon+tue)*M==adjustment*M
    assert all(result[d]==0 for d in (DAYS[0],*DAYS[3:]))


@pytest.mark.parametrize('values,expected',[
    ([],[0]*7),([Q],[1,0,0,0,0,0,0]),([1],[1,0,0,0,0,0,0]),
    ([M]*7,[1,0,0,0,0,0,0]),([14*M,13*M,12*M],[1,1,1,0,0,0,0]),
    ([Q,3*M,3*M],[1,1,0,0,0,0,0]),([4*M,11*M],[0,1,0,0,0,0,0])])
def test_independent_expected_distributions(values,expected):
    assert list(dict(allocate_week(FIRST,week(values))).values())==expected


def test_permutation_and_conservation_many_exact_integer_weeks():
    rng=random.Random(478)
    for _ in range(150):
        values=[rng.randrange(0,5*Q) if rng.randrange(3) else 0 for _ in DAYS]
        pairs=list(week(values)); rng.shuffle(pairs)
        result=allocate_week(FIRST,tuple(pairs))
        assert result==allocate_week(FIRST,week(values))
        quarters=[q for d,q in result]
        target=sum(quarters)
        assert target==(sum(values)+Q-1)//Q
        assert 0<=target*Q-sum(values)<Q
        assert all(q in (a//Q,a//Q+1) for a,q in zip(values,quarters))
        assert all(q==0 for a,q in zip(values,quarters) if a==0)


@pytest.mark.parametrize('bad',[True,1.0,-1,'5',None,MAX_AMOUNT+1,MAX_AMOUNT])
def test_bad_units_and_converted_target_overflow(bad):
    with pytest.raises(ValueError): allocate_week(FIRST,week([bad]))


@pytest.mark.parametrize('bad',[(),week([])[:-1],(*week([]),week([])[0]),
    ((DAYS[0],0),)*7,tuple(('2026-02-30' if i==1 else d,0) for i,d in enumerate(DAYS))])
def test_missing_extra_duplicate_invalid_dates(bad):
    with pytest.raises(ValueError): allocate_week(FIRST,bad)


@pytest.mark.parametrize('first',['9999-12-27','0000-01-01',' 2026-10-18 ','2026-02-30'])
def test_unrepresentable_or_noncanonical_week(first):
    with pytest.raises(ValueError): allocate_week(first,week([]))


@pytest.mark.parametrize('weekday',range(7))
def test_seven_start_conventions_are_calendar_dates(weekday):
    first=date(2026,10,18)+timedelta(days=(weekday-6)%7)
    days=complete_week(first.isoformat())
    assert first.weekday()==weekday
    result=allocate_week(days[0],tuple((d,3*M if i in (1,2) else 0) for i,d in enumerate(days)))
    assert result[1][1]==1 and result[2][1]==0


@pytest.mark.parametrize('us,expected',[(0,0),(200*M,333),(M,2),(17_999_999,0),(18_000_000,1),(18_000_001,1),(53_999_999,1),(54_000_000,2),(1,0)])
def test_exact_half_up_hundredths(us,expected): assert actual_hundredths(us)==expected


def test_cell_sum_differs_from_rerounded_raw_aggregate():
    assert actual_hundredths(M)+actual_hundredths(M)==4
    assert actual_hundredths(2*M)==3
    assert [quarter_text(q) for q in range(5)]==['0.00','0.25','0.50','0.75','1.00']
    assert decimal_text(333)=='3.33'


@pytest.mark.parametrize('bad',[True,0.5,-1,None])
def test_display_rejects_bad_units(bad):
    for f in (actual_hundredths,decimal_text,quarter_text):
        with pytest.raises(ValueError): f(bad)
