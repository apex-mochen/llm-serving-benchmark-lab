// Optional browser E2E: Node 22+, a local Edge/Chrome executable, and an already running demo.
import {spawn} from 'node:child_process';
import {mkdir,readFile,writeFile,mkdtemp} from 'node:fs/promises';
import {resolve,join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const base=process.env.DEMO_URL||'http://127.0.0.1:8765';
assert(['127.0.0.1','localhost'].includes(new URL(base).hostname),'Only local test URLs allowed');
const browser=process.env.BROWSER_PATH||'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
await mkdir(join(root,'.benchmark'),{recursive:true});
const profile=await mkdtemp(join(root,'.benchmark','browser-check-'));
const out=join(root,'docs/validation/demo-browser');await mkdir(out,{recursive:true});
await mkdir(join(root,'docs/media'),{recursive:true});
const child=spawn(browser,['--headless=new','--disable-gpu','--no-first-run',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank'],{windowsHide:true,stdio:'ignore'});
let socket;const errors=[];const checks=[];
try{
  let port;
  for(let i=0;i<100;i++){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await sleep(100);}}
  assert(port,'Headless browser did not start');
  const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page=pages.find(p=>p.type==='page');assert(page);
  socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  let sequence=0;const pending=new Map();
  socket.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const p=pending.get(message.id);if(p){pending.delete(message.id);message.error?p.reject(new Error(JSON.stringify(message.error))):p.resolve(message.result);}}else if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout '+method));},15000);pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value;};
  const until=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await sleep(100);}throw new Error('UI condition not reached: '+expression);};
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});
  await until("document.getElementById('run-count')?.textContent==='24' && document.querySelectorAll('#detail .tails strong').length===3");
  assert.equal(await evaluate("document.getElementById('request-count').textContent"),'1,536');checks.push('24 real runs / 1536 requests rendered');
  assert.equal(await evaluate("document.querySelectorAll('#chart svg rect').length"),8);checks.push('8 real aggregate cells rendered');
  let shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(root,'docs/media/results-browser-desktop.png'),Buffer.from(shot.data,'base64'));
  await evaluate("document.getElementById('engine').value='vllm';document.getElementById('engine').dispatchEvent(new Event('change'))");
  await until("document.getElementById('run-count').textContent==='12'");checks.push('Single-engine filter: 12 runs');
  await evaluate("document.getElementById('concurrency').value='32';document.getElementById('concurrency').dispatchEvent(new Event('change'))");
  await until("document.getElementById('run-count').textContent==='3' && document.querySelectorAll('#runs tr').length===3");checks.push('Concurrency filter: 3 runs / 192 requests');
  await evaluate("document.querySelectorAll('.run-link')[1].click()");
  await until("document.getElementById('detail-title').textContent.includes('第2次') && document.querySelector('#detail .tails strong')!==null");checks.push('Run detail selection and request plot');
  const csv=await(await fetch(base+'/api/export.csv?engine=vllm&concurrency=32')).text();assert.equal(csv.trim().split('\n').length,4);checks.push('CSV export matches filter');
  const listing=await(await fetch(base+'/api/runs?engine=vllm&concurrency=32')).json();
  const raw=await(await fetch(base+`/api/runs/${listing.runs[0].id}/artifacts/result`)).json();assert.equal(raw.completed,64);checks.push('Raw artifact contains actual 64-request result');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(300);
  assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Unexpected horizontal document overflow');checks.push('390px viewport has no document overflow');
  shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(root,'docs/media/results-browser-mobile.png'),Buffer.from(shot.data,'base64'));
  assert.deepEqual(errors,[]);checks.push('No uncaught browser runtime exceptions');
  await writeFile(join(out,'browser-e2e.json'),JSON.stringify({status:'PASS',checks,inference_launched:false,source:'existing historical baseline',browser:browser.split(/[\\/]/).pop()},null,2)+'\n');
  console.log(JSON.stringify({status:'PASS',checks},null,2));
  await send('Browser.close').catch(()=>{});
}catch(error){await writeFile(join(out,'browser-e2e.json'),JSON.stringify({status:'FAIL',checks,error:String(error),runtime_errors:errors},null,2)+'\n');throw error;}
finally{if(socket)socket.close();child.kill();}
