'use strict';
const $ = id => document.getElementById(id);
let runs = [], selected = null, detailSequence = 0, overall = null;
const colors = {vllm:'#2366cc',sglang:'#008e83'};
const names = {vllm:'vLLM',sglang:'SGLang'};
const fmt = value => Number(value).toLocaleString('zh-CN',{minimumFractionDigits:1,maximumFractionDigits:2});
function node(tag, text, cls) { const e = document.createElement(tag); if(text !== undefined)e.textContent=text; if(cls)e.className=cls;return e; }
function svg(tag, attributes={}, text) {const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attributes))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function median(values) {const v=[...values].sort((a,b)=>a-b),i=Math.floor(v.length/2);return v.length%2?v[i]:(v[i-1]+v[i])/2;}
function query() {const q=new URLSearchParams();for(const[id,key]of[['engine','engine'],['concurrency','concurrency'],['source','source']])if($(id).value)q.set(key,$(id).value);return q.toString();}
async function get(url){const r=await fetch(url);if(!r.ok){const e=await r.json();throw new Error(e.detail||'数据加载失败');}return r.json();}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
function chart(){
  const field=$('metric').value, chart=svg('svg',{viewBox:'0 0 760 245',role:'img','aria-label':'每组重复均值的中位数及最小最大范围'}),groups=new Map();
  // Imported runs come from other experiments; never pool them into baseline medians.
  const base=runs.filter(r=>r.kind==='baseline');
  for(const r of base){const key=r.engine+':'+r.concurrency;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r[field]);}
  const all=[...groups.values()].flat();if(!all.length){$('chart').replaceChildren(node('p',runs.length?'当前筛选只有导入结果；图表只展示历史基线。':'没有匹配的结果。','empty'));compare(base,field);return;}
  const top=Math.max(...all)*1.15||1, x0=65,y0=198,h=166,w=630;
  for(let i=0;i<=4;i++){const y=y0-h*i/4;chart.append(svg('line',{x1:x0,x2:x0+w,y1:y,y2:y,stroke:'#e8eef4','stroke-dasharray':'3 4'}));chart.append(svg('text',{x:x0-10,y:y+3,'text-anchor':'end',fill:'#8393a5','font-size':10},fmt(top*i/4)));}
  const cs=[...new Set(base.map(r=>r.concurrency))].sort((a,b)=>a-b),engines=['vllm','sglang'].filter(e=>base.some(r=>r.engine===e));
  cs.forEach((c,i)=>{const center=x0+w*(i+.5)/cs.length;chart.append(svg('text',{x:center,y:225,'text-anchor':'middle',fill:'#718297','font-size':11},'并发 '+c));
    engines.forEach((engine,j)=>{const values=groups.get(engine+':'+c);if(!values)return;const x=center+(j-(engines.length-1)/2)*31,mean=median(values),min=Math.min(...values),max=Math.max(...values),y=v=>y0-h*v/top;
      chart.append(svg('rect',{x:x-10,y:y(mean),width:20,height:y0-y(mean),rx:3,fill:colors[engine],opacity:.85}));
      chart.append(svg('line',{x1:x,x2:x,y1:y(min),y2:y(max),stroke:colors[engine],'stroke-width':1.7}));
      for(const value of [min,max])chart.append(svg('line',{x1:x-5,x2:x+5,y1:y(value),y2:y(value),stroke:colors[engine],'stroke-width':1.7}));
      chart.append(svg('title',{},`${names[engine]} 并发${c}：中位数${fmt(mean)}，范围${fmt(min)}–${fmt(max)}`));
    });});
  $('chart').replaceChildren(chart);
  compare(base,field);
}
// Repeat range of the same configuration is the noise reference (an A/A-style check).
function compare(base,field){
  const target=$('compare'),cs=[...new Set(base.map(r=>r.concurrency))].sort((a,b)=>a-b);
  const pairs=cs.map(c=>[c,...['vllm','sglang'].map(e=>base.filter(r=>r.engine===e&&r.concurrency===c).map(r=>r[field]))]).filter(([,a,b])=>a.length&&b.length);
  if(!pairs.length){target.replaceChildren(node('p','需要同一并发下同时有 vLLM 和 SGLang 的历史基线。','empty'));return;}
  const table=node('table',undefined,'compare-table'),head=node('tr');
  for(const h of ['并发','判断','比值 vLLM/SGLang','vLLM 中位 [范围]','SGLang 中位 [范围]'])head.append(node('th',h));table.append(head);
  const span=v=>`${fmt(median(v))} [${fmt(Math.min(...v))}–${fmt(Math.max(...v))}]`;
  for(const[c,a,b]of pairs){
    const separated=Math.max(...a)<Math.min(...b)||Math.max(...b)<Math.min(...a),tr=node('tr');tr.dataset.concurrency=c;
    tr.append(node('td','C'+c),node('td',separated?'差异超出重复波动':'范围重叠 · 不判定快慢',separated?'verdict separated':'verdict overlap'),
      node('td',(median(a)/median(b)).toFixed(2)),node('td',span(a)),node('td',span(b)));
    table.append(tr);
  }
  target.replaceChildren(table);
}
function renderTable(){
  $('runs').replaceChildren();
  for(const r of runs){const tr=node('tr');tr.dataset.id=r.id;tr.classList.toggle('selected',r.id===selected);
    const first=node('td');first.append(node('span',names[r.engine],`engine-tag ${r.engine==='sglang'?'sglang-tag':''}`),document.createTextNode('C'+(r.concurrency??'—')));
    if(r.kind==='imported')first.append(node('span','导入','import-tag'));tr.append(first);
    for(const value of [r.kind==='imported'?(r.label||'—'):`#${r.repeat+1}`,`${fmt(r.mean_ttft_ms)} ms`,`${fmt(r.mean_tpot_ms)} ms`,fmt(r.output_tokens_per_s)])tr.append(node('td',value));
    const cell=node('td'),button=node('button','查看 →','run-link');button.setAttribute('aria-label',`查看 ${runTitle(r)}`);button.onclick=()=>select(r.id);cell.append(button);tr.append(cell);$('runs').append(tr);
  }
  $('table-count').textContent=runs.length;
}
// Gantt of request phases plus the in-flight step curve; client-side clock only.
function renderTimeline(r){
  const panel=$('timeline-panel'),rows=r.request_timing;
  if(!rows||rows[0].dispatch_ms===undefined){panel.hidden=true;return;}
  panel.hidden=false;$('timeline-title').textContent=runTitle(r);
  const t=r.timeline,span=t.span_ms||1,W=1000,left=46,right=12,top=8,curveH=64,gap=14,rowH=Math.max(3,Math.min(8,320/rows.length));
  const H=top+curveH+gap+rows.length*rowH+24,x=v=>left+(W-left-right)*v/span,g=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${rows.length}个请求的阶段时间线`});
  const events=rows.flatMap(q=>[[q.dispatch_ms,1],[q.end_ms,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const cap=Math.max(t.peak_in_flight,t.max_concurrency||0,1),y=v=>top+curveH-curveH*v/cap;let n=0,pts=[`${x(0)},${y(0)}`];
  for(const[time,change]of events){pts.push(`${x(time)},${y(n)}`);n+=change;pts.push(`${x(time)},${y(n)}`);}
  g.append(svg('line',{x1:left,x2:W-right,y1:y(0),y2:y(0),stroke:'#e8eef4'}));
  if(t.max_concurrency){g.append(svg('line',{x1:left,x2:W-right,y1:y(t.max_concurrency),y2:y(t.max_concurrency),stroke:'#9aa8b6','stroke-dasharray':'4 4'}));g.append(svg('text',{x:left-6,y:y(t.max_concurrency)+3,'text-anchor':'end',fill:'#8393a5','font-size':10},String(t.max_concurrency)));}
  g.append(svg('polyline',{points:pts.join(' '),fill:'none',stroke:colors[r.engine],'stroke-width':1.6}));
  g.append(svg('text',{x:left-6,y:y(0)+3,'text-anchor':'end',fill:'#8393a5','font-size':10},'0'));
  const ordered=[...rows].sort((a,b)=>a.arrival_ms-b.arrival_ms||a.index-b.index),y0=top+curveH+gap;
  ordered.forEach((q,i)=>{const row=svg('g'),yy=y0+i*rowH,h=Math.max(1.5,rowH-1);
    for(const[a,b,c]of[[q.arrival_ms,q.dispatch_ms,'#c9d2dc'],[q.dispatch_ms,q.first_token_ms,'#e0a43a'],[q.first_token_ms,q.end_ms,colors[r.engine]]])
      if(b>a)row.append(svg('rect',{x:x(a),y:yy,width:Math.max(.5,x(b)-x(a)),height:h,fill:c}));
    row.append(svg('title',{},`请求 #${q.index+1}：客户端等待 ${fmt(q.client_queue_ms)} ms，首 token ${fmt(q.ttft_ms)} ms，端到端 ${fmt(q.e2e_ms)} ms`));g.append(row);});
  for(let i=0;i<=4;i++){const v=span*i/4;g.append(svg('text',{x:x(v),y:H-6,'text-anchor':i===0?'start':i===4?'end':'middle',fill:'#8393a5','font-size':10},(v/1000).toFixed(1)+' s'));}
  $('timeline').replaceChildren(g);
  const waited=rows.filter(q=>q.client_queue_ms>1).length,maxWait=Math.max(...rows.map(q=>q.client_queue_ms));
  $('timeline-stats').textContent=`峰值同时在途 ${t.peak_in_flight}`+(t.max_concurrency?` / 客户端上限 ${t.max_concurrency}（${t.within_client_limit?'未超过上限':'超过上限，请检查原始记录'}）`:'')+` · 总时长 ${fmt(span/1000)} s · ${waited} 个请求在客户端等待超过 1 ms（最长 ${fmt(maxWait)} ms）`;
}
function kv(parent,pairs){const dl=node('dl',undefined,'kv');for(const [key,value]of pairs)dl.append(node('dt',key),node('dd',value));parent.append(dl);}
function label(parent,text){parent.append(node('span',text,'detail-label'));}
function runTitle(r){return r.kind==='imported'?`${names[r.engine]} · C${r.concurrency??'—'} · 导入`:`${names[r.engine]} · C${r.concurrency} · 第${r.repeat+1}次`;}
const artifactTitles={result:'原始结果 JSON',metadata:'运行配置',validation:'校验记录',provenance:'导入溯源记录'};
async function select(id){
  selected=id;const sequence=++detailSequence;renderTable();
  try{const r=await get('/api/runs/'+encodeURIComponent(id));if(sequence!==detailSequence)return;
    $('detail-title').textContent=runTitle(r);
    const target=$('detail');target.replaceChildren(node('p',r.id,'detail-sub'));
    const imported=r.kind==='imported';
    if(imported){const p=r.provenance;kv(target,[['状态',r.detail_level==='detailed'?'已导入 · 逐请求复核':'已导入 · 仅汇总'],['请求数',`${r.requests} / ${r.requests}`],['原文件',p.source_name],['导入时间',p.imported_utc.slice(0,19).replace('T',' ')+' UTC'],['工具记录日期',String(p.reported.date??'—')],['到达率',String(p.reported.request_rate??'—')]]);}
    else{const env=r.environment;kv(target,[['状态','已校验历史测量'],['请求数',`${r.requests} / ${r.requests}`],['模型版本',env.model_revision.slice(0,12)],['输入 / 输出',`${env.input_tokens} / ${env.output_tokens} tokens`],['GPU',env.gpu],['引擎版本',env.engine_version],['随机种子',String(env.seed)]]);}
    label(target,'端到端延迟 · 本次请求内分位数');const tails=node('div',undefined,'tails');
    for(const p of ['50','95','99']){const box=node('div');box.append(node('small','P'+p+' · ms'),node('strong',fmt(r.tails.latencies[p])));tails.append(box);}target.append(tails);
    target.append(node('p',`每次只有${r.requests}个请求，P99仅作描述，不代表线上尾延迟。客户端等待不等同服务端调度排队。`,'tail-note'));
    if(r.request_timing){label(target,'逐请求 TTFT · 按原始序号');const mini=node('div',undefined,'mini-chart'),graph=svg('svg',{viewBox:'0 0 300 85',role:'img','aria-label':`${r.request_timing.length}个请求的TTFT序列`}),max=Math.max(...r.request_timing.map(v=>v.ttft_ms))||1;
      const points=r.request_timing.map((v,i)=>`${8+i*284/Math.max(1,r.request_timing.length-1)},${74-v.ttft_ms/max*62}`).join(' ');graph.append(svg('polyline',{points,fill:'none',stroke:colors[r.engine],'stroke-width':1.5}));mini.append(graph);target.append(mini);}
    else target.append(node('p','原文件未用 --save-detailed 保存，没有逐请求 TTFT 与错误记录。','tail-note'));
    if(imported){label(target,'导入核对');const list=node('ul',undefined,'check-list');for(const c of r.provenance.checks)list.append(node('li',c));target.append(list);
      for(const l of r.limitations)target.append(node('p',l,'tail-note'));}
    else{const env=r.environment;label(target,'配置与证据');kv(target,[['模型快照',env.model_snapshot],['引擎提交',env.engine_commit.slice(0,12)],['负载', '有限批次 · 立即到达'],['Prefix cache','关闭']]);}
    const links=node('div',undefined,'download-links');for(const k of Object.keys(r.artifacts)){const a=node('a',artifactTitles[k]||k);a.href=`/api/runs/${encodeURIComponent(id)}/artifacts/${k}`;links.append(a);}target.append(links,node('p','SHA256 · '+r.source_sha256,'hash'));renderTimeline(r);syncUrl();error('');
  }catch(e){if(sequence!==detailSequence)return;$('detail').replaceChildren(node('p','无法核对这条记录的原始文件。','muted'));$('timeline-panel').hidden=true;error(e.message);}
}
// Shareable view: filters, metric and the selected run live in the query string.
function syncUrl(){const q=new URLSearchParams(query());if($('metric').value!=='mean_ttft_ms')q.set('metric',$('metric').value);if(selected)q.set('run',selected);
  const s=q.toString();history.replaceState(null,'',s?'?'+s:location.pathname);}
function restoreUrl(){const q=new URLSearchParams(location.search);
  for(const id of ['engine','concurrency','source','metric']){const v=q.get(id);if(v!==null&&[...$(id).options].some(o=>o.value===v))$(id).value=v;}
  selected=q.get('run');}
async function copyLink(){syncUrl();const button=$('copy-link');
  try{await navigator.clipboard.writeText(location.href);button.textContent='已复制链接 ✓';}catch{button.textContent='请复制地址栏链接';}
  setTimeout(()=>{button.textContent='复制当前视图链接';},1800);}
async function refresh(){
  $('refresh').disabled=true;
  try{const data=await get('/api/runs?'+query());runs=data.runs;$('run-count').textContent=data.total;$('request-count').textContent=data.requests.toLocaleString();
    // Filtered counts must not read as the whole dataset.
    if(!query())overall={total:data.total,requests:data.requests};
    const filtered=Boolean(query())&&overall;
    $('run-note').textContent=filtered?`当前筛选 · 全部 ${overall.total} 次`:'每一行对应一次原始运行';
    $('request-note').textContent=filtered?`当前筛选 · 全部 ${overall.requests.toLocaleString()} 条`:'失败或不完整数据不计入索引';
    // Imported files carry no verified hardware/version, so never label them "real GPU".
    const kinds=new Set(runs.map(r=>r.kind)),mixed=kinds.size>1,onlyImported=kinds.size===1&&kinds.has('imported');
    $('source-word').textContent=mixed?'基线 + 导入':onlyImported?'导入结果':'真实 GPU';
    $('source-note').textContent=mixed||onlyImported?'导入结果的硬件与版本未核实':'本地实验室 · 有限请求批次';$('engine-count').textContent=new Set(runs.map(r=>r.engine)).size;$('export').href='/api/export.csv?'+query();chart();renderTable();error('');
    if(runs.length)await select(runs.some(r=>r.id===selected)?selected:runs[0].id);else{selected=null;$('detail').replaceChildren(node('p','没有匹配记录。','muted'));$('detail-title').textContent='选择运行记录';$('timeline-panel').hidden=true;syncUrl();}
  }catch(e){error(e.message);}finally{$('refresh').disabled=false;}
}
for(const id of ['engine','concurrency','source'])$(id).addEventListener('change',refresh);
$('metric').addEventListener('change',()=>{chart();syncUrl();});$('refresh').onclick=refresh;$('copy-link').onclick=copyLink;restoreUrl();refresh();
