"""Verify aggregation against the original dated measurements."""
import json,re
import numpy as np
import pandas as pd
from analysis import ROOT,load,SENSORS,aggregate
raw,_=load()
daily=pd.read_csv(ROOT/'data/daily_summary.csv',index_col='date',parse_dates=True)
web=json.loads((ROOT/'dashboard/data.json').read_text(encoding='utf-8'))
assert len(web['daily'])==len(daily)==214
assert (daily.samples>0).sum()==212
for date in ['2020-02-01','2020-04-18','2020-09-01']:
    actual=raw.loc[date]
    row=daily.loc[date]
    js=next(r for r in web['daily'] if r['date'][:10]==date)
    for s in SENSORS:
        for stat in ['mean','min','max','std','count']:
            expected=getattr(actual[s],stat)()
            np.testing.assert_allclose(row[s+'_'+stat],expected)
            np.testing.assert_allclose(js[s+'_'+stat],expected,atol=.000006)
for s in SENSORS:
    np.testing.assert_allclose(daily[s+'_ma7'],daily[s+'_mean'].rolling(7,min_periods=7).mean(),equal_nan=True)
for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',(ROOT/'README.md').read_text(encoding='utf-8')):
    assert (ROOT/target).is_file(),target
assert all(r['TP2_mean']==0 and r['assumed_off'] for r in web['daily'] if r['samples']==0)
assert len(web['hourly'])==214*24
assert all(r['TP2_mean']==0 for r in web['hourly'] if r['assumed_off'])
assert sum(r['assumed_off'] for r in web['hourly'])>0
print('PASS: original dates, daily aggregation, web statistics, missing days, moving averages, image links')
