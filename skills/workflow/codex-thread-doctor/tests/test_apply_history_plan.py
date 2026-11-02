import importlib.util, json, pathlib, sqlite3, tempfile, unittest
from unittest.mock import patch

SCRIPT=pathlib.Path(__file__).parents[1]/'scripts/apply_history_plan.py'
spec=importlib.util.spec_from_file_location('repair',SCRIPT); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class RepairTest(unittest.TestCase):
    def fixture(self,root,count=1):
        home=root/'home'; home.mkdir(); prepared=root/'prepared.sqlite'; targets=[]
        with sqlite3.connect(home/'state_5.sqlite') as d: d.execute('create table threads(id text,archived integer,rollout_path text,history_mode text)')
        for dest in (home/'thread_history_1.sqlite',prepared):
            with sqlite3.connect(dest) as d:
                for table in m.TABLES:
                    d.execute(f'create table {table}(thread_id text,turn_id text)'); d.execute(f'insert into {table} values(?,?)',('other','keep'))
        for n in range(count):
            tid=f'target{n}'; original=home/f'{tid}.jsonl'; repaired=root/f'{tid}-fixed.jsonl'
            original.write_text('{"ordinal":0,"payload":"a"}\n{"ordinal":0,"payload":"b"}\n'); repaired.write_text('{"ordinal":0,"payload":"a"}\n{"ordinal":1,"payload":"b"}\n')
            with sqlite3.connect(home/'state_5.sqlite') as d: d.execute('insert into threads values(?,?,?,?)',(tid,0,str(original),'paginated'))
            with sqlite3.connect(home/'thread_history_1.sqlite') as d:
                for table in m.TABLES: d.execute(f'insert into {table} values(?,?)',(tid,'old'))
            with sqlite3.connect(prepared) as d:
                for table in m.TABLES: d.execute(f'insert into {table} values(?,?)',(tid,'new'))
            targets.append({'id':tid,'original':str(original),'original_sha256':m.digest(original),'repaired':str(repaired),'repaired_sha256':m.digest(repaired),'expected_turn_ids':['new']})
        return {'codex_home':str(home),'prepared_projection':str(prepared),'prepared_projection_sha256':m.digest(prepared),'targets':targets}

    def test_apply_rollback_and_partial_original_repaired(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'require_offline'):
            root=pathlib.Path(tmp); plan=self.fixture(root,2); record=m.apply(plan,root/'backups'); manifest=pathlib.Path(record['backup'])/'rollback.json'
            # Simulate a partial retry: one rollout already original, one still repaired.
            m.atomic_copy(record['backup_targets'][0]['path'],plan['targets'][0]['original'])
            m.rollback(json.loads(manifest.read_text()),manifest); m.rollback(json.loads(manifest.read_text()),manifest)
            for target in plan['targets']: self.assertEqual(m.digest(target['original']),target['original_sha256'])
            with sqlite3.connect(root/'home/thread_history_1.sqlite') as d:
                self.assertEqual(d.execute("select turn_id from thread_turns where thread_id='other'").fetchone(),('keep',))

    def test_archived_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'require_offline'):
            root=pathlib.Path(tmp); plan=self.fixture(root)
            with sqlite3.connect(root/'home/state_5.sqlite') as d: d.execute('update threads set archived=1')
            with self.assertRaisesRegex(RuntimeError,'archived'): m.apply(plan,root/'backups')

    def test_prepared_inside_live_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); plan=self.fixture(root); live=root/'home/prepared.sqlite'; live.write_bytes(pathlib.Path(plan['prepared_projection']).read_bytes()); plan['prepared_projection']=str(live); plan['prepared_projection_sha256']=m.digest(live)
            with self.assertRaisesRegex(RuntimeError,'outside live'): m.apply(plan,root/'backups')

    def test_open_handle_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m.subprocess,'check_output',return_value=''),patch.object(m.subprocess,'run',return_value=type('R',(),{'returncode':0,'stdout':'p123\n'})()):
            opened=pathlib.Path(tmp)/'file'; opened.touch()
            with self.assertRaisesRegex(RuntimeError,'open handles'): m.require_offline([opened])

    def test_bad_backup_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'require_offline'):
            root=pathlib.Path(tmp); plan=self.fixture(root); record=m.apply(plan,root/'backups'); manifest=pathlib.Path(record['backup'])/'rollback.json'; pathlib.Path(record['backup_targets'][0]['path']).write_text('bad')
            with self.assertRaisesRegex(RuntimeError,'Backup hash'): m.rollback(json.loads(manifest.read_text()),manifest)

if __name__=='__main__': unittest.main()
