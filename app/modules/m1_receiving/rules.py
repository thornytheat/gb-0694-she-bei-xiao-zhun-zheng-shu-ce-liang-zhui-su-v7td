from app.reader import read_rows
def apply(ctx):
    rows=read_rows(ctx)
    return {'rows':rows,'metrics':[['测量记录',len(rows),'条'],['输入',ctx['input_count'],'条'],['结构隔离',len(ctx['quarantine']),'条']]}

