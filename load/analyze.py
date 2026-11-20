"""Summaries and a standalone SVG chart using only Python's standard library."""
import csv,json,sys,html,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def profile_rows(path):
    d=json.loads(path.read_text());frames=d['shared']['frames'];inclusive=collections.Counter();own=collections.Counter()
    all_weight=0.;handler_weight=0.
    for profile in d.get('profiles',[]):
        if profile['type']!='sampled':continue
        for stack,w in zip(profile.get('samples',[]),profile.get('weights',[1]*len(profile.get('samples',[])))):
            all_weight+=w
            # Exclude idle main-loop stacks from the handler denominator, but retain them in all_weight.
            if not any(frames[i].get('name')=='summary' and frames[i].get('file','').endswith('app.py') for i in stack):continue
            handler_weight+=w
            for i in set(stack):inclusive[i]+=w
            if stack:own[stack[-1]]+=w
    result=[]
    for i,w in inclusive.most_common():
        f=frames[i]
        result.append({'function':f.get('name'),'file':f.get('file'),'line':f.get('line'),
            'inclusive_pct_of_summary':100*w/handler_weight if handler_weight else 0,
            'self_pct_of_summary':100*own[i]/handler_weight if handler_weight else 0,
            'inclusive_pct_all_threads':100*w/all_weight if all_weight else 0})
    return {'all_thread_weight':all_weight,'summary_thread_weight':handler_weight,
        'note':'--idle includes waiting stacks. Percentages are weighted thread-stack observations, not CPU utilization. Inclusive shares overlap.',
        'functions':result}

def chart(rows,mode,path):
    selected=[r for r in rows if r['mode']==mode]
    if not selected:return
    ymax=max(600,max(r['p95_ms'] for r in selected)*1.1);xmax=max(r['rate'] for r in selected)
    def x(v):return 75+610*v/max(1,xmax)
    def y(v):return 355-290*v/ymax
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="760" height="440" viewBox="0 0 760 440">',
           '<rect width="760" height="440" fill="white"/>',f'<text x="75" y="28" font-family="sans-serif" font-size="18">{mode}: p95 / requests per second</text>',
           '<path d="M75 55V355H700" fill="none" stroke="#334155"/>']
    for i in range(6):
        v=ymax*i/5;yy=y(v)
        parts.append(f'<path d="M75 {yy}H700" stroke="#e2e8f0"/><text x="12" y="{yy+5}" font-family="sans-serif" font-size="12">{v:.0f}</text>')
    parts.append(f'<path d="M75 {y(500)}H700" stroke="#dc2626" stroke-dasharray="6 4"/><text x="560" y="{y(500)-8}" fill="#dc2626">500 ms</text>')
    pts=' '.join(f'{x(r["rate"])},{y(r["p95_ms"])}' for r in selected)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    for r in selected:
        xx=x(r['rate']);yy=y(r['p95_ms']);color='#2563eb' if r['passed'] else '#dc2626'
        parts.append(f'<circle cx="{xx}" cy="{yy}" r="5" fill="{color}"/><text x="{xx-9}" y="375" font-family="sans-serif" font-size="12">{r["rate"]}</text>')
    parts+=['<text x="280" y="410" font-family="sans-serif">Requested requests per second</text>','<text x="8" y="45" font-family="sans-serif">p95, ms</text>','</svg>']
    path.write_text('\n'.join(parts))

def main():
    root=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'results'/'hw2'
    rows=[]
    for p in sorted(root.glob('*/summary.json')):
        d=json.loads(p.read_text());v=d['duration']
        if 'p(95)' not in v:continue
        m=json.loads((p.parent/'metadata.json').read_text())
        if m.get('profiled'):continue
        statuses=collections.Counter()
        metric=p.parent/'metrics.jsonl'
        if metric.exists():
            for line in metric.open():
                point=json.loads(line)
                if point.get('type')=='Point' and point.get('metric')=='responses':
                    tags=point['data'].get('tags',{});statuses[(tags.get('operation'),tags.get('code'))]+=point['data']['value']
        (p.parent/'response_counts.json').write_text(json.dumps([{'operation':k[0],'code':k[1],'count':n} for k,n in statuses.items()],indent=2))
        row={'mode':d['mode'],'rate':d['rate'],'p50_ms':v['med'],'p95_ms':v['p(95)'],'max_ms':v['max'],
             'errors_pct':100*d['error_rate'],'dropped':d['dropped'],'effective_rps':d['effective_rps'],
             'business_conflicts':d['conflicts'],'passed':v['p(95)']<500 and d['error_rate']<.01,
             'fully_delivered':d['dropped']==0,'directory':p.parent.name,'commit':m['commit']}
        rows.append(row)
    rows.sort(key=lambda r:(r['mode'],r['rate'],r['directory']))
    if rows:
        with (root/'steps.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        for mode in ['mixed','heavy']:chart(rows,mode,root/(mode+'-p95.svg'))
    for p in root.glob('*/profile.speedscope.json'):
        (p.parent/'hot-functions.json').write_text(json.dumps(profile_rows(p),ensure_ascii=False,indent=2))
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    print('Saved steps.csv, charts (if there are steps), and hot-functions.json (if there are profiles).')
if __name__=='__main__':main()
