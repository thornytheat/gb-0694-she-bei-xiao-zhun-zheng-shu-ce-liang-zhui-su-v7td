from collections import Counter
from app.modules.m6_verdict.rules import apply
from app.numeric import serial
def execute(ctx):
    before=len(ctx['quarantine'])
    result=apply(ctx)
    result['stage']=6
    result['name']='测量裁决'
    result['issues']=dict(Counter(row['原因码'] for row in ctx['quarantine']))
    result['new_quarantine']=len(ctx['quarantine'])-before
    ctx['stages'][str(6)]=serial(result)
    return ctx
