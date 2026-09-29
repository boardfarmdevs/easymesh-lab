'use strict';
// Original SVG implementation, inspired by the OpenSync lab's spring topology.
// Positions are presentation only: there are no protocol side effects from dragging.
let topologyNodes=new Map(), topologySelection='agent', topologySignature='';
const mesh={links:[],view:{x:0,y:0,k:1},drag:null,energy:0,paused:matchMedia('(prefers-reduced-motion: reduce)').matches,raf:0,settleUntil:0};
const meshColors={wired:'#a9bed1',membership:'#65778e','5 GHz':'#9aa5ff','2.4 GHz':'#ffc16c','6 GHz':'#58d6b4',unknown:'#9badbd'};
function topologyAge(t){return t?Math.max(0,Math.floor(Date.now()/1000-t))+'s ago':'not received';}
function meshBand(id,obs){
 const classes=obs.find(x=>x.type===0x85&&x.fields.radio===id)?.fields.operating_classes?.map(x=>x.class)||[];
 return classes.some(x=>x>=131&&x<=137)?'6 GHz':state.radios?.[id]?.rf_bands===2||classes.some(x=>x>=115&&x<=130)?'5 GHz':state.radios?.[id]?.rf_bands===1||classes.some(x=>x>=81&&x<=84)?'2.4 GHz':'unknown';
}
// Global operating class widths (IEEE 802.11 Annex E / hostap).
// Capabilities and channel preferences are deliberately not current-channel evidence.
function meshChannel(id,obs){
 const local=(state.managed_radio_observations||[]).filter(x=>state.operational_bss?.some(b=>b.radio===id&&b.bssid===x.bssid)).sort((a,b)=>b.time-a.time)[0];
 if(local&&Date.now()/1000-local.time<30)return {label:`Ch ${local.channel} · ${local.width_mhz} MHz`,channels:[local],stale:false,reported_at:new Date(local.time*1000).toLocaleString(),evidence:'Managed USB client: iw dev wlan0 info + associated BSSID',note:'Observed client interface channel and width; not a 1905 Operating Channel Report.'};
 const report=obs.filter(x=>x.type===0x8f&&x.fields.radio===id).sort((a,b)=>b.time-a.time)[0];
 const widths={81:20,82:20,83:40,84:40,115:20,116:40,117:40,118:20,119:40,120:40,121:20,122:40,123:40,124:20,125:20,126:40,127:40,128:80,129:160,130:'80+80',131:20,132:40,133:80,134:160,135:'80+80',136:20,137:320};
 const channels=(report?.fields.channels||[]).map(c=>({...c,width_mhz:widths[c.operating_class]??null}));
 const stale=!!report&&(Date.now()/1000-report.time>90||!state.agent_recent);
 const label=channels.length?channels.map(c=>`Ch ${c.channel} · ${c.width_mhz==null?'width unknown':c.width_mhz+' MHz'}`).join(' / ')+(stale?' · stale':''):'Channel / width not reported';
 return {label,channels,stale,reported_at:report?new Date(report.time*1000).toLocaleString():null,evidence:report?'Operating Channel Report TLV 0x8f':'No Operating Channel Report received',note:'Radio operating width, not negotiated client width. Channel numbers are retained as reported; wide-channel operating classes may identify a center channel.'};
}
function meshModel(){
 const obs=Object.values(state.observations||{}),primary=x=>!x.agent||x.agent===state.target;
 const br=obs.find(x=>x.type===0x83&&primary(x)),cr=obs.filter(x=>x.type===0x84&&primary(x)).sort((a,b)=>b.time-a.time)[0];
 const clients=(cr?.fields.bss||[]).flatMap(b=>(b.clients||[]).map(c=>({...c,bssid:b.bssid}))),bsses=state.operational_bss||[],ids=radioIds(),nodes=[],links=[];
 const add=(id,kind,title,sub,detail,x,y,band='unknown')=>nodes.push({id,kind,title,sub,detail,x,y,band});
 const edge=(a,b,kind,label,band='unknown',stale=false)=>links.push({a,b,kind,label,band,stale});
 add('controller','controller','Python controller',state.controller,{role:'Controller',al_mac:state.controller,interface:state.interface||'Not reported',namespace:'easymesh-lab',online:state.controller_online,network:'Local DHCP and speed endpoint; no internet routing'},220,300);
 add('agent','agent',Object.values(state.radios||{}).find(r=>r.model)?.model||'EasyMesh agent',state.target,{role:'Agent',al_mac:state.target,status:state.status,optimizer:state.optimizer,last_seen:state.last_agent_at?new Date(state.last_agent_at*1000).toLocaleString():'Not seen',reported_ssids:[...new Set(bsses.map(b=>b.ssid))],evidence:'Configured Ethernet neighbor; AP Operational BSS TLV 0x83'},490,300);
 edge('controller','agent','wired','Ethernet · 1905.1','unknown',!state.agent_recent);
 bsses.forEach((b,i)=>{
  const band=meshBand(b.radio,obs),channel=meshChannel(b.radio,obs),count=clients.filter(c=>c.bssid===b.bssid).length;
  const stale=!br||Date.now()/1000-br.time>90||!state.agent_recent;
  add('bss-'+b.bssid,'bss',b.ssid||'(hidden / empty SSID)',band+' · '+count+' client'+(count===1?'':'s')+(stale?' · stale':''),{...b,band,radio_capabilities:obs.find(x=>x.type===0x85&&x.fields.radio===b.radio)?.fields||'Not reported',operating_channel:channel,associated_clients:count,evidence:'AP Operational BSS TLV 0x83',reported_at:br?new Date(br.time*1000).toLocaleString():'Unknown',stale,note:'Agent-reported BSS; wired reports do not verify over-the-air beacon visibility.'},750,100+i*200,band);
  nodes[nodes.length-1].channelLabel=channel.label;
  edge('agent','bss-'+b.bssid,'membership',band,band,stale);
 });
 const unmatched=[];
 clients.forEach((c,i)=>{
  const b=bsses.find(b=>b.bssid===c.bssid);if(!b){unmatched.push(c);return;}
  const band=meshBand(b.radio,obs),metrics=obs.find(x=>x.type===0x96&&x.fields.station===c.station);
  add('client-'+c.station,'client',state.client_telemetry?.[c.station]?.identity?.label==='Unknown device'?'Wi-Fi client':(state.client_telemetry?.[c.station]?.identity?.label||'Wi-Fi client')+' (inferred)',c.station,{...c,band,ssid:b.ssid,evidence:'Associated Clients TLV 0x84',reported_at:new Date(cr.time*1000).toLocaleString(),link_metrics:metrics?{...metrics.fields,reported_at:new Date(metrics.time*1000).toLocaleString()}:'Not measured',telemetry:state.client_telemetry?.[c.station]||'Not measured',note:'Identity hints are self-reported, not verified hardware identity.'},1100,250+i*155,band);
  edge('bss-'+b.bssid,'client-'+c.station,'wireless',band,band,Date.now()/1000-cr.time>90||!state.agent_recent);
 });
 // Further admitted agents, e.g. an extender on a wireless backhaul behind the primary agent.
 // 802.11 media info is the network BSSID, then the role: 0x40 is a (backhaul) STA,
 // whose BSSID is the BSS it joined, or all zeros while it is not associated.
 Object.entries(state.agents||{}).forEach(([al,a],k)=>{
  const id='agent-'+al,stale=!a.last_seen||Date.now()/1000-a.last_seen>90,dev=state.topology?.[al]?.device,ifaces=dev?.interfaces||[];
  const wifi=ifaces.find(x=>/^0x01/.test(x.media_type)&&x.media_info?.slice(12,14)==='40'&&!/^0{12}/.test(x.media_info)),parent=wifi?.media_info?.slice(0,12).match(/../g)?.join(':');
  const wired=!wifi&&ifaces.some(x=>/^0x00/.test(x.media_type));
  const up=bsses.find(b=>b.bssid===parent),upBand=up?meshBand(up.radio,obs):'unknown',own=a.operational_bss||[];
  add(id,'agent',Object.values(state.radios||{}).find(r=>r.agent===al&&r.model)?.model||'EasyMesh agent',al,{role:'Agent',al_mac:al,status:a.status,last_seen:a.last_seen?new Date(a.last_seen*1000).toLocaleString():'Not seen',backhaul:wifi?{interface:wifi.mac,media_type:wifi.media_type,joined_bssid:parent||'Not reported'}:'Not reported',reported_ssids:[...new Set(own.map(b=>b.ssid))],evidence:'Admitted agent; Device Information TLV 0x03, AP Operational BSS TLV 0x83'},490,600+k*260,upBand);
  if(wifi)edge(up?'bss-'+up.bssid:'agent',id,'wireless','Wi-Fi backhaul',upBand,stale);
  else if(wired)edge('controller',id,'wired','Ethernet · 1905.1','unknown',stale);
  else edge('agent',id,'wired','Backhaul not reported','unknown',stale);
  const report=obs.filter(x=>x.type===0x84&&x.agent===al).sort((x,y)=>y.time-x.time)[0];
  own.forEach((b,i)=>{
   const band=meshBand(b.radio,obs);
   add('bss-'+b.bssid,'bss',b.ssid||'(hidden / empty SSID)',band,{...b,band,agent:al,evidence:'AP Operational BSS TLV 0x83'},750,560+k*260+i*170,band);
   edge(id,'bss-'+b.bssid,'membership',band,band,stale);
   (report?.fields.bss||[]).filter(x=>x.bssid===b.bssid).flatMap(x=>x.clients||[]).forEach((c,j)=>{
    add('client-'+c.station,'client','Wi-Fi client',c.station,{...c,band,ssid:b.ssid,agent:al,evidence:'Associated Clients TLV 0x84'},1100,600+k*260+j*155,band);
    edge('bss-'+b.bssid,'client-'+c.station,'wireless',band,band,stale);
   });
  });
 });
 return {nodes,links,br,cr,clients,ids,bsses,unmatched};
}
function meshIcon(n){
 const common='fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
 if(n.kind==='controller')return `<g ${common}><rect x="-21" y="-15" width="42" height="28" rx="4"/><path d="M-10 21H10M0 13V21M-12 -5L-5 0L-12 5M0 6H10"/></g>`;
 if(n.kind==='agent')return `<g ${common}><path d="M-22 -13L0 -26L22 -13V13L0 26L-22 13Z"/><path d="M-12 -3Q0 -14 12 -3M-7 3Q0 -4 7 3"/><circle cx="0" cy="9" r="1.5"/></g>`;
 if(n.kind==='client'&&n.title.startsWith('Mac laptop'))return `<g ${common}><rect x="-23" y="-17" width="46" height="30" rx="3"/><path d="M-29 19H29L23 13H-23Z"/></g>`;
 if(n.kind==='client')return `<g ${common}><rect x="-12" y="-22" width="24" height="44" rx="5"/><path d="M-4 -16H4M-3 16H3"/></g>`;
 if(n.kind==='radio')return `<g ${common}><circle r="5"/><path d="M-12 -12A17 17 0 0 0 -12 12M12 -12A17 17 0 0 1 12 12M-19 -19A27 27 0 0 0 -19 19M19 -19A27 27 0 0 1 19 19"/></g>`;
 return `<g ${common}><path d="M-20 -7Q0 -25 20 -7M-13 1Q0 -12 13 1M-6 9Q0 2 6 9"/><circle cx="0" cy="17" r="1.5"/></g>`;
}
function meshMarkup(){
 $('meshLinks').innerHTML=mesh.links.map((l,i)=>`<g class="mesh-edge ${l.kind} ${l.stale?'stale':''}" data-edge="${i}" data-from="${esc(l.a)}" data-to="${esc(l.b)}"><path stroke="${meshColors[l.kind==='wireless'?l.band:l.kind]||meshColors.unknown}"/><g class="edge-label"><rect x="-65" y="-10" width="130" height="20" rx="10"/><text text-anchor="middle" y="4">${esc(l.label)}${l.stale?' · stale':''}</text></g></g>`).join('');
 $('meshNodes').innerHTML=[...topologyNodes.values()].map(n=>`<g class="mesh-node ${n.kind} ${n.id===topologySelection?'selected':''}" data-node="${esc(n.id)}" role="button" tabindex="0" aria-label="${esc(n.title+' '+n.sub)}" aria-pressed="${n.id===topologySelection}"><title>${esc(n.title+' · '+n.sub+' · drag to move')}</title><circle class="node-halo" r="46"/><circle class="node-disc" r="35" stroke="${meshColors[n.band]||meshColors.unknown}"/>${meshIcon(n)}${n.kind==='client'?signalSvg(state.client_telemetry?.[n.detail.station]):''}<text class="node-kind" text-anchor="middle" y="-56">${esc(n.kind.toUpperCase())}</text><text class="node-title" text-anchor="middle" y="64">${esc(n.title)}</text><text class="node-sub" text-anchor="middle" y="82">${esc(n.sub)}</text>${n.channelLabel?`<text class="node-sub node-channel" text-anchor="middle" y="100">${esc(n.channelLabel)}</text>`:''}</g>`).join('');
 for(const n of topologyNodes.values())n.el=$('meshNodes').querySelector(`[data-node="${CSS.escape(n.id)}"]`);
 for(let i=0;i<mesh.links.length;i++){const l=mesh.links[i];l.el=$('meshLinks').children[i];l.path=l.el.querySelector('path');l.badge=l.el.querySelector('.edge-label');}
 meshPaint();
}
function topologyInspect(){
 const n=topologyNodes.get(topologySelection);
 $('topologyDetail').innerHTML=n?`<span class="eyebrow">${esc(n.kind)}</span><h3>${esc(n.title)}</h3><p class="muted">${esc(n.sub)}</p>${n.kind==='client'?signalCard(state.client_telemetry?.[n.detail.station]):''}${n.kind==='client'?'<div class="mesh-client-actions"><button class="button" id="topologyClientMetrics">Link metrics</button><button class="button" id="meshBeacon">802.11k request</button><button class="button" id="meshSteer">802.11v steering</button><button class="button" id="meshSpeed">Speed test</button></div>':''}<div class="tree">${tree(n.detail)}</div>`:'<p>The selected node is no longer in the latest report. Select another node.</p>';
 if(!n)return;
 if(n.kind==='client'){
  $('topologyClientMetrics').onclick=()=>{tab('studio');selectCommand('sta_metrics',{station:n.detail.station});};
  $('meshBeacon').onclick=()=>{tab('studio');selectCommand('beacon_metrics',{station:n.detail.station,target_bssid:n.detail.bssid});};
  $('meshSpeed').onclick=()=>{tab('speed');renderSpeed(n.detail.station);};
  $('meshSteer').onclick=()=>{tab('studio');selectCommand('steer',{station:n.detail.station,bssid:n.detail.bssid});};
 }
}
function meshSelect(id){topologySelection=id;for(const n of topologyNodes.values()){n.el.classList.toggle('selected',n.id===id);n.el.setAttribute('aria-pressed',String(n.id===id));}topologyInspect();}
function renderTopology(){
 const model=meshModel();
 $('topologyStatus').textContent=`Live agent reports · BSSs ${topologyAge(model.br?.time)} · client list ${topologyAge(model.cr?.time)}${state.agent_recent?'':' · Agent not recently seen'}${model.unmatched.length?' · '+model.unmatched.length+' earlier associations have no current BSS':''}`;
 $('meshCounts').innerHTML=`<span><b>1</b> controller</span><span><b>1</b> agent</span><span><b>${model.clients.length}</b> reported clients</span><span><b>${model.ids.length}</b> radios / <b>${model.bsses.length}</b> BSSs</span>`;
 $('topologyRefresh').disabled=source!=='live'||!state.controller_online;
 const signature=JSON.stringify([model.nodes.map(n=>[n.id,n.detail]),model.links]);
 if(signature===topologySignature)return;
 topologySignature=signature;
 const old=topologyNodes;topologyNodes=new Map();
 for(const spec of model.nodes){const prev=old.get(spec.id);topologyNodes.set(spec.id,{...spec,x:prev?.x??spec.x,y:prev?.y??spec.y,vx:prev?.vx||0,vy:prev?.vy||0});}
 const changed=JSON.stringify([...old.keys()])!==JSON.stringify([...topologyNodes.keys()]);
 mesh.links=model.links;meshMarkup();topologyInspect();
 if(changed){for(let i=0;i<160;i++)meshStep();meshFit();meshWake(true);}
}
function meshStep(){
 const nodes=[...topologyNodes.values()];for(const n of nodes){n.fx=0;n.fy=0;}
 for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
  const a=nodes[i],b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y;if(Math.abs(dx)+Math.abs(dy)<.01){dx=1;dy=.7;}
  const d=Math.hypot(dx,dy),f=Math.min(10,18000/(d*d));a.fx-=f*dx/d;a.fy-=f*dy/d;b.fx+=f*dx/d;b.fy+=f*dy/d;
 }
 for(const l of mesh.links){const a=topologyNodes.get(l.a),b=topologyNodes.get(l.b),dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,rest=l.kind==='membership'?190:265,f=(d-rest)*.018;a.fx+=f*dx/d;a.fy+=f*dy/d;b.fx-=f*dx/d;b.fy-=f*dy/d;}
 let speed=0;
 for(const n of nodes){if(mesh.drag?.id===n.id){n.vx=n.vy=0;continue;}n.fx+=(500-n.x)*.0005;n.fy+=(310-n.y)*.0005;n.vx=Math.max(-12,Math.min(12,(n.vx+n.fx)*.8));n.vy=Math.max(-12,Math.min(12,(n.vy+n.fy)*.8));n.x+=n.vx;n.y+=n.vy;speed+=Math.abs(n.vx)+Math.abs(n.vy);}
 return speed;
}
function meshPaint(){
 $('meshWorld').setAttribute('transform',`translate(${mesh.view.x} ${mesh.view.y}) scale(${mesh.view.k})`);
 for(const n of topologyNodes.values())n.el?.setAttribute('transform',`translate(${n.x} ${n.y})`);
 for(const l of mesh.links){
  const a=topologyNodes.get(l.a),b=topologyNodes.get(l.b),dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,ux=dx/d,uy=dy/d,from=Math.min(40,d*.3),to=Math.max(d-40,d*.7);
  let path='';const steps=l.kind==='wireless'?80:1,amp=Math.min(8,1800/d);
  for(let i=0;i<=steps;i++){const t=i/steps,dist=from+(to-from)*t,w=l.kind==='wireless'?Math.sin(t*Math.PI*20)*Math.sin(t*Math.PI)*amp:0;path+=(i?'L':'M')+(a.x+ux*dist-uy*w).toFixed(2)+' '+(a.y+uy*dist+ux*w).toFixed(2);}
  l.path.setAttribute('d',path);l.badge.setAttribute('transform',`translate(${a.x+dx*.5} ${a.y+dy*.5-14})`);
 }
}
function meshWake(reheat=false){
 if(reheat)mesh.settleUntil=performance.now()+3500;
 if(mesh.raf||mesh.paused||activeTab!=='topology'||document.hidden||(!mesh.drag&&performance.now()>=mesh.settleUntil))return;
 const tick=()=>{
  mesh.raf=0;
  if(mesh.paused||activeTab!=='topology'||document.hidden)return;
  if(!mesh.drag&&performance.now()>=mesh.settleUntil){for(const n of topologyNodes.values())n.vx=n.vy=0;return;}
  meshStep();
  const fade=mesh.drag?1:Math.min(1,Math.max(0,(mesh.settleUntil-performance.now())/1200));
  for(const n of topologyNodes.values()){if(mesh.drag?.id===n.id)continue;n.x-=n.vx*(1-fade);n.y-=n.vy*(1-fade);n.vx*=fade;n.vy*=fade;}
  meshPaint();mesh.raf=requestAnimationFrame(tick);
 };mesh.raf=requestAnimationFrame(tick);
}
function meshFit(){const nodes=[...topologyNodes.values()];if(!nodes.length)return;const minx=Math.min(...nodes.map(n=>n.x))-120,maxx=Math.max(...nodes.map(n=>n.x))+120,miny=Math.min(...nodes.map(n=>n.y))-90,maxy=Math.max(...nodes.map(n=>n.y))+120;mesh.view.k=Math.min(1.6,900/(maxx-minx),570/(maxy-miny));mesh.view.x=500-(minx+maxx)/2*mesh.view.k;mesh.view.y=325-(miny+maxy)/2*mesh.view.k;meshPaint();}
function meshPoint(e){const point=$('topologyGraph').createSVGPoint();point.x=e.clientX;point.y=e.clientY;return point.matrixTransform($('topologyGraph').getScreenCTM().inverse());}
function meshZoom(f,point={x:500,y:325}){const k=Math.max(.2,Math.min(3,mesh.view.k*f)),ratio=k/mesh.view.k;mesh.view.x=point.x-(point.x-mesh.view.x)*ratio;mesh.view.y=point.y-(point.y-mesh.view.y)*ratio;mesh.view.k=k;meshPaint();}
const graph=$('topologyGraph');
graph.addEventListener('pointerdown',e=>{if(e.button!==0||mesh.drag)return;const p=meshPoint(e),target=e.target.closest('[data-node]'),id=target?.dataset.node;mesh.drag={id,pointer:e.pointerId,x:p.x,y:p.y,moved:0};if(id)meshSelect(id);graph.setPointerCapture(e.pointerId);meshWake(true);});
graph.addEventListener('pointermove',e=>{const drag=mesh.drag;if(!drag||drag.pointer!==e.pointerId)return;const p=meshPoint(e),dx=p.x-drag.x,dy=p.y-drag.y;drag.moved+=Math.abs(dx)+Math.abs(dy);if(drag.id){const n=topologyNodes.get(drag.id);if(n){n.x+=dx/mesh.view.k;n.y+=dy/mesh.view.k;n.vx=n.vy=0;}}else{mesh.view.x+=dx;mesh.view.y+=dy;}drag.x=p.x;drag.y=p.y;meshPaint();meshWake(true);});
function meshRelease(e){if(mesh.drag?.pointer!==e.pointerId)return;mesh.drag=null;if(graph.hasPointerCapture(e.pointerId))graph.releasePointerCapture(e.pointerId);meshWake(true);}
graph.addEventListener('pointerup',meshRelease);graph.addEventListener('pointercancel',meshRelease);
graph.addEventListener('wheel',e=>{e.preventDefault();meshZoom(Math.exp(-e.deltaY*.0015),meshPoint(e));},{passive:false});
graph.addEventListener('keydown',e=>{const id=e.target.closest('[data-node]')?.dataset.node;if(!id)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();meshSelect(id);}});
$('meshZoomIn').onclick=()=>meshZoom(1.2);$('meshZoomOut').onclick=()=>meshZoom(1/1.2);$('meshFit').onclick=meshFit;
$('meshReset').onclick=()=>{topologyNodes.clear();topologySignature='';renderTopology();};
function meshMotionLabel(){$('meshMotion').textContent=mesh.paused?'Resume motion':'Pause motion';$('meshMotion').setAttribute('aria-pressed',String(mesh.paused));}
$('meshMotion').onclick=()=>{mesh.paused=!mesh.paused;meshMotionLabel();meshWake(true);};meshMotionLabel();
$('topologyRefresh').onclick=async()=>{try{await send('topology');}catch(e){toast(e.message,true);}};
document.addEventListener('visibilitychange',meshWake);
