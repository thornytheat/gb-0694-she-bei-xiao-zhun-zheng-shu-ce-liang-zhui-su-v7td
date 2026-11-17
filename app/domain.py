from datetime import date
from app.numeric import number
from app.errors import DomainError
def day(text):
    try:return date.fromisoformat(text)
    except ValueError:raise DomainError('DATE','日期格式无效')
def volts(value,unit):
    factors={'V':1,'mV':number('0.001')}
    if unit not in factors:raise DomainError('UNIT','电压单位无效')
    return number(value)*factors[unit]
def equivalence(rows):
    parents={}
    def find(x):
        parents.setdefault(x,x)
        if parents[x]!=x:parents[x]=find(parents[x])
        return parents[x]
    for r in rows:
        a,z=find(r['device']),find(r['alias'] or r['device']);parents[max(a,z)]=min(a,z)
    return {x:find(x) for x in list(parents)}
def trace(cert,certs):
    path=[];current=cert;child=None
    while current:
        if current in path:return {'valid':False,'code':'CYCLE','path':path+[current]}
        path.append(current)
        if current not in certs:return {'valid':False,'code':'MISSING_REFERENCE','path':path}
        r=certs[current]
        if r['revoked']=='yes':return {'valid':False,'code':'REVOKED','path':path}
        if child and not day(r['valid_from'])<=day(child['valid_from'])<day(r['valid_to']):return {'valid':False,'code':'REFERENCE_EXPIRED','path':path}
        child=r;current=r['parent']
    return {'valid':True,'code':'TRACEABLE','path':path}
def descendants(start,certs):
    reached={start};todo=[start]
    while todo:
        node=todo.pop()
        for key,value in certs.items():
            if value['parent']==node and key not in reached:reached.add(key);todo.append(key)
    return sorted(reached)
