from app.domain import day
def apply(ctx):
    rows=[]
    for r in ctx['measurements']:
        valid=day(r['valid_from'])<=day(r['measured_at'])<day(r['valid_to']);overlaps=[]
        for key,c in ctx['certs'].items():
            if key!=r['cert'] and c['canonical']==r['canonical'] and max(day(c['valid_from']),day(r['valid_from']))<min(day(c['valid_to']),day(r['valid_to'])):overlaps.append(key)
        r['window_valid']=valid and not overlaps and not ctx['certs'][r['cert']].get('conflicted',False)
        rows.append({'证书':r['cert'],'测量日':r['measured_at'],'生效日':r['valid_from'],'失效日':r['valid_to'],'重叠证书':','.join(sorted(overlaps)),'有效性':'有效' if r['window_valid'] else '无效','行号':r['行号']})
    return {'rows':rows,'metrics':[['有效测量',sum(r['window_valid'] for r in ctx['measurements']),'条'],['无效测量',sum(not r['window_valid'] for r in ctx['measurements']),'条']]}

