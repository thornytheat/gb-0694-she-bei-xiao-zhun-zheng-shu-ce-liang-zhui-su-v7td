"""Back-dated revocation derivation engine.

Pure function over an existing, immutable run payload:
- rebuilds trace chains and M6 verdicts against a standard revoked on an
  effective date;
- measurements before the effective date keep their original verdict;
- measurements on/after the date, whose certificate is structurally
  downstream of the revoked standard, become 拒用(BACKFILL_REVOKED) and
  produce retest (去向) items;
- stages 1-4, quarantine and the original payload are never mutated.
"""
import copy
import hashlib
import json
import time

from app.domain import day, descendants
from app.errors import DomainError
from app.numeric import serial


def structural_path(cert, certs):
    path, seen, current = [], set(), cert
    while current:
        if current in seen:
            return path + [current], 'CYCLE'
        if current not in certs:
            return path + [current], 'MISSING_REFERENCE'
        seen.add(current)
        path.append(current)
        current = certs[current].get('parent') or None
    return path, 'TRACEABLE'


def derived_run_id(revocation_id):
    return hashlib.sha256(('bf-derived:' + revocation_id).encode('utf-8')).hexdigest()[:16]


def evidence_hash(payload):
    # manifest is the hash carrier; decision/revision are store-layer fields
    # merged on read and are not part of the immutable derived payload.
    excluded = {'manifest', 'decision', 'revision', 'reused'}
    body = {k: v for k, v in payload.items() if k not in excluded}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def build_derived(base, revocation_id, standard_id, effective_date, reason=''):
    day(effective_date)  # validate ISO date, raises DomainError on bad input
    certs = base.get('certs') or {}
    if standard_id not in certs:
        raise DomainError('STANDARD', '撤销标准器不在该批次证书内')

    affected = set(descendants(standard_id, certs))
    payload = copy.deepcopy(base)

    # ---- M5: rebuild every chain, flagging backfill-revoked branches ----
    old_chains = payload.get('chains', {})
    new_chains, chain_rows = {}, []
    for key in sorted(certs):
        path, structural_code = structural_path(key, certs)
        conflicted = any(certs.get(node, {}).get('conflicted') for node in path)
        if key in affected:
            chain = {
                'valid': False,
                'code': 'REFERENCE_CONFLICT' if conflicted else 'BACKFILL_REVOKED',
                'path': path,
                'backfill': True,
                'revoked_standard': standard_id,
                'effective_date': effective_date,
            }
        else:
            chain = copy.deepcopy(old_chains.get(key, {'valid': False,
                                                       'code': structural_code, 'path': path}))
        new_chains[key] = chain
        chain_rows.append({
            '证书': key,
            '溯源路径': ' → '.join(path),
            '原因码': chain['code'],
            '状态': '可追溯' if chain['valid'] else '中断',
            '撤销补录': '生效日起失效' if chain.get('backfill') else '',
        })
    payload['chains'] = new_chains
    payload['stages']['5']['rows'] = chain_rows

    # ---- M6: date-aware verdicts, original conclusions retained pre-date ----
    original = {row['行号']: row for row in payload['stages']['6']['rows']}
    verdict_rows, retests = [], []
    accepted = rejected = 0
    for r in payload['measurements']:
        orig = original.get(r['行号'], {})
        old_reasons = [x for x in str(orig.get('原因码', '')).split(',') if x and x != 'ACCEPT']
        post = r['measured_at'] >= effective_date
        is_affected = r['cert'] in affected
        path, _ = structural_path(r['cert'], certs)
        reasons = list(old_reasons)
        if is_affected and post and 'BACKFILL_REVOKED' not in reasons:
            reasons.append('BACKFILL_REVOKED')
        if is_affected and not post:
            # Effective date not reached: the original judgement stands untouched.
            reasons = old_reasons
        verdict = '拒用' if reasons else '可采用'
        accepted += verdict == '可采用'
        rejected += verdict == '拒用'
        row = {
            '证书': r['cert'],
            '设备': r['canonical'],
            '测量值_V': r['value_v'],
            '测量日': r['measured_at'],
            '结论': verdict,
            '原因码': ','.join(reasons) or 'ACCEPT',
            '行号': r['行号'],
            '原结论': orig.get('结论', verdict),
            '原原因码': orig.get('原因码', ','.join(reasons) or 'ACCEPT'),
            '生效日判断': ('生效日前维持原判断' if not post else
                         '生效日起重算' if is_affected else '生效日起重算（不受影响）'),
            '原溯源路径': ' → '.join(path),
        }
        verdict_rows.append(row)
        if is_affected and post:
            retests.append({
                'id': hashlib.sha256(
                    ('bf-retest:' + revocation_id + ':' + r['cert'] + ':' + str(r['行号']))
                    .encode('utf-8')).hexdigest()[:16],
                'cert_id': r['cert'],
                'device': r['canonical'],
                'measured_at': r['measured_at'],
                'source_line': r['行号'],
                'original_verdict': orig.get('结论', ''),
                'current_verdict': verdict,
                'trace_path': ' → '.join(path),
                'destination': '待重测',
                'note': '',
            })
    payload['verdicts'] = verdict_rows
    payload['stages']['6']['rows'] = verdict_rows
    payload['stages']['6']['metrics'] = [
        ['可采用', accepted, '条'], ['拒用', rejected, '条'],
        ['行数守恒', '相符' if payload.get('balanced', True) else '差异', ''],
    ]

    # ---- M7: keep file-flagged rows, add the back-dated revocation row ----
    stage7_rows = list(payload['stages']['7'].get('rows', []))
    for row in stage7_rows:
        row.setdefault('类型', '文件标记')
        row.setdefault('生效日', '')
    stage7_rows.append({
        '撤销源': standard_id,
        '影响证书': ','.join(sorted(affected)),
        '证书数': len(affected),
        '拒用测量': len(retests),
        '复核': '生效日起拒用并安排重测',
        '类型': '补录',
        '生效日': effective_date,
    })
    payload['stages']['7']['rows'] = stage7_rows
    payload['stages']['7']['metrics'] = [
        ['撤销源', len(stage7_rows), '份'],
        ['影响证书', len(affected), '份'],
        ['重测测量', len(retests), '条'],
    ]

    # ---- mark certs (data only; original revoked flag is never overwritten) ----
    for key in affected:
        if key in payload['certs']:
            payload['certs'][key]['backfill_revoked'] = standard_id
            payload['certs'][key]['backfill_effective_date'] = effective_date

    # ---- manifest: new content-addressed id, evidence hash for verification ----
    base_manifest = base['manifest']
    lineage_root = base_manifest.get('lineage_root', base_manifest['run_id'])
    payload['manifest'] = {
        'run_id': derived_run_id(revocation_id),
        'sha256': '',  # filled after hash
        'rule_version': base_manifest['rule_version'],
        'parameters': dict(base_manifest.get('parameters', {})),
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'derived_from': base_manifest['run_id'],
        'lineage_root': lineage_root,
        'backfill': {
            'revocation_id': revocation_id,
            'revoked_standard': standard_id,
            'effective_date': effective_date,
            'reason': reason,
            'affected_certs': sorted(affected),
            'retest_count': len(retests),
        },
    }
    payload['manifest']['sha256'] = evidence_hash(payload)
    return serial(payload), sorted(affected), retests
