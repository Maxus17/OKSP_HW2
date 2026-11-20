import json,subprocess
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DC=['docker','compose','-f','compose.yaml','-f','compose.hw2.yaml']
def command(args,**kw):
    return subprocess.run(args,cwd=ROOT,text=True,check=True,**kw)
def capture(args):return command(args,capture_output=True).stdout.strip()
@lru_cache(maxsize=1)
def prefix():return capture(DC+['exec','-T','db','printenv','POSTGRES_DB'])
def sql(query):
    return capture(DC+['exec','-T','db','psql','-U','librarian','-d',prefix(),'-At','-v','ON_ERROR_STOP=1','-c',query])
def stats(ids):
    raw=capture(['docker','stats','--no-stream','--format','{{json .}}']+ids)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]
