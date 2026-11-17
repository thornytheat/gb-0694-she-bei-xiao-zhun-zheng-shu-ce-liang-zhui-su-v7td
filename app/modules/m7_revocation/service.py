from collections import Counter
from app.modules.m7_revocation.rules import apply
from app.numeric import serial
def execute(ctx):
    before=len(ctx['quarantine'])
    result=apply(ctx)
    result['stage']=7
    result['name']='撤销复核'
    result['issues']=dict(Counter(row['原因码'] for row in ctx['quarantine']))
    result['new_quarantine']=len(ctx['quarantine'])-before
    ctx['stages'][str(7)]=serial(result)
    return ctx
