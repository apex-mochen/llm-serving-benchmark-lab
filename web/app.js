'use strict';
const $ = id => document.getElementById(id);
let runs = [], selected = null, detailSequence = 0;
const colors = {vllm:'#2366cc',sglang:'#008e83'};
const names = {vllm:'vLLM',sglang:'SGLang'};
const fmt = value => Number(value).toLocaleString('zh-CN',{minimumFractionDigits:1,maximumFractionDigits:2});
function node(tag, text, cls) { const e = document.createElement(tag); if(text !== undefined)e.textContent=text; if(cls)e.className=cls;return e; }
function svg(tag, attributes={}, text) {const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attributes))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function median(values) {const v=[...values].sort((a,b)=>a-b),i=Math.floor(v.length/2);return v.length%2?v[i]:(v[i-1]+v[i])/2;}
function query() {const q=new URLSearchParams();if($('engine').value)q.set('engine',$('engine').value);if($('concurrency').value)q.set('concurrency',$('concurrency').value);return q.toString();}
async function get(url){const r=await fetch(url);if(!r.ok){const e=await r.json();throw new Error(e.detail||'数据加载失败');}return r.json();}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
function chart(){
  const field=$('metric').value, chart=svg('svg',{viewBox:'0 0 760 245',role:'img','aria-label':'每组重复均值的中位数及最小最大范围'}),groups=new Map();
  for(const r of runs){const key=r.engine+':'+r.concurrency;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r[field]);}
  const all=[...groups.values()].flat();if(!all.length){$('chart').replaceChildren(node('p','没有匹配的结果。','empty'));return;}
  const top=Math.max(...all)*1.15||1, x0=65,y0=198,h=166,w=630;
  for(let i=0;i<=4;i++){const y=y0-h*i/4;chart.append(svg('line',{x1:x0,x2:x0+w,y1:y,y2:y,stroke:'#e8eef4','stroke-dasharray':'3 4'}));chart.append(svg('text',{x:x0-10,y:y+3,'text-anchor':'end',fill:'#8393a5','font-size':10},fmt(top*i/4)));}
  const cs=[...new Set(runs.map(r=>r.concurrency))].sort((a,b)=>a-b),engines=['vllm','sglang'].filter(e=>runs.some(r=>r.engine===e));
  cs.forEach((c,i)=>{const center=x0+w*(i+.5)/cs.length;chart.append(svg('text',{x:center,y:225,'text-anchor':'middle',fill:'#718297','font-size':11},'并发 '+c));
    engines.forEach((engine,j)=>{const values=groups.get(engine+':'+c);if(!values)return;const x=center+(j-(engines.length-1)/2)*31,mean=median(values),min=Math.min(...values),max=Math.max(...values),y=v=>y0-h*v/top;
      chart.append(svg('rect',{x:x-10,y:y(mean),width:20,height:y0-y(mean),rx:3,fill:colors[engine],opacity:.85}));
      chart.append(svg('line',{x1:x,x2:x,y1:y(min),y2:y(max),stroke:colors[engine],'stroke-width':1.7}));
      for(const value of [min,max])chart.append(svg('line',{x1:x-5,x2:x+5,y1:y(value),y2:y(value),stroke:colors[engine],'stroke-width':1.7}));
      chart.append(svg('title',{},`${names[engine]} 并发${c}：中位数${fmt(mean)}，范围${fmt(min)}–${fmt(max)}`));
    });});
  $('chart').replaceChildren(chart);
}
function renderTable(){
  $('runs').replaceChildren();
  for(const r of runs){const tr=node('tr');tr.dataset.id=r.id;tr.classList.toggle('selected',r.id===selected);
    const first=node('td');first.append(node('span',names[r.engine],`engine-tag ${r.engine==='sglang'?'sglang-tag':''}`),document.createTextNode('C'+r.concurrency));tr.append(first);
    for(const value of [`#${r.repeat+1}`,`${fmt(r.mean_ttft_ms)} ms`,`${fmt(r.mean_tpot_ms)} ms`,fmt(r.output_tokens_per_s)])tr.append(node('td',value));
    const cell=node('td'),button=node('button','查看 →','run-link');button.setAttribute('aria-label',`查看 ${names[r.engine]} 并发${r.concurrency} 第${r.repeat+1}次运行`);button.onclick=()=>select(r.id);cell.append(button);tr.append(cell);$('runs').append(tr);
  }
  $('table-count').textContent=runs.length;
}
function kv(parent,pairs){const dl=node('dl',undefined,'kv');for(const [key,value]of pairs)dl.append(node('dt',key),node('dd',value));parent.append(dl);}
function label(parent,text){parent.append(node('span',text,'detail-label'));}
async function select(id){
  selected=id;const sequence=++detailSequence;renderTable();
  try{const r=await get('/api/runs/'+encodeURIComponent(id));if(sequence!==detailSequence)return;
    $('detail-title').textContent=`${names[r.engine]} · C${r.concurrency} · 第${r.repeat+1}次`;
    const target=$('detail');target.replaceChildren(node('p',r.id,'detail-sub'));
    const env=r.environment;
    kv(target,[['状态','已校验历史测量'],['请求数',`${r.requests} / ${r.requests}`],['模型版本',env.model_revision.slice(0,12)],['输入 / 输出',`${env.input_tokens} / ${env.output_tokens} tokens`],['GPU',env.gpu],['引擎版本',env.engine_version],['随机种子',String(env.seed)]]);
    label(target,'端到端延迟 · 本次请求内分位数');const tails=node('div',undefined,'tails');
    for(const p of ['50','95','99']){const box=node('div');box.append(node('small','P'+p+' · ms'),node('strong',fmt(r.tails.latencies[p])));tails.append(box);}target.append(tails);
    target.append(node('p','每次只有64个请求，P99仅作描述，不代表线上尾延迟。客户端等待不等同服务端调度排队。','tail-note'));
    label(target,'逐请求 TTFT · 按原始序号');const mini=node('div',undefined,'mini-chart'),graph=svg('svg',{viewBox:'0 0 300 85',role:'img','aria-label':'64个请求的TTFT序列'}),max=Math.max(...r.request_timing.map(v=>v.ttft_ms))||1;
    const points=r.request_timing.map((v,i)=>`${8+i*284/Math.max(1,r.request_timing.length-1)},${74-v.ttft_ms/max*62}`).join(' ');graph.append(svg('polyline',{points,fill:'none',stroke:colors[r.engine],'stroke-width':1.5}));mini.append(graph);target.append(mini);
    label(target,'配置与证据');kv(target,[['模型快照',env.model_snapshot],['引擎提交',env.engine_commit.slice(0,12)],['负载', '有限批次 · 立即到达'],['Prefix cache','关闭']]);
    const links=node('div',undefined,'download-links');for(const[k,title]of Object.entries({result:'原始结果 JSON',metadata:'运行配置',validation:'校验记录'})){const a=node('a',title);a.href=`/api/runs/${encodeURIComponent(id)}/artifacts/${k}`;links.append(a);}target.append(links,node('p','SHA256 · '+r.source_sha256,'hash'));error('');
  }catch(e){if(sequence!==detailSequence)return;$('detail').replaceChildren(node('p','无法核对这条记录的原始文件。','muted'));error(e.message);}
}
async function refresh(){
  $('refresh').disabled=true;
  try{const data=await get('/api/runs?'+query());runs=data.runs;$('run-count').textContent=data.total;$('request-count').textContent=data.requests.toLocaleString();$('engine-count').textContent=new Set(runs.map(r=>r.engine)).size;$('export').href='/api/export.csv?'+query();chart();renderTable();error('');
    if(runs.length)await select(runs.some(r=>r.id===selected)?selected:runs[0].id);else{$('detail').replaceChildren(node('p','没有匹配记录。','muted'));$('detail-title').textContent='选择运行记录';}
  }catch(e){error(e.message);}finally{$('refresh').disabled=false;}
}
for(const id of ['engine','concurrency'])$(id).addEventListener('change',refresh);
$('metric').addEventListener('change',chart);$('refresh').onclick=refresh;refresh();
