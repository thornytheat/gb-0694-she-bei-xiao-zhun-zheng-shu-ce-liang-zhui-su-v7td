from flask import Blueprint, render_template, request

from app.backfill import service, store
from app.config import MODULES, TITLE
from app.store import get_run

bp = Blueprint('backfill_web', __name__)


@bp.route('/revocations')
def revocations_page():
    root_id = request.args.get('run_id')
    recs = store.list_revocations(root_id)
    roots = sorted({r['root_id'] for r in recs})
    return render_template('bf_list.html', title=TITLE, modules=MODULES, stage=7,
                           recs=recs, roots=roots, selected_root=root_id)


@bp.route('/revocations/<ident>')
def revocation_page(ident):
    rec = store.get_revocation(ident)
    bundle = service.evidence_bundle(ident)
    retests = store.list_retests(revocation_id=ident)
    base = get_run(rec['root_id'])
    derived = get_run(rec['derived_run_id']) if rec['derived_run_id'] else None
    current_id = store.current_id(rec['root_id'])
    return render_template(
        'bf_detail.html', title=TITLE, modules=MODULES, stage=7, rec=rec,
        bundle=bundle, retests=retests, base=base, derived=derived,
        current_id=current_id, destinations=store.DESTINATIONS)
