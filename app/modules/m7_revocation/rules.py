from app.domain import descendants
def apply(ctx):
    rows=[]
    for cert,r in sorted(ctx['certs'].items()):
        if r['revoked']!='yes':continue
        affected=descendants(cert,ctx['certs']);measurements=[m for m in ctx['measurements'] if m['cert'] in affected]
        rows.append({'撤销源':cert,'影响证书':','.join(affected),'证书数':len(affected),'拒用测量':len(measurements),'复核':'需通知重测'})
    return {'rows':rows,'metrics':[['撤销源',len(rows),'份'],['影响证书',len({x for r in rows for x in r['影响证书'].split(',')}),'份'],['重测测量',sum(r['拒用测量'] for r in rows),'条']]}

