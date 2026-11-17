from app.domain import equivalence,volts
from decimal import Decimal
def test_missing_isolated(ctx): # TRAP-07
    assert any(q['原因码']=='MISSING' for q in ctx['quarantine'])
def test_device_code_preserved(ctx): # TRAP-08
    assert ctx['measurements'][1]['device']=='D0001'
def test_conflict_certificate_flag(ctx): # TRAP-14
    assert ctx['certs']['C0002']['conflicted'] is True
def test_alias_order_independent(): # TRAP-22
    rows=[{'device':'B','alias':'A'},{'device':'C','alias':'B'}];assert equivalence(rows)==equivalence(list(reversed(rows)))
def test_duplicate_not_add(ctx):assert ctx['duplicates']==1
def test_millivolt_conversion():assert volts('5000','mV')==Decimal('5')
def test_canonical_alias(ctx):assert ctx['measurements'][1]['canonical']=='D0001'


def test_invalid_measurement_alias_cannot_pollute_good_device(raw):
    import csv,io
    from app.pipeline import calculate
    records=list(csv.DictReader(io.StringIO(raw)));bad={**records[1],'alias':'D0003','value':'N/A'}
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=list(bad));writer.writeheader();writer.writerows(records+[bad])
    result=calculate(out.getvalue())
    assert result['certs']['C0003']['canonical']=='D0003'
    assert next(r['结论'] for r in result['verdicts'] if r['证书']=='C0003')=='可采用'
