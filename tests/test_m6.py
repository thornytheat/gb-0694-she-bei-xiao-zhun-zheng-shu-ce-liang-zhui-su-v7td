def test_measurement_conservation(ctx):assert ctx['balanced'] is True
def test_bad_certificate_rejected(ctx):assert next(r for r in ctx['verdicts'] if r['证书']=='C0002')['结论']=='拒用'
def test_good_certificate_accepted(ctx):assert next(r for r in ctx['verdicts'] if r['证书']=='C0001')['结论']=='可采用'
def test_out_of_range_reason(ctx):assert 'OUT_OF_RANGE' in next(r for r in ctx['verdicts'] if r['证书']=='C0007')['原因码']
def test_expired_reason(ctx):assert next(r for r in ctx['verdicts'] if r['证书']=='END')['原因码']=='INVALID_WINDOW'
def test_verdict_source_lines(ctx):assert all(r['行号']>=2 for r in ctx['verdicts'])
def test_partition(ctx):assert sum(r['结论']=='可采用' for r in ctx['verdicts'])+sum(r['结论']=='拒用' for r in ctx['verdicts'])==42

