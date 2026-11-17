from app.domain import trace
def apply(ctx):
    chains={};rows=[]
    for key in sorted(ctx['certs']):
        outcome=trace(key,ctx['certs'])
        # A metadata conflict in any ancestor breaks the proof chain.
        if any(ctx['certs'].get(node,{}).get('conflicted') for node in outcome['path']):outcome['valid']=False;outcome['code']='REFERENCE_CONFLICT'
        chains[key]=outcome;rows.append({'证书':key,'溯源路径':' → '.join(outcome['path']),'原因码':outcome['code'],'状态':'可追溯' if outcome['valid'] else '中断'})
    ctx['chains']=chains
    return {'rows':rows,'metrics':[['可追溯',sum(r['valid'] for r in chains.values()),'份'],['中断',sum(not r['valid'] for r in chains.values()),'份']]}

