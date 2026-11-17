from app.domain import descendants
def test_revocation_source(ctx):assert ctx['stages']['7']['rows'][0]['撤销源']=='C0004'
def test_transitive_revocation(ctx):assert descendants('C0004',ctx['certs'])==['C0004','C0024']
def test_affected_measurements(ctx):assert ctx['stages']['7']['rows'][0]['拒用测量']==2
def test_leaf_revocation(ctx):assert descendants('C0040',ctx['certs'])==['C0040']
def test_missing_revocation_root(ctx):assert descendants('NONE',ctx['certs'])==['NONE']
def test_all_descendants_finite(ctx):assert len(descendants('ROOT',ctx['certs']))==42
def test_revoke_all_need_retest(ctx):assert all(r['复核']=='需通知重测' for r in ctx['stages']['7']['rows'])

