'use strict';
// The horizontal axis is capture time. Packet glyph width is not airtime.
let scope={start:0,span:60,follow:true,source:null,marks:[]}, historyEvents=[],historySpeed=[],historyFetch=0;
// Stable message-family colors shared by waveform, legend and packet list.
const packetFamilies=[
 {id:'topology',label:'Topology',color:'#58c7ff',kinds:[0,1,2,3]},
 {id:'discovery',label:'Autoconfig search / response',color:'#ffb454',kinds:[7,8]},
 {id:'wsc',label:'WSC / renew',color:'#ed83d7',kinds:[9,10]},
 {id:'capability',label:'Capabilities',color:'#ad9bff',kinds:[0x8001,0x8002,0x8009,0x800a,0x8027,0x8028]},
 {id:'metrics',label:'Metrics / measurements',color:'#56d6a0',kinds:[5,6,0x800b,0x800c,0x800d,0x800e,0x800f,0x8010,0x8011,0x8012]},
 {id:'steering',label:'Steering',color:'#ff787f',kinds:[0x8014,0x8015,0x8016,0x8017,0x8019,0x801a]},
 {id:'ack',label:'ACK',color:'#e3db8b',kinds:[0x8000]},
 {id:'other',label:'Other',color:'#92a5ba',kinds:[]}
];
function packetFamily(kind){return packetFamilies.find(f=>f.kinds.includes(kind))||packetFamilies.at(-1);}
function scopeDuration(seconds){
 const unit=seconds>=1?['s',1]:seconds>=.001?['ms',1000]:['µs',1000000];
 return Number((seconds*unit[1]).toPrecision(6))+' '+unit[0];
}
function renderScope(){
 const svg=$('scopeGraph');if(!svg)return;
 const packets=visibleEvents().slice().sort((a,b)=>a.time-b.time),last=packets.at(-1)?.time||Date.now()/1000;
 if(scope.source!==source){scope.source=source;scope.follow=true;scope.marks=[];}
 if(scope.follow)scope.start=last-scope.span*.95;
 const x=t=>115+(t-scope.start)/scope.span*865,division=scope.span/5;
 $('scopeScale').textContent=scopeDuration(division)+' / div';
 $('scopeScaleDetail').textContent='5 major divisions · minor tick '+scopeDuration(division/5)+' · window '+scopeDuration(scope.span);
 $('scopeLegend').innerHTML=packetFamilies.map(f=>`<span class="scope-key family-${f.id}"><i></i>${esc(f.label)}</span>`).join('');
 let body='<defs><clipPath id="scopeClip"><rect x="115" y="25" width="865" height="196"/></clipPath></defs>';
 for(let i=0;i<=25;i++){
  const xx=115+i*865/25,major=i%5===0,t=scope.start+i*scope.span/25;
  body+=`<line x1="${xx}" x2="${xx}" y1="35" y2="220" stroke="${major?'#3b536a':'#213347'}" ${major?'':'stroke-dasharray="2 5"'}/>`;
  if(major){const label=scope.span<.01?'+'+scopeDuration(i*scope.span/25):when(t)+(scope.span<10?'.'+String(new Date(t*1000).getMilliseconds()).padStart(3,'0'):'');body+=`<text class="scope-label" x="${xx}" y="245" text-anchor="${i===25?'end':'middle'}">${esc(label)}</text>`;}
 }
 const lanes={TX:80,RX:150,unknown:205};for(const [label,y]of Object.entries(lanes))body+=`<text class="scope-label" x="8" y="${y+4}">${label==='TX'?'Controller TX':label==='RX'?'Agent RX':'Other'}</text><line x1="115" x2="980" y1="${y}" y2="${y}" stroke="#486176"/>`;
 const visible=packets.filter(e=>e.time>=scope.start&&e.time<=scope.start+scope.span);
 body+='<g clip-path="url(#scopeClip)">';
 // MID links remain hints; message colors do not assert a response relationship.
 const requests=new Map();for(const e of packets){if(e.direction==='TX')requests.set(e.packet.mid,e);else{const tx=requests.get(e.packet.mid);if(tx&&e.time-tx.time<30&&e.time>=scope.start&&tx.time<=scope.start+scope.span){const a=Math.max(115,x(tx.time)),b=Math.min(980,x(e.time));body+=`<path d="M${a},80 L${b},150" stroke="${e.command_id&&e.command_id===tx.command_id?'#a48cf3':'#43586a'}" stroke-dasharray="3 4" fill="none"><title>Same MID within 30 seconds; a correlation aid, not proof of a response</title></path>`;requests.delete(e.packet.mid);}}}
 for(const e of visible){
  const xx=x(e.time),y=lanes[e.direction]||205,family=packetFamily(e.packet.kind),chosen=e.id===selected;
  body+=`<g class="scope-pulse family-${family.id}${chosen?' is-selected':''}" data-pulse="${esc(e.id)}" tabindex="0" role="button" aria-label="${esc(e.packet.name)} MID ${e.packet.mid}"><title>${esc(e.packet.name)} · ${hex(e.packet.mid)} · ${new Date(e.time*1000).toISOString()} · ${e.packet.length} captured bytes · fixed-width glyph, not packet duration</title><rect x="${xx-5}" y="${y-25}" width="18" height="32" fill="transparent"/>${chosen?`<rect x="${xx-3}" y="${y-24}" width="14" height="28" rx="3" fill="none" stroke="#fff" stroke-width="1.5"/>`:''}<path class="packet-step" d="M${xx-4},${y} H${xx} V${y-20} H${xx+6} V${y} H${xx+10}" stroke="${family.color}" stroke-width="2" stroke-linejoin="round" fill="none"/><rect x="${xx}" y="${y-20}" width="6" height="20" fill="${family.color}" fill-opacity=".16"/></g>`;
 }
 scope.marks.forEach((m,i)=>{if(m>=scope.start&&m<=scope.start+scope.span)body+=`<line x1="${x(m)}" x2="${x(m)}" y1="25" y2="220" stroke="#f0a6ff" stroke-dasharray="4 3"/><text x="${x(m)+4}" y="34" fill="#f0a6ff" font-size="11">${i?'B':'A'}</text>`;});
 body+='</g>';svg.innerHTML=body;
 $('scopeDelta').textContent=scope.marks.length===2?'A ↔ B  '+scopeDuration(Math.abs(scope.marks[1]-scope.marks[0])):'Shift-click two packets for Δt';
 $('scopeStatus').textContent=`${visible.length} pulses in ${scope.span.toFixed(3)} s · ${scope.follow?'Following latest':'Panned / frozen window'} · ${packets.length} loaded packets (live buffer ≤20,000). ${scope.marks.length===2?'Δt = '+(Math.abs(scope.marks[1]-scope.marks[0])*1000).toFixed(3)+' ms':''} Window start ${new Date(scope.start*1000).toLocaleString()}. Browser-local time; glyph width is decorative, not airtime.`;
}
function scopeZoom(factor,fraction=.5){const anchor=scope.start+scope.span*fraction;scope.span=Math.min(86400,Math.max(.001,scope.span*factor));scope.start=anchor-scope.span*fraction;scope.follow=false;renderScope();}
const scopeSvg=$('scopeGraph');let scopeDrag=null;
scopeSvg.addEventListener('wheel',e=>{e.preventDefault();const r=scopeSvg.getBoundingClientRect();scopeZoom(e.deltaY>0?1.25:.8,Math.max(0,Math.min(1,((e.clientX-r.left)/r.width*1000-115)/865)));},{passive:false});
scopeSvg.addEventListener('pointerdown',e=>{scopeDrag={x:e.clientX,start:scope.start,moved:false};});
scopeSvg.addEventListener('pointermove',e=>{if(!scopeDrag)return;const dx=e.clientX-scopeDrag.x;if(Math.abs(dx)>3){scopeDrag.moved=true;scopeSvg.setPointerCapture(e.pointerId);}if(scopeDrag.moved){scope.follow=false;scope.start=scopeDrag.start-dx/scopeSvg.getBoundingClientRect().width*1000/865*scope.span;renderScope();}});
scopeSvg.addEventListener('pointerup',()=>{setTimeout(()=>scopeDrag=null,0);});scopeSvg.addEventListener('pointercancel',()=>scopeDrag=null);
function choosePulse(e){if(scopeDrag?.moved)return;const el=e.target.closest('[data-pulse]');if(!el)return;const packet=events.find(x=>x.id===el.dataset.pulse);if(!packet)return;if(e.shiftKey){scope.marks.push(packet.time);scope.marks=scope.marks.slice(-2);}inspect(packet);}
scopeSvg.addEventListener('click',choosePulse);scopeSvg.addEventListener('keydown',e=>{if(e.key==='Enter')choosePulse(e);else if(e.key==='+'||e.key==='=')scopeZoom(.5);else if(e.key==='-')scopeZoom(2);else if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();scope.follow=false;scope.start+=scope.span*(e.key==='ArrowLeft'?-.2:.2);renderScope();}});
$('scopeTimebase').onchange=e=>{if(!e.target.value)return;const center=scope.start+scope.span/2;scope.span=Number(e.target.value)*5;scope.start=center-scope.span/2;scope.follow=false;renderScope();e.target.value='';};
$('scopeIn').onclick=()=>scopeZoom(.5);$('scopeOut').onclick=()=>scopeZoom(2);$('scopeLive').onclick=()=>{scope.follow=true;renderScope();};$('scopeFit').onclick=()=>{const p=visibleEvents();if(!p.length)return;const min=Math.min(...p.map(e=>e.time)),max=Math.max(...p.map(e=>e.time));scope.span=Math.max(.01,(max-min)*1.1);scope.start=min-scope.span*.05;scope.follow=false;renderScope();};
function options(id,items){const el=$(id),old=el.value,html=items.map(([value,label])=>`<option value="${esc(value)}">${esc(label)}</option>`).join('');if(el.innerHTML!==html){el.innerHTML=html;if(items.some(x=>x[0]===old))el.value=old;}}
const lessons=[
 ['topology','Discover the agent','Send Topology Query (0x0002). Inspect Device Information, Operational BSS (0x83) and Associated Clients (0x84), when reported. A 30-second timeout means no matching reply, not unsupported.'],
 ['capabilities','Read radio capabilities','Inspect AP Radio Basic Capabilities (0x85): radio IDs, supported operating classes and excluded channels. Capability is not current configuration.'],
 ['sta_metrics','Measure the current client link','Select a current station. Inspect Associated STA Link Metrics (0x96), measurement age and RCPI. This is AP receive power, not client-measured RSSI.'],
 ['beacon_metrics','Ask what the client hears','A beacon metrics request asks for client observations; support and refusal depend on the client and agent. Preserve the raw report and distinguish it from AP RCPI.'],
 ['steer','Attempt a supervised band move','Use a fresh source association and a valid target channel. Inspect Steering Request TLV 0x9b, BTM Report 0x9c, then fresh topology. ACK alone is not a roam.']
];
function renderExperiments(){
 const views=state.client_telemetry||{},bsses=state.operational_bss||[];
 options('experimentClient',Object.entries(views).map(([mac,v])=>[mac,`${v.identity?.label||'Client'} · ${mac}${v.stale?' · stale':''}`]));
 const station=$('experimentClient').value,current=views[station];
 options('experimentTarget',bsses.filter(b=>b.bssid!==current?.bssid).map(b=>[b.bssid,`${b.ssid} · ${b.bssid}`]));
 $('steerAdvice').textContent=current?`Current BSSID ${current.bssid}. ${current.stale?'Measurements or association are stale; refresh topology and metrics before steering.':'Review target SSID/security and client band support before sending.'}`:'No client currently reported. Connect a phone or laptop and query topology.';
 $('prepareSteer').disabled=!current||source!=='live';
 $('steerResults').innerHTML=results.filter(r=>r.steering).slice(0,8).map(r=>`<div class="experiment-step"><strong>${esc(r.steering.station)}</strong> · ${esc(r.status)}<br>BTM status: ${esc(r.steering.btm_status_code??'not reported')} · Outcome: ${esc(r.steering.outcome)}<br><small>${esc(r.steering.source_bssid)} → ${esc(r.steering.target_bssid)}</small></div>`).join('')||'<p class="muted">No tracked steering experiment yet. Pending outcomes expire after 120 seconds; controller restart ends in-memory tracking.</p>';
 $('guidedExperiments').innerHTML=lessons.filter(l=>boot.catalog.some(c=>c.id===l[0])).map(([id,title,text])=>`<div class="experiment-step"><h3>${esc(title)}</h3><p>${esc(text)}</p><button class="button" data-guide="${id}">Prepare & inspect TLVs</button></div>`).join('');
 $('optimizerAdvice').innerHTML=(state.optimizer?.clients||[]).map(c=>`<p><code>${esc(c.station)}</code> · ${esc(c.status)}: ${esc(c.reason)}</p>`).join('')||'<p>No current client evidence to assess.</p>';
 $('optimizerAdvice').innerHTML+=`<p class="muted">${esc(state.optimizer?.next_requirement||'Waiting for controller state')}</p><p class="muted">Policy: weak signal below −72 dBm; target gain ≥8 dB; association dwell ≥120 s; cooldown 300 s. Candidate power must be fresh, compatible and comparable across receivers/bands.</p>`;
 const six=Object.values(state.observations||{}).filter(o=>o.type===0x85&&o.fields.operating_classes?.some(c=>c.class>=131&&c.class<=137));
 $('onboardingEvidence').innerHTML=`<p>Onboarding: <strong>${state.onboarding_paused?'paused':'active'}</strong> · 6 GHz status: ${esc(state.six_ghz_status||'unknown')}</p>`+six.map(o=>{const r=state.radios?.[o.fields.radio],bs=bsses.filter(b=>b.radio===o.fields.radio);return `<p>Radio <code>${esc(o.fields.radio)}</code>: advertised · 6 GHz M1/M2 state: ${r?.rf_bands===8?'recorded by controller':'not recorded'} · SSID ${esc(bs.map(b=>b.ssid).join(', ')||'none reported')}</p>`;}).join('')+'<p class="muted">A manual BSS does not confirm controller provisioning. Next: record exact hardware/firmware from the extender UI, audit discovery capability TLVs, and compare with a compatible commercial controller. Do not infer a firmware defect from missing M1 alone.</p>';
 if(state.onboarding_evidence)$('onboardingEvidence').innerHTML+='<details><summary>Discovery and M1 evidence since '+esc(when(state.onboarding_evidence.since))+'</summary><div class="tree">'+tree(state.onboarding_evidence)+'</div></details>';
 const names=new Set(Object.keys(views));for(const e of historyEvents){Object.keys(e.clients||{}).forEach(m=>names.add(m));if(e.station)names.add(e.station);}
 options('historyClient',[...names].map(m=>[m,`${views[m]?.identity?.label||'Client'} · ${m}`]));renderClientHistory();
 if(Date.now()-historyFetch>10000){historyFetch=Date.now();Promise.all([api('/api/history'),api('/api/speed')]).then(([d,s])=>{historyEvents=d.events||[];historySpeed=s.results||[];if(activeTab==='experiments')renderExperiments();}).catch(e=>toast(e.message,true));}
}
$('experimentClient').onchange=renderExperiments;$('historyClient').onchange=renderClientHistory;
$('prepareSteer').onclick=()=>{const mac=$('experimentClient').value,v=state.client_telemetry?.[mac],b=(state.operational_bss||[]).find(b=>b.bssid===$('experimentTarget').value);if(!v||!b)return;const op=Object.values(state.observations||{}).find(o=>o.type===0x8f&&o.fields.radio===b.radio&&Date.now()/1000-o.time<90)?.fields.channels?.[0];tab('studio');selectCommand('steer',{station:mac,bssid:v.bssid,target_bssid:b.bssid,opclass:op?.operating_class||'',channel:op?.channel||''});toast(op?'Review the target and preview before sending.':'Target channel is not freshly reported; enter a verified operating class and channel.');};
$('guidedExperiments').onclick=e=>{const b=e.target.closest('[data-guide]');if(!b)return;const station=$('experimentClient').value;tab('studio');selectCommand(b.dataset.guide,station?{station}:{});};
function renderClientHistory(){
 const mac=$('historyClient').value,rows=historyEvents.filter(e=>e.clients?.[mac]),marks=historyEvents.filter(e=>e.station===mac),out=$('clientHistory');
 if(!rows.length){out.innerHTML='<p class="muted">No retained samples for this client yet. Samples are collected every 15 seconds.</p>';return;}
 const tests=historySpeed.filter(r=>r.mac===mac);
 const first=rows[0].time,last=rows.at(-1).time,span=Math.max(1,last-first),x=t=>60+(t-first)/span*900;
 let svg='<svg class="history-plot" viewBox="0 0 1000 240" role="img" aria-label="Client AP receive power over capture time">';for(const db of [-100,-80,-60,-40]){let y=210-(db+110)*2;svg+=`<line x1="60" x2="960" y1="${y}" y2="${y}" stroke="#d3dfe8"/><text x="5" y="${y}">${db} dBm</text>`;}
 let previous=null;for(const e of rows){const v=e.clients[mac],valid=!v.stale&&v.dbm!==null&&!v.bound;if(valid){const xx=x(e.time),yy=210-(v.dbm+110)*2;if(previous&&e.time-previous.time<=30&&previous.bssid===v.bssid)svg+=`<path d="M${x(previous.time)},${210-(previous.dbm+110)*2} L${xx},${yy}" stroke="#008c91" fill="none"/>`;svg+=`<circle cx="${xx}" cy="${yy}" r="3" fill="#008c91"><title>${esc(when(e.time))}: ${v.dbm} dBm · ${esc(v.bssid)}</title></circle>`;previous={time:e.time,...v};}else previous=null;}
 let prior=null;for(const e of rows){const v=e.clients[mac];if(!v.stale){if(prior&&prior!==v.bssid)svg+=`<line x1="${x(e.time)}" x2="${x(e.time)}" y1="25" y2="210" stroke="#4377b9" stroke-dasharray="6 3"><title>Association report changed: ${esc(prior)} → ${esc(v.bssid)}</title></line>`;prior=v.bssid;}}
 for(const t of tests)if(t.finished_at>=first&&t.finished_at<=last)svg+=`<circle cx="${x(t.finished_at)}" cy="18" r="6" fill="#b67628"><title>Speed test: ${esc(t.download?.mbps??'?')} / ${esc(t.upload?.mbps??'?')} Mbps</title></circle>`;
 for(const e of marks)if(e.time>=first&&e.time<=last)svg+=`<line x1="${x(e.time)}" x2="${x(e.time)}" y1="25" y2="210" stroke="#bd6cbf" stroke-dasharray="3 3"><title>${esc(e.event)} ${esc(e.outcome||'')}</title></line>`;
 svg+=`<text x="60" y="233">${esc(when(first))}</text><text x="880" y="233">${esc(when(last))}</text></svg>`;
 let rateSvg='<svg class="history-plot" viewBox="0 0 1000 180" role="img" aria-label="Estimated PHY rates over time">';
 const maxRate=Math.max(1,...rows.flatMap(e=>[e.clients[mac].downlink_mbps||0,e.clients[mac].uplink_mbps||0]));
 rateSvg+=`<text x="60" y="18">Estimated PHY: downlink (blue), uplink (orange) · top ${maxRate} Mbps</text>`;
 for(const [key,color] of [['downlink_mbps','#4377b9'],['uplink_mbps','#bd742e']]){let prev=null;for(const e of rows){const v=e.clients[mac],rate=v[key];if(v.stale||!Number.isFinite(rate)||rate<=0){prev=null;continue;}const yy=145-rate/maxRate*110;if(prev&&e.time-prev.time<=30&&prev.bssid===v.bssid)rateSvg+=`<path d="M${x(prev.time)},${prev.y} L${x(e.time)},${yy}" stroke="${color}" fill="none"/>`;rateSvg+=`<circle cx="${x(e.time)}" cy="${yy}" r="2" fill="${color}"><title>${key}: ${rate} Mbps at ${esc(when(e.time))}</title></circle>`;prev={time:e.time,y:yy,bssid:v.bssid};}}
 rateSvg+='</svg>';
 const speeds=tests.map(t=>`<p>Speed test ${esc(when(t.finished_at))}: ${esc(t.status)} · download ${esc(t.download?.mbps??'?')} Mbps / upload ${esc(t.upload?.mbps??'?')} Mbps · HTTP latency ${esc(t.http_latency_ms??'?')} ms</p>`).join('');
 out.innerHTML=svg+rateSvg+speeds+'<table class="history-table"><thead><tr><th>Time</th><th>Band / BSSID</th><th>AP signal</th><th>Estimated PHY ↓ / ↑</th></tr></thead><tbody>'+rows.slice(-80).reverse().map(e=>{const v=e.clients[mac],b=e.bss?.find(b=>b.bssid===v.bssid),rf=e.radios?.[b?.radio],band=({1:'2.4 GHz',2:'5 GHz',8:'6 GHz'})[rf]||'Band unknown';return `<tr><td>${esc(when(e.time))}</td><td>${esc(band)} · ${esc(v.bssid)}</td><td>${v.stale?'stale':v.dbm===null?'unknown':(v.bound==='at_most'?'≤':v.bound==='at_least'?'≥':'')+v.dbm+' dBm'}</td><td>${v.downlink_mbps??'?'} / ${v.uplink_mbps??'?'} Mbps</td></tr>`;}).join('')+'</tbody></table>'+marks.slice(-15).map(e=>`<p>${esc(when(e.time))} · ${esc(e.event)} · ${esc(e.outcome||('BTM status '+(e.btm_status_code??'pending')))}</p>`).join('');
}
