from app.numeric import number
def apply(ctx):
    rows=[]
    for r in ctx['measurements']:
        valid=number(r['min_v'])<=number(r['value_v'])<=number(r['max_v']);r['range_valid']=valid
        rows.append({'证书':r['cert'],'测量值_V':r['value_v'],'下限_V':r['min_v'],'上限_V':r['max_v'],'量程':'符合' if valid else '超量程','行号':r['行号']})
    return {'rows':rows,'metrics':[['量程符合',sum(r['range_valid'] for r in ctx['measurements']),'条'],['超量程',sum(not r['range_valid'] for r in ctx['measurements']),'条']]}

