"""Collect read-only plans after (not during) the load tests."""
import sys,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import DB
queries={
 'summary_counts':"SELECT count(*) FILTER(WHERE returned_on IS NULL) AS on_hands,count(*) FILTER(WHERE returned_on IS NULL AND due_on<CURRENT_DATE) AS overdue FROM loans",
 'summary_top':"SELECT b.id,b.title,count(*) AS issued FROM loans l JOIN copies c ON c.id=l.copy_id JOIN books b ON b.id=c.book_id GROUP BY b.id,b.title ORDER BY issued DESC,b.id LIMIT 10",
 'filter_count':"SELECT count(*) FROM loans WHERE returned_on IS NULL AND due_on<CURRENT_DATE",
 'filter_page':"SELECT * FROM loans WHERE returned_on IS NULL AND due_on<CURRENT_DATE ORDER BY id DESC LIMIT 20 OFFSET 0",
 'issue_busy':"SELECT id FROM loans WHERE copy_id=1 AND returned_on IS NULL LIMIT 1",
 'issue_overdue':"SELECT id FROM loans WHERE reader_id=3001 AND returned_on IS NULL AND due_on<CURRENT_DATE LIMIT 1",
}
with DB() as db:
    plans={name:db.query('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q)[0]['QUERY PLAN'] for name,q in queries.items()}
    plans['indexes']=db.query('SELECT tablename,indexdef FROM pg_indexes WHERE schemaname=%s',(os.environ['PERSONAL_PREFIX'],))
Path('results/hw2/plans.json').write_text(json.dumps(plans,ensure_ascii=False,indent=2))
print('results/hw2/plans.json')
