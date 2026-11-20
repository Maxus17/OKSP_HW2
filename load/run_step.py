"""Usage: python3 load/run_step.py mixed|heavy RATE [--profile] [--seconds 30]."""
import argparse,subprocess,time,json,sys,hashlib,platform,os
from pathlib import Path
from datetime import datetime,timezone
from common import ROOT,DC,command,capture,stats,sql,prefix
p=argparse.ArgumentParser();p.add_argument('mode',choices=['mixed','heavy']);p.add_argument('rate',type=int)
p.add_argument('--seconds',type=int,default=30);p.add_argument('--profile',action='store_true')
p.add_argument('--profile-rate',type=int,default=10)
p.add_argument('--pre-vus',type=int,default=100);p.add_argument('--max-vus',type=int,default=400)
a=p.parse_args()
if a.rate<1 or a.seconds<1 or a.profile_rate<1:p.error('rate/seconds/profile-rate must be positive')
if a.profile and (a.mode!='heavy' or a.seconds<25):p.error('--profile needs heavy and at least 25 seconds')
label=f'{a.mode}-{a.rate}-'+datetime.now().strftime('%Y%m%d-%H%M%S')+('-profile' if a.profile else '')
directory=ROOT/'results'/'hw2'/label;directory.mkdir(parents=True)
print('Результаты:',directory,flush=True)
# Do not start/reset a new step until prior load drains and CPU has returned to idle.
ids=[capture(DC+['ps','-q',s]) for s in ('app','db')]
if not all(ids):raise SystemExit('First start app and db with compose.hw2.yaml')
quiet=0
for _ in range(30):
    activity=int(sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid() AND state='active'"))
    cpu=sum(float(s['CPUPerc'].rstrip('%')) for s in stats(ids))
    quiet=quiet+1 if cpu<25 and activity==0 else 0
    if quiet>=3:break
    print(f'Ожидаем простой: CPU app+db={cpu:.1f}%, active={activity}',flush=True);time.sleep(1)
else:raise SystemExit('No idle baseline within approximately 90 seconds; stop other workloads and retry')
for args,file in [(['exec','-T','app','python','seed.py','work'],'seed.txt'),
                  (['exec','-T','app','python','load/prepare.py'],'fixtures.txt')]:
    with (directory/file).open('w') as f:command(DC+args,stdout=f)
# Readiness check in the runner uses urllib in app; password is not written to logs or commands.
probe="import os,base64,urllib.request; h={'Authorization':'Basic '+base64.b64encode(('librarian:'+os.environ['API_PASSWORD']).encode()).decode()};r=urllib.request.urlopen(urllib.request.Request('http://localhost:8000/api/summary',headers=h));assert r.status==200;print('ready')"
command(DC+['exec','-T','app','python','-c',probe])
manifest={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
          for f in ROOT.rglob('*') if f.is_file() and ('load' in f.relative_to(ROOT).parts or f.name in ['app.py','db.py','rules.py','seed.py','compose.yaml','compose.hw2.yaml','Dockerfile.hw2','requirements.txt']) and '__pycache__' not in f.parts and 'results' not in f.relative_to(ROOT).parts and '.git' not in f.parts}
try:
    commit=capture(['git','rev-parse','HEAD']);dirty=capture(['git','status','--porcelain','--untracked-files=normal'])
except subprocess.CalledProcessError:commit='NOT_COMMITTED';dirty='No local git repository; commit exact code before final reported series'
metadata={'mode':a.mode,'rate':a.rate,'seconds':a.seconds,'profiled':a.profile,'prefix':prefix(),
          'idle_cpu_threshold_percent':25,'profiler_rate_hz':a.profile_rate,'utc':datetime.now(timezone.utc).isoformat(),'commit':commit,'git_status':dirty,
          'source_sha256':manifest,'platform':platform.platform(),
          'k6_version':capture(DC+['run','--rm','--no-deps','k6','version']),
          'python_version':capture(DC+['exec','-T','app','python','--version']),
          'profiler_version':capture(DC+['exec','-T','app','py-spy','--version'])}
(directory/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
monitor=subprocess.Popen([sys.executable,str(ROOT/'load'/'monitor.py'),str(directory/'resources.jsonl')],cwd=ROOT)
profiler=None;log=None;child=None
try:
    time.sleep(6)
    metadata['load_start_utc']=datetime.now(timezone.utc).isoformat()
    args=DC+['run','--rm','--no-deps','--user',f'{os.getuid()}:{os.getgid()}',
        '-e','MODE='+a.mode,'-e','RATE='+str(a.rate),'-e','SECONDS='+str(a.seconds),
        '-e','PRE_VUS='+str(a.pre_vus),'-e','MAX_VUS='+str(a.max_vus),
        '-e','OUT=/results/hw2/'+label+'/summary',
        'k6','run','--out','json=/results/hw2/'+label+'/metrics.jsonl','/scripts/test.js']
    log=(directory/'k6.log').open('w');child=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if a.profile:
        time.sleep(5)
        profiler=subprocess.Popen(DC+['exec','-T','app','py-spy','record','--pid','1','--duration','15',
            '--rate',str(a.profile_rate),'--threads','--idle','--format','speedscope',
            '-o','/app/results/hw2/'+label+'/profile.speedscope.json'],cwd=ROOT)
    rc=child.wait();metadata['load_end_utc']=datetime.now(timezone.utc).isoformat();metadata['k6_exit_code']=rc
    if profiler:
        prc=profiler.wait();metadata['profiler_exit_code']=prc
        if prc:print('Профиль не записан. Пришлите ошибку; нагрузочные данные сохранены.',flush=True)
    time.sleep(6)
finally:
    if child and child.poll() is None:child.terminate();child.wait()
    if profiler and profiler.poll() is None:profiler.terminate();profiler.wait()
    monitor.terminate();monitor.wait()
    if log:log.close()
    (directory/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
# Retain service errors, counts and baseline settings, never docker compose config (contains passwords).
with (directory/'app.log').open('w') as f:command(DC+['logs','--since',metadata['load_start_utc'],'--no-color','app'],stdout=f)
with (directory/'db.log').open('w') as f:command(DC+['logs','--since',metadata['load_start_utc'],'--no-color','db'],stdout=f)
counts="import json;from db import DB;\nwith DB() as db: print(json.dumps({t:db.query('SELECT count(*) AS n FROM '+t)[0]['n'] for t in ('readers','books','copies','loans')}))"
(directory/'after_counts.json').write_text(capture(DC+['exec','-T','app','python','-c',counts]))
summary=directory/'summary.json'
if summary.exists():
    d=json.loads(summary.read_text());dur=d['duration'];errors=d['error_rate']
    valid=dur.get('count',d.get('requests',0))>0 and errors is not None
    passed=valid and dur.get('p(95)',float('inf'))<500 and errors<.01
    print(f"p50={dur.get('med')} мс; p95={dur.get('p(95)')} мс; max={dur.get('max')} мс; errors={errors}; dropped={d['dropped']}; actual={d['effective_rps']:.2f}/с")
    print('ПОРОГ ВЫДЕРЖАН' if passed else 'ПОРОГ НЕ ВЫДЕРЖАН / НЕТ ДАННЫХ')
    if d['dropped']:print('Есть пропуски: генератор не подал весь заданный поток. Не считать ступень полностью доставленной.')
    if rc not in (0,99):print('Ошибка запуска k6: см. k6.log, код',rc)
else:print('Нет summary.json: пришлите k6.log. Код k6:',rc)
print('Для анализа отправьте каталог:',directory)
