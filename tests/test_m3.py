from app.modules.m3_validity.rules import apply
from copy import deepcopy
def test_expiry_endpoint(ctx): # TRAP-23
    assert next(r for r in ctx['measurements'] if r['cert']=='END')['window_valid'] is False
def test_valid_sample(ctx):assert next(r for r in ctx['measurements'] if r['cert']=='C0001')['window_valid'] is True
def test_conflict_invalid_window(ctx):assert next(r for r in ctx['measurements'] if r['cert']=='C0002')['window_valid'] is False
def test_overlapping_certificates(ctx): # TRAP-25
    c=deepcopy(ctx);c['certs']['COPY']={**c['certs']['C0001'],'cert':'COPY'};apply(c);assert next(r for r in c['measurements'] if r['cert']=='C0001')['window_valid'] is False
def test_start_day_included(ctx):
    c=deepcopy(ctx);c['measurements'][1]['measured_at']='2026-01-01';apply(c);assert c['measurements'][1]['window_valid'] is True
def test_before_start_rejected(ctx):
    c=deepcopy(ctx);c['measurements'][1]['measured_at']='2025-12-31';apply(c);assert c['measurements'][1]['window_valid'] is False
def test_validity_evidence(ctx):assert len(ctx['stages']['3']['rows'])==42

