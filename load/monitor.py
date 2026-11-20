"""Sample every two seconds with a persistent stats stream and SQL session."""
import json,sys,time,signal,subprocess,threading
from pathlib import Path
from datetime import datetime,timezone
from common import DC,capture,prefix
running=threading.Event(); running.set()
def stop(*_):running.clear()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
ids=[capture(DC+['ps','-q',s]) for s in ('app','db')]
latest={}; lock=threading.Lock()
stream=subprocess.Popen(['docker','stats','--format','{{json .}}']+ids,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def collect():
    for line in stream.stdout:
        try:
            # Docker may prefix terminal-clearing escapes, even with JSON formatting.
            start=line.find('{')
            if start<0:continue
            value=json.JSONDecoder().raw_decode(line[start:])[0]
            with lock:latest[value['Name']]=(value,datetime.now(timezone.utc).isoformat())
        except (ValueError,KeyError):continue
thread=threading.Thread(target=collect,daemon=True);thread.start()
query="""SELECT json_build_object('total',count(*),'active',count(*) FILTER(WHERE state='active'),'waiting_lock',count(*) FILTER(WHERE wait_event_type='Lock')) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid();"""
session=subprocess.Popen(DC+['exec','-T','db','psql','-U','librarian','-d',prefix(),'-At','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True)
start=time.monotonic();deadline=start
try:
    with path.open('w') as f:
        while running.is_set():
            tick=time.monotonic()
            row={'timestamp':datetime.now(timezone.utc).isoformat(),'elapsed_s':tick-start}
            try:
                with lock:
                    values=list(latest.values())
                row['containers']=[v[0] for v in values]
                row['container_sample_utc']={v[0]['Name']:v[1] for v in values}
                session.stdin.write(query+'\n');session.stdin.flush()
                result=session.stdout.readline()
                if not result:raise RuntimeError('SQL sampling session ended')
                row['connections']=json.loads(result)
                if len(values)!=len(ids):row['warming_up']=True
            except Exception as e:row['error']=str(e)
            f.write(json.dumps(row)+'\n');f.flush()
            deadline+=2
            while running.is_set() and time.monotonic()<deadline:
                time.sleep(min(.1,deadline-time.monotonic()))
finally:
    session.stdin.close()
    try:session.wait(timeout=5)
    except subprocess.TimeoutExpired:session.terminate();session.wait(timeout=5)
    stream.terminate();stream.wait(timeout=5)