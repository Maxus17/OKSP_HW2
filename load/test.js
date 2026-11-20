import http from 'k6/http';
import encoding from 'k6/encoding';
import exec from 'k6/execution';
import {check, fail} from 'k6';
import {Trend, Rate, Counter} from 'k6/metrics';
import {SharedArray} from 'k6/data';

const mode=__ENV.MODE || 'mixed';
const rate=Number(__ENV.RATE || 2);
const seconds=Number(__ENV.SECONDS || 30);
if (!['mixed','heavy'].includes(mode) || !Number.isInteger(rate) || rate<1 || !Number.isInteger(seconds) || seconds<1)
  throw Error('MODE=mixed/heavy; RATE and SECONDS must be positive integers');
if (!__ENV.API_PASSWORD) throw Error('API_PASSWORD missing');
const fixture=new SharedArray('fixtures',()=>[JSON.parse(open('/results/hw2/fixtures.json'))])[0];
const headers={Authorization:'Basic '+encoding.b64encode((__ENV.API_USER || 'librarian')+':'+__ENV.API_PASSWORD),'Content-Type':'application/json'};
const base=__ENV.BASE_URL || 'http://app:8000';
const timings=new Trend('target_ms',true);
const errors=new Rate('target_errors');
const attempts=new Counter('target_requests');
const conflicts=new Counter('business_conflicts');
const statuses=new Counter('responses');
const issued=[]; // Per-VU recent successful loans, preferred for return when available.
const pre=Number(__ENV.PRE_VUS || 100), max=Number(__ENV.MAX_VUS || 400);
export const options={
  scenarios:{[mode]:{executor:'constant-arrival-rate',rate,timeUnit:'1s',duration:seconds+'s',
    preAllocatedVUs:pre,maxVUs:max,exec:'step',gracefulStop:'30s'}},
  thresholds:{target_ms:['p(95)<500'],target_errors:['rate<0.01'],
    'target_ms{operation:list}':[], 'target_ms{operation:filter}':[],
    'target_ms{operation:detail}':[], 'target_ms{operation:summary}':[],
    'target_ms{operation:issue}':[], 'target_ms{operation:return}':[]},
  summaryTrendStats:['avg','min','med','max','p(95)','count'],
  systemTags:['status','method','name','scenario','expected_response'],
};
function params(operation,write=false){return {headers,redirects:0,timeout:'30s',
  tags:{operation,name:operation},responseCallback:write ? http.expectedStatuses(200,201,409) : http.expectedStatuses(200)};}
export function setup(){
  // Basic Auth has no login endpoint/session. One authorized readiness check before timed traffic.
  const r=http.get(base+'/api/summary',params('setup'));
  if(r.status!==200 || !r.json() || r.json().on_hands===undefined) fail('Readiness/authentication failed: '+r.status);
  if(fixture.prefix!==__ENV.PERSONAL_PREFIX) fail('Fixture belongs to a different personal prefix');
}
export function operationAt(index){
  // Permutation avoids blocks of writes; exactly weighted for each full 100 started iterations.
  const bucket=((index%100)*37)%100;
  return bucket<30?'list':bucket<45?'filter':bucket<75?'detail':bucket<85?'issue':bucket<95?'return':'summary';
}
function pick(values){return values[Math.floor(Math.random()*values.length)];}
export function step(){
  const operation=mode==='heavy'?'summary':operationAt(exec.scenario.iterationInTest);
  let response;
  const p=params(operation,operation==='issue'||operation==='return');
  if(operation==='list') response=http.get(base+'/api/loans?page=1&size=20',p);
  if(operation==='filter') response=http.get(base+'/api/loans?page=1&size=20&status=overdue',p);
  if(operation==='detail') response=http.get(base+'/api/loans/'+(1+Math.floor(Math.random()*fixture.loan_count)),p);
  if(operation==='summary') response=http.get(base+'/api/summary',p);
  if(operation==='issue'){
    response=http.post(base+'/api/loans',JSON.stringify({reader_id:pick(fixture.reader_ids),copy_id:pick(fixture.copy_ids),days:14}),p);
    if(response.status===201){try{issued.push(response.json().id);}catch(e){}}
  }
  if(operation==='return'){
    const id=issued.length?issued.pop():pick(fixture.return_ids);
    response=http.post(base+'/api/loans/'+id+'/return','{}',p);
  }
  const expectedStatus=operation==='issue'?[201,409]:operation==='return'?[200,409]:[200];
  let data=null;try{data=response.json();}catch(e){}
  const business=response.status===409 && data && typeof data.error==='string';
  let valid=false;
  if(response.status===200 || response.status===201){
    valid=operation==='list'||operation==='filter' ? data && Array.isArray(data.items) && Number.isInteger(data.total)
      :operation==='summary' ? data && Number.isInteger(data.on_hands) && Array.isArray(data.top_books)
      :data && Number.isInteger(data.id);
  }
  const ok=expectedStatus.includes(response.status) && Boolean(business||valid);
  timings.add(response.timings.duration,{operation});
  errors.add(!ok,{operation});attempts.add(1,{operation});
  statuses.add(1,{operation,code:String(response.status)});
  check(response,{'expected status and response shape':()=>ok},{operation});
  if(business) conflicts.add(1,{operation});
  if(!ok) console.error(JSON.stringify({operation,status:response.status,body:response.body?.slice(0,300)}));
}
export function handleSummary(data){
  const path=__ENV.OUT || '/results/hw2/last';
  const v=name=>data.metrics[name]?.values || {};
  const n=v('target_requests').count || 0;
  const result={mode,rate,seconds,prefix:__ENV.PERSONAL_PREFIX,
    duration:v('target_ms'),error_rate:v('target_errors').rate ?? null,
    requests:n,dropped:v('dropped_iterations').count || 0,
    effective_rps:n/(data.state.testRunDurationMs/1000),
    note:'effective_rps includes drain/gracefulStop; profile duration requested separately',
    run_duration_ms:data.state.testRunDurationMs,
    conflicts:v('business_conflicts').count || 0,summary:data};
  const line=`${mode} rate=${rate}: p50=${result.duration.med?.toFixed(2)} ms; p95=${result.duration['p(95)']?.toFixed(2)} ms; errors=${result.error_rate}; dropped=${result.dropped}; actual=${result.effective_rps.toFixed(2)}/s\n`;
  return {[path+'.json']:JSON.stringify(result,null,2),stdout:line};
}
