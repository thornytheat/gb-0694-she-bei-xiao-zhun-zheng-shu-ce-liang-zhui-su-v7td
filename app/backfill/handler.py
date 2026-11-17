import csv
import io

from flask import Blueprint, Response, jsonify, request

from app.backfill import service, store
from app.errors import DomainError

bp = Blueprint('backfill_api', __name__)


def _body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise DomainError('REQUEST', '请求内容必须为JSON对象', 400)
    return payload


def _require(body, name):
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DomainError('REQUEST', f'缺少必填字段 {name}')
    return value.strip()


@bp.route('/api/revocations', methods=['POST'])
def create_revocation():
    body = _body()
    root_id = _require(body, 'run_id')
    standard_id = _require(body, 'standard_id')
    effective_date = _require(body, 'effective_date')
    reason = body.get('reason') or ''
    fault_plan = body.get('fault_plan')
    if fault_plan is not None and not isinstance(fault_plan, dict):
        raise DomainError('REQUEST', 'fault_plan 必须为对象')
    # Presence of fault_plan in the request governs simulation; absent on a
    # retry means the prior fault plan is cleared and processing resumes.
    rec, reused = service.create_and_process(
        root_id, standard_id, effective_date, reason, fault_plan,
        clear_fault='fault_plan' not in body)
    return jsonify({**rec, 'reused': reused})


@bp.route('/api/revocations/<ident>', methods=['GET'])
def revocation_detail(ident):
    return jsonify(store.get_revocation(ident))


@bp.route('/api/revocations/<ident>/resume', methods=['POST'])
def resume_revocation(ident):
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise DomainError('REQUEST', '请求内容必须为JSON对象', 400)
    fault_plan = body.get('fault_plan')
    if fault_plan is not None and not isinstance(fault_plan, dict):
        raise DomainError('REQUEST', 'fault_plan 必须为对象')
    # A plain resume clears any prior simulated fault; passing fault_plan
    # explicitly keeps/re-arms simulation for demonstration.
    return jsonify(service.process(ident, fault_plan, clear_fault='fault_plan' not in body))


@bp.route('/api/revocations', methods=['GET'])
def list_revocations():
    root_id = request.args.get('run_id')
    return jsonify(store.list_revocations(root_id))


@bp.route('/api/batches/<root_id>/current')
def current_version(root_id):
    from app.store import get_run
    current = store.current_id(root_id)
    return jsonify({'root_id': root_id, 'current_id': current,
                    'versions': store.versions(root_id),
                    'run': get_run(current)})

@bp.route('/api/retests', methods=['GET'])
def retests():
    return jsonify(store.list_retests(
        revocation_id=request.args.get('revocation_id'),
        root_id=request.args.get('run_id')))


@bp.route('/api/retests/<ident>/disposition', methods=['POST'])
def retest_disposition(ident):
    body = _body()
    destination = _require(body, 'destination')
    note = body.get('note') or ''
    store.update_retest(ident, destination, note)
    return jsonify({'id': ident, 'destination': destination, 'note': note})


@bp.route('/api/revocations/<ident>/evidence')
def evidence_json(ident):
    return jsonify(service.evidence_bundle(ident))


@bp.route('/api/revocations/<ident>/evidence.csv')
def evidence_csv(ident):
    bundle = service.evidence_bundle(ident)
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['# 撤销补录证据包', bundle['revocation']['id']])
    writer.writerow(['# 证据包SHA256', bundle['bundle_sha256']])
    writer.writerow([])
    writer.writerow(['视角一：原路径与原结论（不可变）'])
    writer.writerow(['证书', '溯源路径', '原因码', '可追溯', '原结论', '原原因码', '行号'])
    original_verdicts = {v['行号']: v for v in bundle['original']['verdicts']}
    for cert, chain in bundle['original']['chains'].items():
        writer.writerow([cert, ' → '.join(chain['path']), chain['code'],
                         '是' if chain['valid'] else '否', '', '', ''])
    for v in bundle['original']['verdicts']:
        writer.writerow([v['证书'], '', '', '', v['结论'], v['原因码'], v['行号']])
    writer.writerow([])
    writer.writerow(['视角二：当前影响（生效日重算）'])
    writer.writerow(['证书', '溯源路径', '原因码', '可追溯', '补录失效'])
    for cert, chain in bundle.get('derived', {}).get('chains', {}).items():
        writer.writerow([cert, ' → '.join(chain['path']), chain['code'],
                         '是' if chain['valid'] else '否',
                         '是' if chain.get('backfill') else ''])
    writer.writerow([])
    writer.writerow(['视角三：去向（重测处置）'])
    writer.writerow(['任务', '证书', '设备', '测量日', '原结论', '当前结论', '去向', '更新时间'])
    for item in bundle['destinations']:
        writer.writerow([item['id'], item['cert_id'], item['device'], item['measured_at'],
                         item['original_verdict'], item['current_verdict'],
                         item['destination'], item['updated_at']])
    writer.writerow([])
    writer.writerow(['续跑日志'])
    writer.writerow(['阶段', '项目', '状态', '说明'])
    for entry in bundle['journal']:
        writer.writerow([entry['stage'], entry['item_key'], entry['status'],
                         entry.get('detail', '')])
    return Response('﻿' + out.getvalue(), mimetype='text/csv',
                    content_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename=revocation-{ident}-evidence.csv'})
