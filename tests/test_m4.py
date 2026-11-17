from app.modules.m4_ranges.rules import apply
from copy import deepcopy
def test_sample_out_of_range(ctx):assert sum(not r['range_valid'] for r in ctx['measurements'])==5
def test_voltage_normalization(ctx):assert next(r for r in ctx['measurements'] if r['cert']=='END')['value_v']=='5.000'
def test_lower_endpoint(ctx):
    c=deepcopy(ctx);c['measurements'][1]['value_v']='0';apply(c);assert c['measurements'][1]['range_valid'] is True
def test_upper_endpoint(ctx):
    c=deepcopy(ctx);c['measurements'][1]['value_v']='10';apply(c);assert c['measurements'][1]['range_valid'] is True
def test_negative_outside(ctx):
    c=deepcopy(ctx);c['measurements'][1]['value_v']='-0.001';apply(c);assert c['measurements'][1]['range_valid'] is False
def test_range_output_units(ctx):assert '测量值_V' in ctx['stages']['4']['rows'][0]
def test_root_range(ctx):assert ctx['measurements'][0]['range_valid'] is True

