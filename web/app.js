'use strict';
const $ = id => document.getElementById(id);
let runs = [], selected = null, detailSequence = 0, overall = null, current = null;
const names = {vllm:'vLLM',sglang:'SGLang'};
const metricNames = {mean_ttft_ms:'平均 TTFT',mean_tpot_ms:'平均 TPOT',output_tokens_per_s:'输出吞吐'};
const metricUnits = {mean_ttft_ms:'ms',mean_tpot_ms:'ms',output_tokens_per_s:'tokens/s'};
const fmt = value => Number(value).toLocaleString('zh-CN',{minimumFractionDigits:1,maximumFractionDigits:2});
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
function node(tag, text, cls) { const e = document.createElement(tag); if(text !== undefined)e.textContent=text; if(cls)e.className=cls;return e; }
function svg(tag, attributes={}, text) {const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attributes))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function median(values) {const v=[...values].sort((a,b)=>a-b),i=Math.floor(v.length/2);return v.length%2?v[i]:(v[i-1]+v[i])/2;}
function query() {const q=new URLSearchParams();for(const[id,key]of[['engine','engine'],['concurrency','concurrency'],['source','source']])if($(id).value)q.set(key,$(id).value);return q.toString();}
async function get(url){const r=await fetch(url);if(!r.ok){const e=await r.json();throw new Error(e.detail||'数据加载失败');}return r.json();}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
function store(key,value){try{localStorage.setItem(key,value);}catch{}}
function recall(key){try{return localStorage.getItem(key);}catch{return null;}}

// ---------- small conveniences: toast, tooltip, copy ----------
let toastTimer;
function toast(message){const t=$('toast');t.textContent=message;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),1600);}
function tip(event,title,rows){const t=$('tip');t.replaceChildren(node('b',title));
  for(const[k,v]of rows){const line=node('span');line.append(node('em',k),node('strong',v));t.append(line);}
  t.hidden=false;const pad=14,w=t.offsetWidth,h=t.offsetHeight;
  let x=event.clientX+pad,y=event.clientY+pad;if(x+w>innerWidth-8)x=event.clientX-w-pad;if(y+h>innerHeight-8)y=event.clientY-h-pad;
  t.style.left=Math.max(8,x)+'px';t.style.top=Math.max(8,y)+'px';}
function hideTip(){$('tip').hidden=true;}
// Clipboard API first; fall back to a hidden textarea for older or non-secure contexts.
async function writeClipboard(text){
  try{await navigator.clipboard.writeText(text);return true;}catch{}
  const area=node('textarea');area.value=text;area.setAttribute('readonly','');area.style.cssText='position:fixed;opacity:0;top:0;left:0';
  document.body.append(area);area.select();let ok=false;try{ok=document.execCommand('copy');}catch{}area.remove();return ok;}
async function copy(text,message){toast(await writeClipboard(text)?message:'无法写入剪贴板，请手动复制');}
function emptyState(message,withClear){const box=node('div',undefined,'empty');
  const icon=svg('svg',{viewBox:'0 0 24 24','aria-hidden':'true'});icon.append(svg('circle',{cx:11,cy:11,r:7}),svg('path',{d:'M20 20l-4-4'}));box.append(icon,node('p',message));
  if(withClear&&query()){const b=node('button','清除筛选','link-button');b.type='button';b.onclick=clearFilters;box.append(b);}return box;}

// ---------- theme ----------
const themes=['auto','light','dark'],themeLabels={auto:'跟随系统',light:'浅色',dark:'深色'};
function applyTheme(pref){if(pref==='auto')document.documentElement.removeAttribute('data-theme');else document.documentElement.dataset.theme=pref;$('theme-label').textContent=themeLabels[pref];$('theme').dataset.pref=pref;}
function cycleTheme(){const next=themes[(themes.indexOf($('theme').dataset.pref||'auto')+1)%3];applyTheme(next);store('bl-theme',next);toast('配色：'+themeLabels[next]);}

// ---------- counters ----------
let counterFrame;
function setCounters(values){
  cancelAnimationFrame(counterFrame);
  const els=Object.keys(values).map(id=>[$(id),values[id]]);
  const from=els.map(([el])=>Number(el.textContent.replace(/[^\d]/g,''))||0);
  const done=()=>els.forEach(([el,v])=>{el.textContent=v.toLocaleString();});
  if(reduceMotion||document.hidden||from.every((f,i)=>f===els[i][1])){done();return;}
  const start=performance.now(),duration=420;
  const step=now=>{const p=Math.min(1,(now-start)/duration),e=1-Math.pow(1-p,3);
    if(p>=1){done();return;}
    // Intermediate frames round toward the start so no counter shows its final value early;
    // all counters reach their true values together in done().
    els.forEach(([el,v],i)=>{const raw=from[i]+(v-from[i])*e;el.textContent=(v>=from[i]?Math.floor(raw):Math.ceil(raw)).toLocaleString();});counterFrame=requestAnimationFrame(step);};
  counterFrame=requestAnimationFrame(step);
}

// ---------- chart ----------
// Round axis ticks (1/2/5 x 10^n) so the scale reads at a glance.
function niceTicks(max,count=4){const raw=max/count,mag=10**Math.floor(Math.log10(raw||1)),step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=raw)||raw;
  const ticks=[];for(let v=0;v<=max+step*.001;v+=step)ticks.push(v);if(ticks[ticks.length-1]<max)ticks.push(ticks[ticks.length-1]+step);return ticks;}
const tickLabel=v=>v===0?'0':v>=100?Math.round(v).toLocaleString('zh-CN'):fmt(v);
function chart(){
  const field=$('metric').value,unit=metricUnits[field],groups=new Map();
  // Draw at the container's real width so labels keep their true size on narrow screens.
  const W=Math.max(320,($('chart').clientWidth||784)-24);
  const g=svg('svg',{viewBox:`0 0 ${W} 250`,role:'img','aria-label':'每组重复均值的中位数及最小最大范围'});
  // Imported runs come from other experiments; never pool them into baseline medians.
  const base=runs.filter(r=>r.kind==='baseline');
  for(const r of base){const key=r.engine+':'+r.concurrency;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r[field]);}
  const all=[...groups.values()].flat();
  if(!all.length){$('chart').replaceChildren(emptyState(runs.length?'当前筛选只有导入结果；图表只展示历史基线。':'没有匹配的结果。',true));compare(base,field);return;}
  const ticks=niceTicks(Math.max(...all)*1.05||1),top=ticks[ticks.length-1],x0=58,y0=200,h=170,w=W-x0-10,y=v=>y0-h*v/top;
  for(const v of ticks){const yy=y(v);g.append(svg('line',{x1:x0,x2:x0+w,y1:yy,y2:yy,class:'grid'}),svg('text',{x:x0-10,y:yy+3.5,'text-anchor':'end',class:'axis'},tickLabel(v)));}
  const cs=[...new Set(base.map(r=>r.concurrency))].sort((a,b)=>a-b),engines=['vllm','sglang'].filter(e=>base.some(r=>r.engine===e));
  const slot=w/cs.length,barW=Math.max(10,Math.min(26,slot/(engines.length*2.2))),step=barW*1.4;
  cs.forEach((c,i)=>{const center=x0+slot*(i+.5);g.append(svg('text',{x:center,y:228,'text-anchor':'middle',class:'xlabel'},'并发 '+c));
    engines.forEach((engine,j)=>{const values=groups.get(engine+':'+c);if(!values)return;
      const x=center+(j-(engines.length-1)/2)*step,mid=median(values),min=Math.min(...values),max=Math.max(...values);
      const isCurrent=current&&current.kind==='baseline'&&current.engine===engine&&current.concurrency===c;
      const bar=svg('rect',{x:x-barW/2,y:y(mid),width:barW,height:Math.max(1,y0-y(mid)),rx:Math.min(4,barW/4),class:`bar ${engine}${isCurrent?' current':''}`,tabindex:0,
        'aria-label':`${names[engine]} 并发${c}：中位数 ${fmt(mid)} ${unit}，范围 ${fmt(min)}–${fmt(max)}。按回车筛选到该组`});
      const show=e=>tip(e,`${names[engine]} · 并发 ${c}`,[['中位数',`${fmt(mid)} ${unit}`],['重复范围',`${fmt(min)} – ${fmt(max)}`],['重复次数',String(values.length)],['','点击筛选到这一组']]);
      bar.addEventListener('mousemove',show);bar.addEventListener('mouseleave',hideTip);
      const pick=()=>{hideTip();$('engine').value=engine;$('concurrency').value=String(c);refresh();toast(`已筛选：${names[engine]} · 并发 ${c}`);};
      bar.addEventListener('click',pick);bar.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick();}});
      g.append(bar);
      g.append(svg('line',{x1:x,x2:x,y1:y(min),y2:y(max),class:`whisker ${engine}`}));
      for(const value of [min,max])g.append(svg('line',{x1:x-5,x2:x+5,y1:y(value),y2:y(value),class:`whisker ${engine}`}));
    });});
  $('chart').replaceChildren(g);
  compare(base,field);
}
// Repeat range of the same configuration is the noise reference (an A/A-style check).
function compare(base,field){
  const target=$('compare'),cs=[...new Set(base.map(r=>r.concurrency))].sort((a,b)=>a-b);
  const pairs=cs.map(c=>[c,...['vllm','sglang'].map(e=>base.filter(r=>r.engine===e&&r.concurrency===c).map(r=>r[field]))]).filter(([,a,b])=>a.length&&b.length);
  if(!pairs.length){target.replaceChildren(emptyState('需要同一并发下同时有 vLLM 和 SGLang 的历史基线。',true));return;}
  const table=node('table',undefined,'compare-table'),head=node('tr');
  for(const h of ['并发','判断','比值 vLLM/SGLang','vLLM 中位 [范围]','SGLang 中位 [范围]'])head.append(node('th',h));table.append(head);
  const span=v=>`${fmt(median(v))} [${fmt(Math.min(...v))}–${fmt(Math.max(...v))}]`;
  for(const[c,a,b]of pairs){
    const separated=Math.max(...a)<Math.min(...b)||Math.max(...b)<Math.min(...a),tr=node('tr');tr.dataset.concurrency=c;
    const verdict=node('td',undefined,separated?'verdict separated':'verdict overlap');verdict.append(node('span',separated?'差异超出重复波动':'范围重叠 · 不判定快慢','pill'));
    tr.append(node('td','C'+c),verdict,node('td',(median(a)/median(b)).toFixed(2)),node('td',span(a)),node('td',span(b)));
    table.append(tr);
  }
  target.replaceChildren(table);
}

// ---------- runs table ----------
function runTitle(r){return r.kind==='imported'?`${names[r.engine]} · C${r.concurrency??'—'} · 导入`:`${names[r.engine]} · C${r.concurrency} · 第${r.repeat+1}次`;}
function renderTable(){
  $('runs').replaceChildren();
  if(!runs.length){const tr=node('tr'),td=node('td');td.colSpan=6;td.append(emptyState('没有符合条件的运行记录。',true));tr.append(td);$('runs').append(tr);}
  for(const r of runs){const tr=node('tr');tr.dataset.id=r.id;tr.classList.toggle('selected',r.id===selected);tr.onclick=()=>select(r.id);
    const first=node('td');first.append(node('span',names[r.engine],`engine-tag ${r.engine==='sglang'?'sglang-tag':''}`),document.createTextNode('C'+(r.concurrency??'—')));
    if(r.kind==='imported')first.append(node('span','导入','import-tag'));tr.append(first);
    for(const value of [r.kind==='imported'?(r.label||'—'):`#${r.repeat+1}`,`${fmt(r.mean_ttft_ms)} ms`,`${fmt(r.mean_tpot_ms)} ms`,fmt(r.output_tokens_per_s)])tr.append(node('td',value));
    const cell=node('td'),button=node('button','查看 →','run-link');button.type='button';button.setAttribute('aria-label',`查看 ${runTitle(r)}`);
    button.onclick=e=>{e.stopPropagation();select(r.id);};cell.append(button);tr.append(cell);$('runs').append(tr);
  }
  $('table-count').textContent=runs.length;
}
function move(step){if(!runs.length)return;const i=runs.findIndex(r=>r.id===selected),next=runs[Math.min(runs.length-1,Math.max(0,(i<0?0:i+step)))];
  if(next&&next.id!==selected){select(next.id);requestAnimationFrame(()=>document.querySelector(`#runs tr[data-id="${next.id}"]`)?.scrollIntoView({block:'nearest'}));}}

// ---------- request timeline ----------
// Gantt of request phases plus the in-flight step curve; client-side clock only.
function renderTimeline(r){
  const panel=$('timeline-panel'),rows=r.request_timing;
  if(!rows||rows[0].dispatch_ms===undefined){panel.hidden=true;return;}
  panel.hidden=false;$('timeline-title').textContent=runTitle(r);
  const t=r.timeline,span=t.span_ms||1,W=Math.max(320,($('timeline').clientWidth||1028)-28),left=48,right=14,top=10,curveH=70,gap=16,rowH=Math.max(3,Math.min(8,320/rows.length));
  const H=top+curveH+gap+rows.length*rowH+26,x=v=>left+(W-left-right)*v/span,g=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${rows.length}个请求的阶段时间线`});
  const events=rows.flatMap(q=>[[q.dispatch_ms,1],[q.end_ms,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const cap=Math.max(t.peak_in_flight,t.max_concurrency||0,1),y=v=>top+curveH-curveH*v/cap;let n=0;const pts=[`${x(0)},${y(0)}`];
  for(const[time,change]of events){pts.push(`${x(time)},${y(n)}`);n+=change;pts.push(`${x(time)},${y(n)}`);}
  g.append(svg('line',{x1:left,x2:W-right,y1:y(0),y2:y(0),class:'grid'}));
  g.append(svg('polygon',{points:[...pts,`${x(span)},${y(0)}`].join(' '),class:`inflight-area ${r.engine}`}));
  if(t.max_concurrency){g.append(svg('line',{x1:left,x2:W-right,y1:y(t.max_concurrency),y2:y(t.max_concurrency),class:'limit'}),svg('text',{x:left-8,y:y(t.max_concurrency)+3.5,'text-anchor':'end',class:'axis'},String(t.max_concurrency)));}
  g.append(svg('polyline',{points:pts.join(' '),class:`inflight ${r.engine}`}),svg('text',{x:left-8,y:y(0)+3.5,'text-anchor':'end',class:'axis'},'0'));
  const ordered=[...rows].sort((a,b)=>a.arrival_ms-b.arrival_ms||a.index-b.index),y0=top+curveH+gap;
  ordered.forEach((q,i)=>{const row=svg('g',{class:'req'}),yy=y0+i*rowH,h=Math.max(1.5,rowH-1);
    row.append(svg('rect',{x:left,y:yy,width:W-left-right,height:rowH,class:'hit'}));
    for(const[a,b,c]of[[q.arrival_ms,q.dispatch_ms,'seg wait'],[q.dispatch_ms,q.first_token_ms,'seg ttft'],[q.first_token_ms,q.end_ms,`seg decode ${r.engine}`]])
      if(b>a)row.append(svg('rect',{x:x(a),y:yy,width:Math.max(.5,x(b)-x(a)),height:h,rx:Math.min(1.5,h/2),class:c}));
    row.addEventListener('mousemove',e=>tip(e,`请求 #${q.index+1}`,[['到达',`${fmt(q.arrival_ms/1000)} s`],['客户端等待',`${fmt(q.client_queue_ms)} ms`],['首 token（TTFT）',`${fmt(q.ttft_ms)} ms`],['端到端',`${fmt(q.e2e_ms)} ms`]]));
    row.addEventListener('mouseleave',hideTip);g.append(row);});
  for(let i=0;i<=4;i++){const v=span*i/4;g.append(svg('text',{x:x(v),y:H-6,'text-anchor':i===0?'start':i===4?'end':'middle',class:'axis'},(v/1000).toFixed(1)+' s'));}
  $('timeline').replaceChildren(g);
  const waited=rows.filter(q=>q.client_queue_ms>1).length,maxWait=Math.max(...rows.map(q=>q.client_queue_ms));
  $('timeline-stats').textContent=`峰值同时在途 ${t.peak_in_flight}`+(t.max_concurrency?` / 客户端上限 ${t.max_concurrency}（${t.within_client_limit?'未超过上限':'超过上限，请检查原始记录'}）`:'')+` · 总时长 ${fmt(span/1000)} s · ${waited} 个请求在客户端等待超过 1 ms（最长 ${fmt(maxWait)} ms）`;
}

// ---------- detail ----------
function kv(parent,pairs){const dl=node('dl',undefined,'kv');for(const [key,value]of pairs)dl.append(node('dt',key),node('dd',value));parent.append(dl);}
function label(parent,text){parent.append(node('span',text,'detail-label'));}
function copyButton(text,message){const b=node('button','复制','copy');b.type='button';b.onclick=()=>copy(text,message);return b;}
function note(parent,text){parent.append(node('p',text,'tail-note'));}
const artifactTitles={result:'原始结果 JSON',metadata:'运行配置',validation:'校验记录',provenance:'导入溯源记录'};
async function select(id){
  selected=id;const sequence=++detailSequence;renderTable();
  try{const r=await get('/api/runs/'+encodeURIComponent(id));if(sequence!==detailSequence)return;
    current=r;$('detail-title').textContent=runTitle(r);
    const target=$('detail'),sub=node('p',undefined,'detail-sub');sub.append(document.createTextNode(r.id),copyButton(r.id,'已复制运行 ID'));target.replaceChildren(sub);
    const imported=r.kind==='imported';
    if(imported){const p=r.provenance;kv(target,[['状态',r.detail_level==='detailed'?'已导入 · 逐请求复核':'已导入 · 仅汇总'],['请求数',`${r.requests} / ${r.requests}`],['原文件',p.source_name],['导入时间',p.imported_utc.slice(0,19).replace('T',' ')+' UTC'],['工具记录日期',String(p.reported.date??'—')],['到达率',String(p.reported.request_rate??'—')]]);}
    else{const env=r.environment;kv(target,[['状态','已校验历史测量'],['请求数',`${r.requests} / ${r.requests}`],['模型版本',env.model_revision.slice(0,12)],['输入 / 输出',`${env.input_tokens} / ${env.output_tokens} tokens`],['GPU',env.gpu],['引擎版本',env.engine_version],['随机种子',String(env.seed)]]);}
    label(target,'端到端延迟 · 本次请求内分位数');const tails=node('div',undefined,'tails');
    for(const p of ['50','95','99']){const box=node('div');box.append(node('small','P'+p+' · ms'),node('strong',fmt(r.tails.latencies[p])));tails.append(box);}target.append(tails);
    note(target,`每次只有${r.requests}个请求，P99仅作描述，不代表线上尾延迟。客户端等待不等同服务端调度排队。`);
    if(r.request_timing){label(target,'逐请求 TTFT · 按原始序号');const mini=node('div',undefined,'mini-chart'),graph=svg('svg',{viewBox:'0 0 300 85',preserveAspectRatio:'none',role:'img','aria-label':`${r.request_timing.length}个请求的TTFT序列`}),max=Math.max(...r.request_timing.map(v=>v.ttft_ms))||1;
      const pts=r.request_timing.map((v,i)=>`${4+i*292/Math.max(1,r.request_timing.length-1)},${80-v.ttft_ms/max*70}`);
      graph.append(svg('polygon',{points:['4,82',...pts,'296,82'].join(' '),class:`area ${r.engine}`}),svg('polyline',{points:pts.join(' '),class:`spark ${r.engine}`,'vector-effect':'non-scaling-stroke'}));mini.append(graph);target.append(mini);}
    else note(target,'原文件未用 --save-detailed 保存，没有逐请求 TTFT 与错误记录。');
    if(imported){label(target,'导入核对');const list=node('ul',undefined,'check-list');for(const c of r.provenance.checks)list.append(node('li',c));target.append(list);
      for(const l of r.limitations)note(target,l);}
    else{const env=r.environment;label(target,'配置与证据');kv(target,[['模型快照',env.model_snapshot],['引擎提交',env.engine_commit.slice(0,12)],['负载', '有限批次 · 立即到达'],['Prefix cache','关闭']]);}
    const links=node('div',undefined,'download-links');for(const k of Object.keys(r.artifacts)){const a=node('a',artifactTitles[k]||k);a.href=`/api/runs/${encodeURIComponent(id)}/artifacts/${k}`;links.append(a);}
    const hash=node('p',undefined,'hash');hash.append(document.createTextNode('SHA256 · '+r.source_sha256),copyButton(r.source_sha256,'已复制 SHA256'));
    target.append(links,hash);renderTimeline(r);syncUrl();chart();error('');
  }catch(e){if(sequence!==detailSequence)return;$('detail').replaceChildren(emptyState('无法核对这条记录的原始文件。'));$('timeline-panel').hidden=true;error(e.message);}
}

// ---------- URL state, filters ----------
// Shareable view: filters, metric and the selected run live in the query string.
function syncUrl(){const q=new URLSearchParams(query());if($('metric').value!=='mean_ttft_ms')q.set('metric',$('metric').value);if(selected)q.set('run',selected);
  const s=q.toString();history.replaceState(null,'',s?'?'+s:location.pathname);}
function restoreUrl(){const q=new URLSearchParams(location.search);
  for(const id of ['engine','concurrency','source','metric']){const v=q.get(id);if(v!==null&&[...$(id).options].some(o=>o.value===v))$(id).value=v;}
  selected=q.get('run');}
async function copyLink(){syncUrl();const button=$('copy-link');
  if(await writeClipboard(location.href)){button.textContent='已复制链接 ✓';toast('链接已复制，可以直接发给导师');}else button.textContent='请复制地址栏链接';
  setTimeout(()=>{button.textContent='复制当前视图链接';},1800);}
function clearFilters(){for(const id of ['engine','concurrency','source'])$(id).value='';refresh();}
function markFilters(){for(const id of ['engine','concurrency','source'])$(id).classList.toggle('active',Boolean($(id).value));$('clear-filters').hidden=!query();}
function summary(data){const s=$('filter-summary');s.replaceChildren();
  if(query()&&overall){s.append('显示 ',node('b',String(data.total)),` / ${overall.total} 次运行 · ${data.requests.toLocaleString()} 条请求`);}
  else s.append('共 ',node('b',String(data.total)),` 次运行 · ${data.requests.toLocaleString()} 条请求`);}
async function refresh(){
  $('refresh').disabled=true;markFilters();
  try{const data=await get('/api/runs?'+query());runs=data.runs;
    // Filtered counts must not read as the whole dataset.
    if(!query())overall={total:data.total,requests:data.requests};
    else if(!overall){const all=await get('/api/runs');overall={total:all.total,requests:all.requests};}
    const filtered=Boolean(query())&&overall;
    setCounters({'run-count':data.total,'request-count':data.requests,'engine-count':new Set(runs.map(r=>r.engine)).size});
    $('run-note').textContent=filtered?`当前筛选 · 全部 ${overall.total} 次`:'每一行对应一次原始运行';
    $('request-note').textContent=filtered?`当前筛选 · 全部 ${overall.requests.toLocaleString()} 条`:'失败或不完整数据不计入索引';
    // Imported files carry no verified hardware/version, so never label them "real GPU".
    const kinds=new Set(runs.map(r=>r.kind)),mixed=kinds.size>1,onlyImported=kinds.size===1&&kinds.has('imported');
    $('source-word').textContent=mixed?'基线 + 导入':onlyImported?'导入结果':'真实 GPU';
    $('source-note').textContent=mixed||onlyImported?'导入结果的硬件与版本未核实':'本地实验室 · 有限请求批次';
    $('export').href='/api/export.csv?'+query();$('report').href='/api/report.md?'+query();summary(data);chart();renderTable();error('');
    if(runs.length)await select(runs.some(r=>r.id===selected)?selected:runs[0].id);
    else{selected=current=null;$('detail').replaceChildren(emptyState('没有匹配记录。',true));$('detail-title').textContent='选择运行记录';$('timeline-panel').hidden=true;syncUrl();}
  }catch(e){error(e.message);}finally{$('refresh').disabled=false;}
}

// ---------- wiring ----------
applyTheme(themes.includes(recall('bl-theme'))?recall('bl-theme'):'auto');
if(recall('bl-guide')!=='closed')$('guide').hidden=false;
$('guide-close').onclick=()=>{$('guide').hidden=true;store('bl-guide','closed');};
for(const id of ['engine','concurrency','source'])$(id).addEventListener('change',refresh);
$('metric').addEventListener('change',()=>{chart();syncUrl();});
$('refresh').onclick=async()=>{await refresh();toast('列表已刷新');};
$('copy-link').onclick=copyLink;$('clear-filters').onclick=clearFilters;$('theme').onclick=cycleTheme;
$('help').onclick=()=>$('shortcuts').showModal();
addEventListener('scroll',hideTip,{passive:true});
// Re-draw charts when their width changes (window resize, sidebar collapse, rotation).
let resizeTimer,lastWidths='';
new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{
  const widths=$('chart').clientWidth+':'+$('timeline').clientWidth;if(widths===lastWidths)return;lastWidths=widths;
  if(runs.length)chart();if(current&&!$('timeline-panel').hidden)renderTimeline(current);},120);}).observe(document.querySelector('main'));
document.addEventListener('keydown',e=>{
  if(e.metaKey||e.ctrlKey||e.altKey||e.target.closest('input,select,textarea')||$('shortcuts').open)return;
  // Arrow keys keep scrolling the page unless focus is inside the runs table.
  const inTable=Boolean(e.target.closest&&e.target.closest('#runs-panel'));
  if(e.key==='j'||(inTable&&e.key==='ArrowDown')){e.preventDefault();move(1);}
  else if(e.key==='k'||(inTable&&e.key==='ArrowUp')){e.preventDefault();move(-1);}
  else if(e.key==='c')copyLink();
  else if(e.key==='t')cycleTheme();
  else if(e.key==='?'){e.preventDefault();$('shortcuts').showModal();}
  else if(e.key==='Escape'&&query())clearFilters();
});
restoreUrl();refresh();
