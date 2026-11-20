"""Run inside app after seed.py work. Does not alter application behavior."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import DB
with DB() as db:
    counts={t:db.query('SELECT count(*) AS n FROM '+t)[0]['n'] for t in ('readers','books','copies','loans')}
    if counts != {'readers':3000,'books':10000,'copies':30000,'loans':50000}:
        raise SystemExit('First run seed.py work; unexpected starting counts: '+str(counts))
    # A real reader cohort without overdue books. Existing seeded readers are all overdue in November.
    db.query("INSERT INTO readers(id,name) SELECT i,'Нагрузочный читатель '||i FROM generate_series(3001::integer,3200::integer) i")
    copies=[r['id'] for r in db.query('''SELECT c.id FROM copies c WHERE NOT EXISTS
        (SELECT 1 FROM loans l WHERE l.copy_id=c.id AND l.returned_on IS NULL) ORDER BY c.id''')]
    returns=[r['id'] for r in db.query('SELECT id FROM loans WHERE returned_on IS NULL ORDER BY id')]
    today=str(db.query('SELECT CURRENT_DATE AS day')[0]['day'])
    data={'prefix':os.environ['PERSONAL_PREFIX'],'date':today,'reader_ids':list(range(3001,3201)),
          'copy_ids':copies,'return_ids':returns,'loan_count':50000,
          'counts':dict(counts,readers=3200)}
Path('results/hw2').mkdir(parents=True,exist_ok=True)
Path('results/hw2/fixtures.json').write_text(json.dumps(data,ensure_ascii=False))
print(json.dumps({'prefix':data['prefix'],'date':today,'counts':data['counts'],
                  'free_copies':len(copies),'active_loans':len(returns)},ensure_ascii=False))
