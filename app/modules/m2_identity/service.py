from collections import Counter
from app.modules.m2_identity.rules import apply
from app.numeric import serial
def execute(ctx):
    before=len(ctx['quarantine'])
    result=apply(ctx)
    result['stage']=2
    result['name']='设备别名'
    result['issues']=dict(Counter(row['原因码'] for row in ctx['quarantine']))
    result['new_quarantine']=len(ctx['quarantine'])-before
    ctx['stages'][str(2)]=serial(result)
    return ctx
