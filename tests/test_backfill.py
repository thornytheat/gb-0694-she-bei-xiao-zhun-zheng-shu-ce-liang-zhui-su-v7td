"""M7 back-dated revocation: version derivation, effective-date boundary,
immutable review evidence, resumable journal, retry reuse, destinations."""
import copy

import pytest

from app.backfill.engine import build_derived, derived_run_id, evidence_hash
from app.backfill.service import evidence_bundle
from app.pipeline import calculate

FIXTURE = (
    'cert,device,alias,parent,valid_from,valid_to,minimum,maximum,unit,revoked,'
    'measured_at,value,measure_unit,version\n'
    'ROOT,REF-001,标准源,,2025-01-01,2028-01-01,0,1000,V,no,2026-05-01,100,V,1\n'
    'S1,STD-01,工作标准器,ROOT,2026-01-01,2027-01-01,0,100,V,no,2026-05-01,50,V,1\n'
    'C100,D100,表A,S1,2026-01-01,2027-01-01,0,10,V,no,2026-05-01,5,V,1\n'
    'C100,D100,表A,S1,2026-01-01,2027-01-01,0,10,V,no,2026-07-01,5,V,1\n'
    'C101,D101,表B,S1,2026-01-01,2027-01-01,0,10,V,no,2026-05-01,5,V,1\n'
    'C101,D101,表B,S1,2026-01-01,2027-01-01,0,10,V,no,2026-07-01,5,V,1\n'
    'C200,D200,独立表,ROOT,2026-01-01,2027-01-01,0,10,V,no,2026-05-01,5,V,1\n'
    'C200,D200,独立表,ROOT,2026-01-01,2027-01-01,0,10,V,no,2026-07-01,5,V,1\n'
)


@pytest.fixture
def base_run(client):
    return client.post('/api/run', json={'csv': FIXTURE}).get_json()


def _rev(client, run_id, standard='S1', date='2026-06-01', **extra):
    body = {'run_id': run_id, 'standard_id': standard, 'effective_date': date, **extra}
    return client.post('/api/revocations', json=body)


# ---------- pure engine: effective-date boundary ----------

def test_pre_effective_verdicts_are_retained():
    base = calculate(FIXTURE)
    payload, affected, retests = build_derived(base, 'rev1', 'S1', '2026-06-01')
    assert affected == ['C100', 'C101', 'S1']
    by_line = {v['行号']: v for v in payload['verdicts']}
    # Two C100 measurements: May (pre-date) keeps ACCEPT, July is rejected.
    may = next(v for v in payload['verdicts'] if v['证书'] == 'C100' and v['测量日'] == '2026-05-01')
    july = next(v for v in payload['verdicts'] if v['证书'] == 'C100' and v['测量日'] == '2026-07-01')
    assert may['结论'] == '可采用' and may['原结论'] == '可采用'
    assert may['生效日判断'] == '生效日前维持原判断'
    assert july['结论'] == '拒用' and 'BACKFILL_REVOKED' in july['原因码']
    assert july['原结论'] == '可采用'  # original evidence preserved in derived view
    # Only the two post-date affected measurements need retesting.
    assert sorted((r['cert_id'], r['measured_at']) for r in retests) == [
        ('C100', '2026-07-01'), ('C101', '2026-07-01')]
    # Unaffected branch never changes.
    independent = next(v for v in payload['verdicts'] if v['证书'] == 'C200'
                       and v['测量日'] == '2026-07-01')
    assert independent['结论'] == '可采用' and independent['原因码'] == 'ACCEPT'


def test_effective_date_is_closed_boundary():
    base = calculate(FIXTURE)
    payload, _, retests = build_derived(base, 'rev1', 'S1', '2026-07-01')
    on_date = next(v for v in payload['verdicts'] if v['证书'] == 'C100'
                   and v['测量日'] == '2026-07-01')
    assert on_date['结论'] == '拒用'  # measured_at >= effective_date
    assert len(retests) == 2


def test_original_payload_is_not_mutated():
    base = calculate(FIXTURE)
    payload, _, _ = build_derived(base, 'rev1', 'S1', '2026-06-01')
    assert base['chains']['S1']['code'] == 'TRACEABLE'
    assert base['chains']['S1'].get('backfill') is None
    assert payload['chains']['S1']['code'] == 'BACKFILL_REVOKED'
    assert base['certs']['S1'].get('backfill_revoked') is None
    assert payload['certs']['S1']['backfill_revoked'] == 'S1'
    assert all('原结论' not in row for row in base['verdicts'])


def test_derived_id_and_evidence_hash_are_deterministic():
    base = calculate(FIXTURE)
    p1, _, _ = build_derived(base, 'rev1', 'S1', '2026-06-01')
    p2, _, _ = build_derived(base, 'rev1', 'S1', '2026-06-01')
    assert p1['manifest']['run_id'] == p2['manifest']['run_id'] == derived_run_id('rev1')
    assert p1['manifest']['sha256'] == evidence_hash(p1)
    assert p1['manifest']['sha256'] == p2['manifest']['sha256']
    assert p1['manifest']['lineage_root'] == base['manifest']['run_id']


def test_unknown_standard_and_bad_date_are_rejected():
    base = calculate(FIXTURE)
    with pytest.raises(Exception):
        build_derived(base, 'rev1', 'NOPE', '2026-06-01')
    with pytest.raises(Exception):
        build_derived(base, 'rev1', 'S1', 'not-a-date')


# ---------- HTTP flow ----------

def test_create_switches_current_and_keeps_original_review(client, base_run):
    rid = base_run['manifest']['run_id']
    # Review the original first; its evidence must survive the switch.
    client.post('/api/review', json={'id': rid, 'revision': 1, 'decision': '通过'})
    resp = _rev(client, rid)
    assert resp.status_code == 200 and resp.get_json()['status'] == 'applied'
    ident = resp.get_json()['id']

    current = client.get('/api/batches/' + rid + '/current').get_json()
    assert current['current_id'] != rid
    derived = current['run']
    assert derived['manifest']['derived_from'] == rid

    original = client.get('/api/runs/' + rid).get_json()
    assert original['decision'] == '通过' and original['revision'] == 2
    assert original['chains']['S1']['code'] == 'TRACEABLE'
    assert derived['chains']['S1']['code'] == 'BACKFILL_REVOKED'

    versions = current['versions']
    assert versions[0]['parent_id'] == rid and versions[0]['is_current'] == 1
    bundle = client.get('/api/revocations/' + ident + '/evidence').get_json()
    assert bundle['original']['decision'] == '通过'
    assert len(bundle['bundle_sha256']) == 64


def test_retry_reuses_same_record_and_derived_version(client, base_run):
    rid = base_run['manifest']['run_id']
    first = _rev(client, rid).get_json()
    again = _rev(client, rid).get_json()
    assert again['reused'] is True and again['id'] == first['id']
    assert again['derived_run_id'] == first['derived_run_id']
    assert client.get('/api/revocations?run_id=' + rid).get_json() == [
        client.get('/api/revocations?run_id=' + rid).get_json()[0]]
    assert len(client.get('/api/revocations?run_id=' + rid).get_json()) == 1
    # Idempotent content-addressed store still holds one derived payload.
    assert client.get('/api/runs/' + first['derived_run_id']).status_code == 200


def test_derive_fault_is_resumable_and_keeps_current_pointer(client, base_run):
    rid = base_run['manifest']['run_id']
    resp = _rev(client, rid, fault_plan={'stage': 'derive', 'fail_after_items': 1})
    rec = resp.get_json()
    assert rec['status'] == 'interrupted'
    assert client.get('/api/batches/' + rid + '/current').get_json()['current_id'] == rid

    resumed = client.post('/api/revocations/' + rec['id'] + '/resume', json={}).get_json()
    assert resumed['status'] == 'applied' and resumed['id'] == rec['id']
    current = client.get('/api/batches/' + rid + '/current').get_json()
    assert current['current_id'] == resumed['derived_run_id']
    # Journal shows the blocked item was retried and the switch completed.
    journal = evidence_bundle(rec['id'])['journal']
    statuses = {(j['stage'], j['item_key']): j['status'] for j in journal}
    assert statuses[('derive', 'S1')] == 'done'
    assert statuses[('derive', 'C100')] == 'done'
    assert statuses[('switch', '__batch__')] == 'done'


def test_switch_failure_leaves_original_evidence_visible(client, base_run):
    rid = base_run['manifest']['run_id']
    rec = _rev(client, rid, fault_plan={'stage': 'switch', 'fail_after_items': 0}).get_json()
    assert rec['status'] == 'interrupted'
    # Pointer untouched: the archive still serves the original batch.
    assert client.get('/api/batches/' + rid + '/current').get_json()['current_id'] == rid
    detail_page = client.get('/revocations/' + rec['id']).data.decode()
    assert '原复核证据' in detail_page and '续跑处理' in detail_page
    # Resume clears the old fault plan and completes the switch.
    resumed = client.post('/api/revocations/' + rec['id'] + '/resume', json={}).get_json()
    assert resumed['status'] == 'applied'
    assert client.get('/api/batches/' + rid + '/current').get_json()['current_id'] \
        == resumed['derived_run_id']


def test_retry_clears_stale_fault_plan(client, base_run):
    rid = base_run['manifest']['run_id']
    rec = _rev(client, rid, fault_plan={'stage': 'derive', 'fail_after_items': 0}).get_json()
    assert rec['status'] == 'interrupted'
    # Re-POST with the same natural key and no fault plan: reuse + complete.
    again = _rev(client, rid).get_json()
    assert again['id'] == rec['id'] and again['status'] == 'applied'
    assert again['fault_plan'] is None
    # A blocked row remains in the journal as historical evidence of the stop.
    journal = evidence_bundle(rec['id'])['journal']
    assert any(j['status'] == 'blocked' for j in journal)
    assert any(j['status'] == 'done' and j['stage'] == 'switch' for j in journal)


def test_retest_destinations_and_validation(client, base_run):
    rid = base_run['manifest']['run_id']
    ident = _rev(client, rid).get_json()['id']
    retests = client.get('/api/retests?revocation_id=' + ident).get_json()
    assert len(retests) == 2 and all(r['destination'] == '待重测' for r in retests)
    target = retests[0]['id']
    ok = client.post('/api/retests/' + target + '/disposition',
                     json={'destination': '已重测合格', 'note': '换用S2重测'})
    assert ok.status_code == 200
    updated = client.get('/api/retests?revocation_id=' + ident).get_json()
    row = next(r for r in updated if r['id'] == target)
    assert row['destination'] == '已重测合格' and row['note'] == '换用S2重测'
    assert client.post('/api/retests/' + target + '/disposition',
                       json={'destination': '报废'}).status_code == 422
    assert client.post('/api/retests/unknown/disposition',
                       json={'destination': '停用'}).status_code == 404


def test_validation_errors(client, base_run):
    rid = base_run['manifest']['run_id']
    assert _rev(client, rid, standard='GHOST').status_code == 422
    assert _rev(client, rid, date='2026-13-99').status_code == 422
    for bad in ([], 'text', 7, None):
        resp = client.post('/api/revocations', json=bad) if bad is not None \
            else client.post('/api/revocations', data='null', content_type='application/json')
        assert resp.status_code == 400
    assert client.get('/api/revocations/missing').status_code == 404


def test_pages_and_evidence_exports(client, base_run):
    rid = base_run['manifest']['run_id']
    ident = _rev(client, rid).get_json()['id']
    for url in ('/work/7?run_id=' + rid, '/revocations?run_id=' + rid,
                '/revocations/' + ident):
        page = client.get(url)
        assert page.status_code == 200
    bundle = client.get('/api/revocations/' + ident + '/evidence')
    assert bundle.status_code == 200 and bundle.get_json()['revocation']['id'] == ident
    csv_resp = client.get('/api/revocations/' + ident + '/evidence.csv')
    assert csv_resp.status_code == 200 and 'text/csv' in csv_resp.content_type
    text = csv_resp.data.decode('utf-8-sig')
    for heading in ('视角一：原路径与原结论（不可变）', '视角二：当前影响（生效日重算）',
                    '视角三：去向（重测处置）', '续跑日志'):
        assert heading in text
    assert 'BACKFILL_REVOKED' in text and ident in text


def test_derived_batch_still_supports_native_review_and_evidence(client, base_run):
    rid = base_run['manifest']['run_id']
    derived_id = _rev(client, rid).get_json()['derived_run_id']
    # The derived run is a normal batch: pages, review lock and evidence CSV work.
    assert client.get('/work/6?run_id=' + derived_id).status_code == 200
    review = client.post('/api/review',
                         json={'id': derived_id, 'revision': 1, 'decision': '退回'})
    assert review.status_code == 200 and review.get_json()['revision'] == 2
    stale = client.post('/api/review',
                        json={'id': derived_id, 'revision': 1, 'decision': '退回'})
    assert stale.status_code == 409
    evidence = client.get('/api/evidence.csv?run_id=' + derived_id).data.decode('utf-8-sig')
    assert 'BACKFILL_REVOKED' in evidence


def test_second_backfill_chains_off_lineage_root(client, base_run):
    rid = base_run['manifest']['run_id']
    first = _rev(client, rid, standard='S1', date='2026-06-01').get_json()
    # A later backfill on another standard derives from the lineage root,
    # not from the already-derived version (retry reuses the original version).
    second = _rev(client, rid, standard='ROOT', date='2027-01-01').get_json()
    assert second['id'] != first['id'] and second['status'] == 'applied'
    derived2 = client.get('/api/runs/' + second['derived_run_id']).get_json()
    assert derived2['manifest']['derived_from'] == rid
    assert derived2['manifest']['lineage_root'] == rid
    versions = client.get('/api/batches/' + rid + '/current').get_json()['versions']
    assert [v['seq'] for v in versions] == [2, 3]
    assert all(v['parent_id'] == rid for v in versions)


def test_evidence_hash_is_recomputable_and_detects_tampering(client, base_run):
    rid = base_run['manifest']['run_id']
    derived_id = _rev(client, rid).get_json()['derived_run_id']
    stored = client.get('/api/runs/' + derived_id).get_json()
    assert evidence_hash(stored) == stored['manifest']['sha256']
    tampered = copy.deepcopy(stored)
    target = next(v for v in tampered['verdicts'] if v['结论'] == '拒用')
    target['结论'] = '可采用'
    assert evidence_hash(tampered) != stored['manifest']['sha256']


def test_backfill_anchored_on_derived_batch_resolves_to_lineage_root(client, base_run):
    rid = base_run['manifest']['run_id']
    derived_id = _rev(client, rid, standard='S1', date='2026-06-01').get_json()['derived_run_id']
    # POSTing the derived batch id must anchor on the lineage root, not fork.
    rec = _rev(client, derived_id, standard='ROOT', date='2027-01-01').get_json()
    assert rec['root_id'] == rid and rec['base_run_id'] == rid
    second = client.get('/api/runs/' + rec['derived_run_id']).get_json()
    assert second['manifest']['derived_from'] == rid
    # Repeating from either id hits the same natural key.
    again = _rev(client, derived_id, standard='ROOT', date='2027-01-01').get_json()
    assert again['reused'] is True and again['id'] == rec['id']


def test_no_external_urls_in_backfill_assets():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ('app/static/backfill.js', 'app/static/backfill.css',
                 'app/templates/bf_list.html', 'app/templates/bf_detail.html',
                 'app/templates/m7.html'):
        text = (root / name).read_text(encoding='utf-8')
        for marker in ('http://', 'https://', '//cdn', '@import url'):
            assert marker not in text, (name, marker)
