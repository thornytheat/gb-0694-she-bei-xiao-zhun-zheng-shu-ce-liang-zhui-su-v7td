from app.domain import trace
def test_reference_cycle(ctx): # TRAP-20
    certs={'A':{**ctx['certs']['ROOT'],'parent':'B'},'B':{**ctx['certs']['ROOT'],'parent':'A'}};result=trace('A',certs);assert result['code']=='CYCLE' and result['path']==['A','B','A']
def test_revoked_chain(ctx):assert ctx['chains']['C0024']['code']=='REVOKED'
def test_root_trusted(ctx):assert ctx['chains']['ROOT']['valid'] is True
def test_missing_reference(ctx):assert trace('ABSENT',ctx['certs'])['code']=='MISSING_REFERENCE'
def test_conflicted_ancestor(ctx):assert ctx['chains']['C0022']['code']=='REFERENCE_CONFLICT'
def test_reference_expired(ctx):
    certs={'A':{**ctx['certs']['C0001'],'parent':'B'},'B':{**ctx['certs']['ROOT'],'valid_to':'2026-01-01'}};assert trace('A',certs)['code']=='REFERENCE_EXPIRED'
def test_chain_contains_parent(ctx):assert ctx['chains']['C0021']['path']==['C0021','C0001','ROOT']

