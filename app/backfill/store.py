import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from app.errors import DomainError

SCHEMA = """
CREATE TABLE IF NOT EXISTS bf_batch_versions(
  id TEXT PRIMARY KEY,
  root_id TEXT NOT NULL,
  parent_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(root_id, seq)
);
CREATE TABLE IF NOT EXISTS bf_batch_current(
  root_id TEXT PRIMARY KEY,
  current_id TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bf_revocations(
  id TEXT PRIMARY KEY,
  root_id TEXT NOT NULL,
  base_run_id TEXT NOT NULL,
  derived_run_id TEXT,
  standard_id TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  reason TEXT,
  status TEXT NOT NULL,
  fault_plan TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(root_id, standard_id, effective_date)
);
CREATE TABLE IF NOT EXISTS bf_journal(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  revocation_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  item_key TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bf_journal_lookup
  ON bf_journal(revocation_id, stage, item_key);
CREATE TABLE IF NOT EXISTS bf_retests(
  id TEXT PRIMARY KEY,
  revocation_id TEXT NOT NULL,
  root_id TEXT NOT NULL,
  cert_id TEXT NOT NULL,
  device TEXT NOT NULL,
  measured_at TEXT NOT NULL,
  source_line INTEGER,
  original_verdict TEXT NOT NULL,
  current_verdict TEXT NOT NULL,
  trace_path TEXT NOT NULL,
  destination TEXT NOT NULL,
  note TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bf_audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  revocation_id TEXT,
  event TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
"""


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _connect():
    path = Path(os.environ.get('APP_DB', 'data/runs.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


@contextmanager
def reading():
    db = _connect()
    try:
        db.executescript(SCHEMA)
        yield db
    finally:
        db.close()


@contextmanager
def writing():
    """One explicit transaction per write block: commit on success,
    rollback on error, connection always closed."""
    db = _connect()
    try:
        db.executescript(SCHEMA)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def audit(db, revocation_id, event, detail=''):
    db.execute('INSERT INTO bf_audit(revocation_id,event,detail,created_at) VALUES(?,?,?,?)',
               (revocation_id, event, detail, now()))


def insert_revocation(rec):
    with writing() as db:
        db.execute(
            'INSERT INTO bf_revocations(id,root_id,base_run_id,standard_id,effective_date,reason,'
            'status,fault_plan,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (rec['id'], rec['root_id'], rec['base_run_id'], rec['standard_id'],
             rec['effective_date'], rec.get('reason', ''), rec['status'],
             json.dumps(rec.get('fault_plan'), ensure_ascii=False) if rec.get('fault_plan') else None,
             now(), now()))
        audit(db, rec['id'], 'created',
              f"standard={rec['standard_id']} effective={rec['effective_date']}")


def get_revocation(ident):
    with reading() as db:
        row = db.execute('SELECT * FROM bf_revocations WHERE id=?', (ident,)).fetchone()
    if row is None:
        raise DomainError('NOT_FOUND', '撤销补录记录不存在', 404)
    return _revocation_dict(row)


def find_revocation(root_id, standard_id, effective_date):
    with reading() as db:
        row = db.execute(
            'SELECT * FROM bf_revocations WHERE root_id=? AND standard_id=? AND effective_date=?',
            (root_id, standard_id, effective_date)).fetchone()
    return _revocation_dict(row) if row else None


def list_revocations(root_id=None):
    with reading() as db:
        if root_id:
            rows = db.execute('SELECT * FROM bf_revocations WHERE root_id=? ORDER BY rowid',
                              (root_id,)).fetchall()
        else:
            rows = db.execute('SELECT * FROM bf_revocations ORDER BY rowid').fetchall()
    return [_revocation_dict(r) for r in rows]


def update_status(ident, status, error=None, derived_run_id=None, fault_plan=None):
    with writing() as db:
        if derived_run_id is not None:
            db.execute('UPDATE bf_revocations SET status=?,error=?,derived_run_id=?,updated_at=?'
                       ' WHERE id=?', (status, error, derived_run_id, now(), ident))
        elif fault_plan is not None:
            db.execute('UPDATE bf_revocations SET status=?,error=?,fault_plan=?,updated_at=?'
                       ' WHERE id=?',
                       (status, error,
                        json.dumps(fault_plan, ensure_ascii=False) if fault_plan else None,
                        now(), ident))
        else:
            db.execute('UPDATE bf_revocations SET status=?,error=?,updated_at=? WHERE id=?',
                       (status, error, now(), ident))
        audit(db, ident, 'status_' + status, error or '')


def set_fault_plan(ident, fault_plan):
    with writing() as db:
        db.execute('UPDATE bf_revocations SET fault_plan=?,updated_at=? WHERE id=?',
                   (json.dumps(fault_plan, ensure_ascii=False) if fault_plan else None,
                    now(), ident))
        audit(db, ident, 'fault_plan_updated', json.dumps(fault_plan, ensure_ascii=False))


def journal_done(ident):
    with reading() as db:
        rows = db.execute(
            "SELECT stage,item_key FROM bf_journal WHERE revocation_id=? AND status IN "
            "('done','resumed-done')", (ident,)).fetchall()
    return {(r['stage'], r['item_key']) for r in rows}


def journal_all(ident):
    with reading() as db:
        rows = db.execute(
            'SELECT stage,item_key,status,detail,created_at FROM bf_journal '
            'WHERE revocation_id=? ORDER BY rowid', (ident,)).fetchall()
    return [dict(r) for r in rows]


def mark_journal(ident, stage, item_key, status, detail=''):
    """Record a checkpoint. A prior row on the same item is never overwritten:
    a retry appends 'resumed-done' so blocked evidence stays visible."""
    with writing() as db:
        existing = db.execute(
            'SELECT 1 FROM bf_journal WHERE revocation_id=? AND stage=? AND item_key=?',
            (ident, stage, item_key)).fetchone()
        effective_status = 'resumed-done' if existing and status == 'done' else status
        db.execute(
            'INSERT INTO bf_journal(revocation_id,stage,item_key,status,detail,created_at)'
            ' VALUES(?,?,?,?,?,?)', (ident, stage, item_key, effective_status, detail, now()))


def next_seq(root_id):
    with reading() as db:
        row = db.execute('SELECT COALESCE(MAX(seq),1) AS s FROM bf_batch_versions WHERE root_id=?',
                         (root_id,)).fetchone()
    return row['s'] + 1


def versions(root_id):
    with reading() as db:
        rows = db.execute(
            'SELECT v.*, c.current_id IS NOT NULL AS is_current FROM bf_batch_versions v '
            'LEFT JOIN bf_batch_current c ON c.root_id=v.root_id AND c.current_id=v.id '
            'WHERE v.root_id=? ORDER BY v.seq', (root_id,)).fetchall()
    return [dict(r) for r in rows]


def current_id(root_id):
    with reading() as db:
        row = db.execute('SELECT current_id FROM bf_batch_current WHERE root_id=?',
                         (root_id,)).fetchone()
    return row['current_id'] if row else root_id


def switch_version(rec, derived_payload, retests, version_id, parent_id, seq):
    """Single transaction: version row + current pointer + revocation pointer
    + retests + switch checkpoint. Any failure rolls the whole switch back,
    leaving the current pointer on the original batch."""
    from app.store import save  # local import to avoid cycle at module load
    saved = save(derived_payload)  # content-addressed, idempotent, own transaction
    with writing() as db:
        db.execute('INSERT OR REPLACE INTO bf_batch_versions(id,root_id,parent_id,seq,created_at)'
                   ' VALUES(?,?,?,?,?)', (version_id, rec['root_id'], parent_id, seq, now()))
        db.execute('INSERT OR REPLACE INTO bf_batch_current(root_id,current_id,updated_at)'
                   ' VALUES(?,?,?)', (rec['root_id'], version_id, now()))
        for item in retests:
            db.execute(
                'INSERT OR IGNORE INTO bf_retests(id,revocation_id,root_id,cert_id,device,'
                'measured_at,source_line,original_verdict,current_verdict,trace_path,'
                'destination,note,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (item['id'], rec['id'], rec['root_id'], item['cert_id'], item['device'],
                 item['measured_at'], item['source_line'], item['original_verdict'],
                 item['current_verdict'], item['trace_path'], item['destination'],
                 item.get('note', ''), now()))
        db.execute('UPDATE bf_revocations SET derived_run_id=?,status=?,error=?,updated_at=?'
                   ' WHERE id=?', (version_id, 'applied', None, now(), rec['id']))
        prior = db.execute(
            'SELECT 1 FROM bf_journal WHERE revocation_id=? AND stage=? AND item_key=?',
            (rec['id'], 'switch', '__batch__')).fetchone()
        effective_status = 'resumed-done' if prior else 'done'
        db.execute('INSERT INTO bf_journal(revocation_id,stage,item_key,status,detail,created_at)'
                   ' VALUES(?,?,?,?,?,?)',
                   (rec['id'], 'switch', '__batch__', effective_status, version_id, now()))
        audit(db, rec['id'], 'applied', f'derived={version_id} seq={seq}')
    return saved


def list_retests(revocation_id=None, root_id=None):
    sql, args = 'SELECT * FROM bf_retests', []
    if revocation_id:
        sql += ' WHERE revocation_id=?'
        args.append(revocation_id)
    elif root_id:
        sql += ' WHERE root_id=?'
        args.append(root_id)
    sql += ' ORDER BY rowid'
    with reading() as db:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


DESTINATIONS = ('待重测', '重测中', '已重测合格', '已重测不合格', '停用')


def update_retest(ident, destination, note):
    if destination not in DESTINATIONS:
        raise DomainError('DESTINATION', '重测去向无效')
    with writing() as db:
        changed = db.execute(
            'UPDATE bf_retests SET destination=?,note=?,updated_at=? WHERE id=?',
            (destination, note, now(), ident)).rowcount
        if not changed:
            raise DomainError('NOT_FOUND', '重测任务不存在', 404)
        row = db.execute('SELECT revocation_id FROM bf_retests WHERE id=?', (ident,)).fetchone()
        audit(db, row['revocation_id'], 'retest_' + destination, ident)


def _revocation_dict(row):
    if row is None:
        return None
    out = dict(row)
    out['fault_plan'] = json.loads(row['fault_plan']) if row['fault_plan'] else None
    return out
