#!/usr/bin/env python3
"""Apply an exact-target offline history repair with a recoverable manifest."""
import argparse, datetime, hashlib, json, os, shutil, sqlite3, subprocess, tempfile
from pathlib import Path

TABLES = ('thread_turns', 'thread_items', 'thread_history_projection_state', 'thread_realtime_items')
MANIFEST_VERSION = 2

def digest(path):
    with open(path, 'rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def connect_ro(path): return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)

def inside(path, parent):
    path, parent = Path(path).resolve(), Path(parent).resolve()
    return path == parent or parent in path.parents

def require_offline(paths=()):
    ps = subprocess.check_output(['ps', '-axo', 'comm='], text=True).splitlines()
    active = [p.strip() for p in ps if Path(p.strip()).name.lower() in {'codex','chatgpt','codex app-server'} or ('/Contents/MacOS/' in p and ('ChatGPT.app/' in p or 'Codex.app/' in p))]
    if active: raise RuntimeError('Fully quit Codex/ChatGPT and Codex CLI processes before applying: ' + ', '.join(sorted(set(active))))
    paths = [str(Path(p).resolve()) for p in paths if Path(p).exists()]
    if paths:
        result = subprocess.run(['lsof', '-Fn', '--', *paths], text=True, capture_output=True)
        if result.returncode not in (0, 1): raise RuntimeError('lsof failed while checking live files')
        if result.returncode == 0 and result.stdout.strip(): raise RuntimeError('Live repair files have open handles')

def columns(db, table): return [r[1] for r in db.execute(f'PRAGMA table_info({table})')]

def require_schema(db, label):
    for table in TABLES:
        if 'thread_id' not in columns(db, table): raise RuntimeError(f'Schema changed for {label}.{table}')

def fingerprint(db, table, ids, exclude=False):
    marks = ','.join('?' for _ in ids)
    info = db.execute(f'PRAGMA table_info({table})').fetchall()
    pk = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r:r[5])]
    order = pk or [r[1] for r in info]
    quoted = ','.join('"'+c.replace('"','""')+'"' for c in order)
    cursor = db.execute(f"SELECT * FROM {table} WHERE thread_id {'NOT IN' if exclude else 'IN'} ({marks}) ORDER BY {quoted}", ids)
    hasher=hashlib.sha256(); count=0
    for row in cursor:
        hasher.update(json.dumps(list(row),separators=(',',':'),default=str).encode()+b'\n'); count+=1
    return {'rows':count,'sha256':hasher.hexdigest()}

def fingerprints(db, ids, exclude=False): return {t: fingerprint(db, t, ids, exclude) for t in TABLES}

def replace_rows(dst, src, ids):
    for table in TABLES:
        cols = columns(dst, table)
        if not cols or cols != columns(src, table): raise RuntimeError('Schema changed for ' + table)
        marks = ','.join('?' for _ in cols)
        for tid in ids:
            dst.execute(f'DELETE FROM {table} WHERE thread_id=?', (tid,))
            dst.executemany(f'INSERT INTO {table} VALUES ({marks})', src.execute(f'SELECT * FROM {table} WHERE thread_id=?', (tid,)).fetchall())

def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def atomic_copy(src, dst, mode=None):
    dst = Path(dst); fd, temp = tempfile.mkstemp(prefix='.history-repair-', dir=dst.parent)
    try:
        with open(src, 'rb') as inp, os.fdopen(fd, 'wb') as out:
            shutil.copyfileobj(inp, out); out.flush(); os.fsync(out.fileno())
        os.chmod(temp, mode if mode is not None else Path(src).stat().st_mode & 0o777)
        os.replace(temp, dst); fsync_dir(dst.parent)
    finally:
        if Path(temp).exists(): Path(temp).unlink()

def write_manifest(path, record, phase):
    record['phase'] = phase; data = (json.dumps(record, indent=2) + '\n').encode()
    fd, temp = tempfile.mkstemp(prefix='.manifest-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out: out.write(data); out.flush(); os.fsync(out.fileno())
        os.chmod(temp, 0o600); os.replace(temp, path); fsync_dir(path.parent)
    finally:
        if Path(temp).exists(): Path(temp).unlink()

def verify_payloads(original, repaired):
    with open(original, 'rb') as a, open(repaired, 'rb') as b:
        for index, (old, new) in enumerate(zip(a, b, strict=True)):
            old, new = json.loads(old), json.loads(new); old.pop('ordinal', None)
            if new.pop('ordinal', None) != index or old != new: raise RuntimeError('Repair changed payload/order or did not normalize ordinals')

def live_paths(home, targets):
    result=[]
    for name in ('state_5.sqlite','thread_history_1.sqlite'):
        p=home/name; result += [p, Path(str(p)+'-wal'), Path(str(p)+'-shm')]
    return result + [Path(t['original']) for t in targets]

def validate_plan(plan, backup_root):
    home, backup_root = Path(plan['codex_home']).resolve(), Path(backup_root).resolve()
    if inside(backup_root, home): raise RuntimeError('Backup must be outside live Codex home')
    targets=plan['targets']; ids=[t['id'] for t in targets]
    if not ids or len(ids)!=len(set(ids)): raise RuntimeError('An explicit, unique target set is required')
    prepared=Path(plan['prepared_projection']).resolve(); inputs=[prepared]+[Path(t['repaired']).resolve() for t in targets]
    if any(inside(p,home) for p in inputs): raise RuntimeError('Prepared inputs must be outside live Codex home')
    originals={Path(t['original']).resolve() for t in targets}
    if len(inputs)!=len(set(inputs)) or set(inputs)&originals: raise RuntimeError('Prepared inputs and live targets must not overlap')
    if digest(prepared)!=plan['prepared_projection_sha256']: raise RuntimeError('Prepared projection changed')
    return home,backup_root,targets,ids,prepared

def apply(plan, backup_root):
    home,backup_root,targets,ids,prepared_path=validate_plan(plan,backup_root)
    require_offline(live_paths(home,targets)); state_path=home/'state_5.sqlite'; history_path=home/'thread_history_1.sqlite'
    backup=backup_root/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'); backup.mkdir(parents=True,mode=0o700); os.chmod(backup,0o700); fsync_dir(backup.parent)
    with sqlite3.connect(state_path) as state, connect_ro(prepared_path) as prepared, connect_ro(history_path) as history:
        state.execute('BEGIN IMMEDIATE'); require_schema(prepared,'prepared'); require_schema(history,'live')
        prepared_fp=fingerprints(prepared,ids); original_fp=fingerprints(history,ids); non_target_fp=fingerprints(history,ids,True)
        for target in targets:
            row=state.execute('SELECT archived,rollout_path,history_mode FROM threads WHERE id=?',(target['id'],)).fetchone()
            if row!=(0,target['original'],'paginated'): raise RuntimeError('Target state changed or archived: '+target['id'])
            original=Path(target['original']).resolve()
            if not inside(original,home): raise RuntimeError('Target rollout is outside Codex home')
            if digest(original)!=target['original_sha256'] or digest(target['repaired'])!=target['repaired_sha256']: raise RuntimeError('Rollout changed since validation: '+target['id'])
            verify_payloads(original,target['repaired'])
            actual={r[0] for r in prepared.execute('SELECT turn_id FROM thread_turns WHERE thread_id=?',(target['id'],))}
            if actual!=set(target['expected_turn_ids']): raise RuntimeError('Prepared turns do not match validation')
        for name in ('state_5.sqlite','thread_history_1.sqlite'):
            with connect_ro(home/name) as src, sqlite3.connect(backup/name) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchall()!=[('ok',)]: raise RuntimeError('Backup integrity check failed')
            os.chmod(backup/name,0o600)
        backed=[]
        for target in targets:
            dst=backup/(target['id']+'.jsonl'); atomic_copy(target['original'],dst,0o600)
            if digest(dst)!=target['original_sha256']: raise RuntimeError('Rollout backup differs from original: '+target['id'])
            backed.append({'id':target['id'],'path':str(dst),'sha256':target['original_sha256']})
        backups={n:{'path':str(backup/n),'sha256':digest(backup/n)} for n in ('state_5.sqlite','thread_history_1.sqlite')}
        for e in list(backups.values())+backed:
            if digest(e['path'])!=e['sha256']: raise RuntimeError('Backup hash verification failed')
        record={'manifest_version':MANIFEST_VERSION,'codex_home':str(home),'backup':str(backup),'targets':targets,'backups':backups,'backup_targets':backed,'prepared_projection_sha256':plan['prepared_projection_sha256'],'prepared_target_fingerprints':prepared_fp,'original_target_fingerprints':original_fp,'non_target_fingerprints':non_target_fp}
        manifest=backup/'rollback.json'; write_manifest(manifest,record,'backups_verified')
        if digest(prepared_path)!=plan['prepared_projection_sha256']: raise RuntimeError('Prepared projection changed before apply')
        for target in targets:
            if digest(target['original'])!=target['original_sha256'] or digest(target['repaired'])!=target['repaired_sha256']: raise RuntimeError('Repair input changed before apply: '+target['id'])
        with sqlite3.connect(history_path) as db:
            db.execute('BEGIN IMMEDIATE'); replace_rows(db,prepared,ids)
            if fingerprints(db,ids)!=prepared_fp or fingerprints(db,ids,True)!=non_target_fp: raise RuntimeError('Projection fingerprint verification failed')
            if db.execute('PRAGMA quick_check').fetchone()!=('ok',) or db.execute('PRAGMA foreign_key_check').fetchone() is not None: raise RuntimeError('Post-apply database integrity check failed')
            db.commit()
        write_manifest(manifest,record,'projection_applied')
        for target in targets:
            if digest(target['original'])!=target['original_sha256']: raise RuntimeError('Target changed after backup')
            atomic_copy(target['repaired'],target['original'])
        write_manifest(manifest,record,'applied_pending_app_verification'); state.commit()
    return record

def validate_manifest(path,record):
    path=Path(path).resolve(); backup=Path(record['backup']).resolve(); home=Path(record['codex_home']).resolve()
    if record.get('manifest_version')!=MANIFEST_VERSION: raise RuntimeError('Unsupported rollback manifest version')
    if path!=backup/'rollback.json': raise RuntimeError('Manifest location does not match backup directory')
    if inside(backup,home): raise RuntimeError('Backup is inside live Codex home')
    targets=record.get('targets',[]); ids=[t.get('id') for t in targets]
    if not ids or None in ids or len(ids)!=len(set(ids)): raise RuntimeError('Invalid target IDs in manifest')
    for target in targets:
        if not inside(target.get('original',''),home): raise RuntimeError('Manifest target is outside live Codex home')
    expected={e['id']:e for e in record.get('backup_targets',[])}
    if set(expected)!=set(ids): raise RuntimeError('Backup target set does not match manifest')
    db_backups=record.get('backups',{})
    if set(db_backups)!={'state_5.sqlite','thread_history_1.sqlite'}: raise RuntimeError('Manifest database backup set is incomplete')
    entries=list(db_backups.items())+[(e['id'],e) for e in expected.values()]
    for name,e in entries:
        wanted=backup/(name if name.endswith('.sqlite') else name+'.jsonl')
        if Path(e['path']).resolve()!=wanted or digest(e['path'])!=e['sha256']: raise RuntimeError('Backup hash or path verification failed: '+name)
    by_id={t['id']:t for t in targets}
    for tid,e in expected.items():
        if e['sha256']!=by_id[tid]['original_sha256']: raise RuntimeError('Rollout backup hash differs from original: '+tid)
    with connect_ro(backup/'state_5.sqlite') as state_backup, connect_ro(backup/'thread_history_1.sqlite') as history_backup:
        if state_backup.execute('PRAGMA quick_check').fetchone()!=('ok',) or history_backup.execute('PRAGMA quick_check').fetchone()!=('ok',): raise RuntimeError('Backup integrity check failed')
        require_schema(history_backup,'backup')
    return home,backup,targets,ids

def rollback(record,manifest_path=None):
    manifest_path=Path(manifest_path or Path(record['backup'])/'rollback.json'); home,backup,targets,ids=validate_manifest(manifest_path,record)
    require_offline(live_paths(home,targets))
    with sqlite3.connect(home/'state_5.sqlite') as state:
        state.execute('BEGIN IMMEDIATE')
        for target in targets:
            if digest(target['original']) not in {target['original_sha256'],target['repaired_sha256']}: raise RuntimeError('Refusing rollback after unknown rollout writes: '+target['id'])
            if state.execute('SELECT archived,rollout_path FROM threads WHERE id=?',(target['id'],)).fetchone()!=(0,target['original']): raise RuntimeError('Target state changed; review rollback manually')
        with sqlite3.connect(home/'thread_history_1.sqlite') as db, connect_ro(backup/'thread_history_1.sqlite') as src:
            db.execute('BEGIN IMMEDIATE'); replace_rows(db,src,ids)
            if fingerprints(db,ids)!=record['original_target_fingerprints'] or fingerprints(db,ids,True)!=record['non_target_fingerprints']: raise RuntimeError('Rollback projection fingerprint verification failed')
            if db.execute('PRAGMA quick_check').fetchone()!=('ok',) or db.execute('PRAGMA foreign_key_check').fetchone() is not None: raise RuntimeError('Post-rollback database integrity check failed')
            db.commit()
        write_manifest(manifest_path,record,'projection_rolled_back'); backed={e['id']:e for e in record['backup_targets']}
        for target in targets: atomic_copy(backed[target['id']]['path'],target['original'])
        for target in targets:
            if digest(target['original'])!=target['original_sha256']: raise RuntimeError('Rollback rollout verification failed: '+target['id'])
        write_manifest(manifest_path,record,'rolled_back'); state.commit()
    return {'status':'rolled_back','targets':ids}

def main():
    p=argparse.ArgumentParser(description=__doc__); g=p.add_mutually_exclusive_group(required=True); g.add_argument('--plan',type=Path); g.add_argument('--rollback',type=Path); p.add_argument('--apply',action='store_true'); p.add_argument('--backup-root',type=Path); a=p.parse_args()
    if not a.apply: p.error('No mutation without --apply; audit with audit_history.py first')
    if a.plan and not a.backup_root: p.error('--backup-root is required with --plan')
    try:
        path=a.plan or a.rollback; data=json.loads(path.read_text()); result=apply(data,a.backup_root) if a.plan else rollback(data,path); print(json.dumps(result,indent=2))
    except Exception as exc: p.exit(1,f'ERROR: {exc}\n')

if __name__=='__main__': main()
