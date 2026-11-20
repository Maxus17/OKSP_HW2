import unittest,json,tempfile
from pathlib import Path
from analyze import profile_rows
class ProfileTests(unittest.TestCase):
    def test_excludes_idle_main_and_counts_self(self):
        doc={'shared':{'frames':[{'name':'summary','file':'/app/app.py','line':67},
             {'name':'query','file':'/app/db.py','line':15},{'name':'poll','file':'driver.py'}, {'name':'serve_forever','file':'server.py'}]},
             'profiles':[{'type':'sampled','samples':[[3],[0,1,2],[0,1]],'weights':[7,2,1]}]}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'p.json';p.write_text(json.dumps(doc));result=profile_rows(p)
        self.assertEqual(result['all_thread_weight'],10)
        self.assertEqual(result['summary_thread_weight'],3)
        query=next(r for r in result['functions'] if r['function']=='query')
        self.assertEqual(query['inclusive_pct_of_summary'],100)
        self.assertAlmostEqual(query['self_pct_of_summary'],100/3)
    def test_no_summary_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'p.json';p.write_text(json.dumps({'shared':{'frames':[]},'profiles':[]}));r=profile_rows(p)
        self.assertEqual(r['summary_thread_weight'],0)
        self.assertEqual(r['functions'],[])
if __name__=='__main__':unittest.main()
