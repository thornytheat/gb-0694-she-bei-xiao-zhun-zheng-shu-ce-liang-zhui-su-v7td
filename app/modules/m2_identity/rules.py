from app.domain import day,equivalence,volts
from app.numeric import number
from app.errors import DomainError
from app.reasons import isolate
def apply(ctx):
    certs={};measurements=[];seen=set();duplicates=0;conflicted=set()
    fields=('device','parent','valid_from','valid_to','minimum','maximum','unit','revoked','version')
    for r in ctx['rows']:
        try:
            if not r['cert'] or not r['device']:raise DomainError('MISSING','证书或设备为空')
            start,end=day(r['valid_from']),day(r['valid_to']);day(r['measured_at']);value=volts(r['value'],r['measure_unit']);minimum=volts(r['minimum'],r['unit']);maximum=volts(r['maximum'],r['unit'])
            if start>=end or minimum>maximum:raise DomainError('RANGE','证书区间无效')
            if r['revoked'] not in ('yes','no'):raise DomainError('REVOKED_FLAG','撤销标识无效')
            if r['version']!='1':raise DomainError('VERSION','不支持的证书版本')
            item={**r,'value_v':str(value),'min_v':str(minimum),'max_v':str(maximum)}
            if r['cert'] in certs and any(certs[r['cert']][k]!=r[k] for k in fields):conflicted.add(r['cert']);isolate(ctx,r,'CONFLICT','同证书定义冲突');continue
            key=(r['cert'],r['measured_at'],r['value'],r['measure_unit'])
            if key in seen:duplicates+=1;continue
            seen.add(key);certs[r['cert']]=item;measurements.append(item)
        except DomainError as e:isolate(ctx,r,e.code,e.message)
    # A conflicted certificate is never trusted for either retained or later measurements.
    for cert in conflicted:certs[cert]['conflicted']=True
    names=equivalence([r for r in measurements if r['cert'] not in conflicted])
    for r in measurements: r['canonical']=names.get(r['device'],r['device'])
    ctx.update(certs=certs,measurements=measurements,duplicates=duplicates)
    return {'rows':[{'证书':r['cert'],'设备':r['canonical'],'别名':r['alias'],'父证书':r['parent'],'定义状态':'冲突' if r['cert'] in conflicted else '一致','行号':r['行号']} for r in measurements],'metrics':[['证书',len(certs),'份'],['冲突定义',len(conflicted),'份'],['重复',duplicates,'条']]}

