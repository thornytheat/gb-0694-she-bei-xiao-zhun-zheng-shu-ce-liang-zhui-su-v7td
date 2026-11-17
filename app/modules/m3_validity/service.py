from collections import Counter
from app.modules.m3_validity.rules import apply
from app.numeric import serial
def execute(ctx):
    before=len(ctx['quarantine'])
    result=apply(ctx)
    result['stage']=3
    result['name']='有效区间'
    result['issues']=dict(Counter(row['原因码'] for row in ctx['quarantine']))
    result['new_quarantine']=len(ctx['quarantine'])-before
    ctx['stages'][str(3)]=serial(result)
    return ctx
