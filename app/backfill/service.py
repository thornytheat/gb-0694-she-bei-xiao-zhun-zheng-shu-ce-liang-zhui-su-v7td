"""Orchestration: create back-dated revocations, process them with a
resumable journal, and switch the current batch version atomically."""
import hashlib
import json

from app.backfill import store
from app.backfill.engine import build_derived, derived_run_id, evidence_hash
from app.store import get_run


def revocation_id(root_id, standard_id, effective_date):
    return hashlib.sha256(
        ('bf:' + root_id + ':' + standard_id + ':' + effective_date).encode('utf-8')
    ).hexdigest()[:16]


def create(root_id, standard_id, effective_date, reason='', fault_plan=None,
           clear_fault=False):
    # Any batch id (original or already-derived) resolves to its lineage root;
    # every derivation is built from the root so retries reuse one version.
    anchor = get_run(root_id)
    root_id = anchor['manifest'].get('lineage_root', anchor['manifest']['run_id'])
    from app.domain import day
    day(effective_date)
    ident = revocation_id(root_id, standard_id, effective_date)
    existing = store.find_revocation(root_id, standard_id, effective_date)
    if existing:
        # Retries reuse the original record/version. A retry without a new
        # fault plan clears any prior simulated-fault plan so processing can
        # actually resume.
        if clear_fault:
            store.set_fault_plan(ident, fault_plan)
            existing = store.get_revocation(ident)
        return existing, True
    store.insert_revocation({
        'id': ident,
        'root_id': root_id,
        'base_run_id': root_id,
        'standard_id': standard_id,
        'effective_date': effective_date,
        'reason': reason,
        'status': 'pending',
        'fault_plan': fault_plan,
    })
    return store.get_revocation(ident), False


def _fault(plan, stage, processed_count):
    """Fail when the configured threshold is reached on the given stage."""
    if not plan:
        return None
    target_stage = plan.get('stage', 'derive')
    fail_after = int(plan.get('fail_after_items', 0))
    if stage == target_stage and processed_count >= fail_after:
        return plan.get('message', '模拟写入中断（fault_plan）')
    return None


def process(ident, fault_plan=None, clear_fault=False):
    rec = store.get_revocation(ident)
    if rec['status'] == 'applied':
        return rec
    if clear_fault:
        store.set_fault_plan(ident, fault_plan)
        rec = store.get_revocation(ident)

    base = get_run(rec['root_id'])
    payload, affected, retests = build_derived(
        base, rec['id'], rec['standard_id'], rec['effective_date'], rec.get('reason') or '')

    done = store.journal_done(ident)
    plan = rec.get('fault_plan')
    interrupted = False

    # Stage 1: per-certificate checkpoints. Each is an independent transaction
    # so a crash leaves explicit progress that a retry skips.
    processed = sum(1 for k in affected if ('derive', k) in done)
    for cert_id in affected:
        if ('derive', cert_id) in done:
            continue
        message = _fault(plan, 'derive', processed)
        if message:
            store.update_status(ident, 'interrupted', error=message)
            store.mark_journal(ident, 'derive', cert_id, 'blocked', message)
            interrupted = True
            break
        store.mark_journal(ident, 'derive', cert_id, 'done',
                           '生效日起受影响，拒用并重测')
        processed += 1

    # Stage 2: atomic switch. Failure here rolls back, leaving the current
    # pointer (and therefore the original review evidence) untouched.
    if not interrupted and ('switch', '__batch__') not in done:
        message = _fault(plan, 'switch', 0)
        if message:
            store.update_status(ident, 'interrupted', error=message)
            store.mark_journal(ident, 'switch', '__batch__', 'blocked', message)
            interrupted = True
        else:
            seq = store.next_seq(rec['root_id'])
            version_id = derived_run_id(rec['id'])
            # switch_version writes the switch checkpoint inside the same
            # transaction; a prior blocked row is retained as evidence.
            store.switch_version(rec, payload, retests, version_id, rec['root_id'], seq)
    return store.get_revocation(ident)


def create_and_process(root_id, standard_id, effective_date, reason='', fault_plan=None,
                       clear_fault=False):
    rec, reused = create(root_id, standard_id, effective_date, reason, fault_plan, clear_fault)
    return process(rec['id'], fault_plan if not clear_fault else None, clear_fault), reused


def evidence_bundle(ident):
    rec = store.get_revocation(ident)
    base = get_run(rec['root_id'])
    current_id = store.current_id(rec['root_id'])
    versions = store.versions(rec['root_id'])
    journal = store.journal_all(ident)
    retests = store.list_retests(revocation_id=ident)
    bundle = {
        'revocation': {k: rec[k] for k in
                       ('id', 'root_id', 'base_run_id', 'derived_run_id', 'standard_id',
                        'effective_date', 'reason', 'status', 'error', 'created_at', 'updated_at')},
        'original': {
            'run_id': base['manifest']['run_id'],
            'decision': base.get('decision', '待复核'),
            'revision': base.get('revision', 1),
            'evidence_sha256': base['manifest'].get('sha256', ''),
            'chains': {k: {'path': v['path'], 'code': v['code'], 'valid': v['valid']}
                       for k, v in base.get('chains', {}).items()},
            'verdicts': base.get('verdicts', []),
        },
        'current': {'run_id': current_id, 'versions': versions},
        'destinations': retests,
        'journal': journal,
    }
    if rec['derived_run_id']:
        derived = get_run(rec['derived_run_id'])
        bundle['derived'] = {
            'run_id': derived['manifest']['run_id'],
            'evidence_sha256': derived['manifest'].get('sha256', ''),
            'chains': {k: {'path': v['path'], 'code': v['code'], 'valid': v['valid'],
                           'backfill': v.get('backfill', False)}
                       for k, v in derived.get('chains', {}).items()},
            'verdicts': derived.get('verdicts', []),
        }
        bundle['evidence_sha256'] = evidence_hash(derived)
    body = {k: v for k, v in bundle.items() if k != 'evidence_sha256'}
    bundle['bundle_sha256'] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode('utf-8')
    ).hexdigest()
    return bundle
