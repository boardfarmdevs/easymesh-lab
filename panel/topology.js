'use strict';
// Original SVG implementation, inspired by the OpenSync lab's spring topology.
// Positions are presentation only: there are no protocol side effects from dragging.
let topologyNodes=new Map(), topologySelection='agent', topologySignature='';
const mesh={links:[],view:{x:0,y:0,k:1},drag:null,energy:0,paused:matchMedia('(prefers-reduced-motion: reduce)').matches,raf:0,expanded:false};
const meshColors={wired:'#a9bed1',membership:'#65778e','5 GHz':'#9aa5ff','2.4 GHz':'#ffc16c','6 GHz':'#58d6b4',unknown:'#9badbd'};
function topologyAge(t){return t?Math.max(0,Math.floor(Date.now()/1000-t))+'s ago':'not received';}
function meshBand(id,obs){
 const classes=obs.find(x=>x.type===0x85&&x.fields.radio===id)?.fields.operating_classes?.map(x=>x.class)||[];
 return classes.some(x=>x>=131&&x<=137)?'6 GHz':state.radios?.[id]?.rf_bands===2||classes.some(x=>x>=115&&x<=130)?'5 GHz':state.radios?.[id]?.rf_bands===1||classes.some(x=>x>=81&&x<=84)?'2.4 GHz':'unknown';
}
function meshModel(){
 const obs=Object.values(state.observations||{}),br=obs.find(x=>x.type===0x83),cr=obs.filter(x=>x.type===0x84).sort((a,b)=>b.time-a.time)[0];
 const clients=(cr?.fields.bss||[]).flatMap(b=>(b.clients||[]).map(c=>({...c,bssid:b.bssid}))),bsses=state.operational_bss||[],ids=radioIds(),nodes=[],links=[];
 const add=(id,kind,title,sub,detail,x,y,band='unknown')=>nodes.push({id,kind,title,sub,detail,x,y,band});
 const edge=(a,b,kind,label,band='unknown',stale=false)=>links.push({a,b,kind,label,band,stale});
 add('controller','controller','Python controller',state.controller,{role:'Controller',al_mac:state.controller,interface:state.interface||'Not reported',namespace:'easymesh-lab',online:state.controller_online,network:'Local DHCP and speed endpoint; no internet routing'},220,300);
 add('agent','agent',Object.values(state.radios||{}).find(r=>r.model)?.model||'EasyMesh agent',state.target,{role:'Agent',al_mac:state.target,status:state.status,optimizer:state.optimizer,last_seen:state.last_agent_at?new Date(state.last_agent_at*1000).toLocaleString():'Not seen',reported_ssids:[...new Set(bsses.map(b=>b.ssid))],evidence:'Configured Ethernet neighbor; AP Operational BSS TLV 0x83'},490,300);
 edge('controller','agent','wired','Ethernet · 1905.1','unknown',!state.agent_recent);
 if(mesh.expanded)ids.forEach((id,i)=>{
  const band=meshBand(id,obs),cap=obs.find(x=>x.type===0x85&&x.fields.radio===id);
  add('radio-'+id,'radio',band+' radio',id,{radio:id,band,capabilities:cap?.fields||'Not reported',provisioning:state.radios?.[id]||'Not provisioned',six_ghz_request:band==='6 GHz'?(state.six_ghz_status||'not_requested'):'Not applicable',evidence:'AP Radio Basic Capabilities TLV 0x85'},580,120+i*190,band);
  edge('agent','radio-'+id,'membership','Radio');
  bsses.filter(b=>b.radio===id).forEach((b,j)=>{
   add('bss-'+b.bssid,'bss',b.ssid,b.bssid,{...b,band,evidence:'AP Operational BSS TLV 0x83',reported_at:br?new Date(br.time*1000).toLocaleString():'Unknown'},800+j*130,120+i*190,band);
   edge('radio-'+id,'bss-'+b.bssid,'membership','BSS');
  });
 });
 const unmatched=[];
 clients.forEach((c,i)=>{
  const b=bsses.find(b=>b.bssid===c.bssid);if(!b){unmatched.push(c);return;}
  const band=meshBand(b.radio,obs),metrics=obs.find(x=>x.type===0x96&&x.fields.station===c.station);
  add('client-'+c.station,'client',state.client_telemetry?.[c.station]?.identity?.label==='Unknown device'?'Wi-Fi client':(state.client_telemetry?.[c.station]?.identity?.label||'Wi-Fi client')+' (inferred)',c.station,{...c,band,ssid:b.ssid,evidence:'Associated Clients TLV 0x84',reported_at:new Date(cr.time*1000).toLocaleString(),link_metrics:metrics?{...metrics.fields,reported_at:new Date(metrics.time*1000).toLocaleString()}:'Not measured',telemetry:state.client_telemetry?.[c.station]||'Not measured',note:'Identity hints are self-reported, not verified hardware identity.'},mesh.expanded?1040:790,250+i*155,band);
  edge(mesh.expanded?'bss-'+b.bssid:'agent','client-'+c.station,'wireless',band,band,Date.now()/1000-cr.time>90||!state.agent_recent);
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
 $('meshNodes').innerHTML=[...topologyNodes.values()].map(n=>`<g class="mesh-node ${n.kind} ${n.id===topologySelection?'selected':''} ${n.pinned?'pinned':''}" data-node="${esc(n.id)}" role="button" tabindex="0" aria-label="${esc(n.title+' '+n.sub)}" aria-pressed="${n.id===topologySelection}"><title>${esc(n.title+' · '+n.sub+' · drag to move, double-click or P to pin')}</title><circle class="node-halo" r="46"/><circle class="node-disc" r="35" stroke="${meshColors[n.band]||meshColors.unknown}"/>${meshIcon(n)}${n.kind==='client'?signalSvg(state.client_telemetry?.[n.detail.station]):''}<text class="node-kind" text-anchor="middle" y="-56">${esc(n.kind.toUpperCase())}</text><text class="node-title" text-anchor="middle" y="64">${esc(n.title)}</text><text class="node-sub" text-anchor="middle" y="82">${esc(n.sub)}</text><text class="node-pin" text-anchor="middle" y="-39">PINNED</text></g>`).join('');
 for(const n of topologyNodes.values())n.el=$('meshNodes').querySelector(`[data-node="${CSS.escape(n.id)}"]`);
 for(let i=0;i<mesh.links.length;i++){const l=mesh.links[i];l.el=$('meshLinks').children[i];l.path=l.el.querySelector('path');l.badge=l.el.querySelector('.edge-label');}
 meshPaint();
}
function topologyInspect(){
 const n=topologyNodes.get(topologySelection);
 $('topologyDetail').innerHTML=n?`<span class="eyebrow">${esc(n.kind)}</span><h3>${esc(n.title)}</h3><p class="muted">${esc(n.sub)}</p><button class="button" id="meshPin">${n.pinned?'Unpin':'Pin'} position</button>${n.kind==='client'?signalCard(state.client_telemetry?.[n.detail.station]):''}${n.kind==='client'?'<div class="mesh-client-actions"><button class="button" id="topologyClientMetrics">Link metrics</button><button class="button" id="meshBeacon">802.11k request</button><button class="button" id="meshSteer">802.11v steering</button><button class="button" id="meshSpeed">Speed test</button></div>':''}<div class="tree">${tree(n.detail)}</div>`:'<p>The selected node is no longer in the latest report. Select another node.</p>';
 if(!n)return;
 $('meshPin').onclick=()=>meshPin(n.id);
 if(n.kind==='client'){
  $('topologyClientMetrics').onclick=()=>{tab('studio');selectCommand('sta_metrics',{station:n.detail.station});};
  $('meshBeacon').onclick=()=>{tab('studio');selectCommand('beacon_metrics',{station:n.detail.station,target_bssid:n.detail.bssid});};
  $('meshSpeed').onclick=()=>{tab('speed');renderSpeed(n.detail.station);};
  $('meshSteer').onclick=()=>{tab('studio');selectCommand('steer',{station:n.detail.station,bssid:n.detail.bssid});};
 }
}
function meshSelect(id){topologySelection=id;for(const n of topologyNodes.values()){n.el.classList.toggle('selected',n.id===id);n.el.setAttribute('aria-pressed',String(n.id===id));}topologyInspect();}
function meshPin(id){const n=topologyNodes.get(id);if(!n)return;n.pinned=!n.pinned;n.vx=n.vy=0;n.el.classList.toggle('pinned',n.pinned);topologyInspect();meshWake();}
function renderTopology(){
 const model=meshModel();
 $('topologyStatus').textContent=`Live agent reports · BSSs ${topologyAge(model.br?.time)} · client list ${topologyAge(model.cr?.time)}${state.agent_recent?'':' · Agent not recently seen'}${model.unmatched.length?' · '+model.unmatched.length+' earlier associations have no current BSS':''}`;
 $('meshCounts').innerHTML=`<span><b>1</b> controller</span><span><b>1</b> agent</span><span><b>${model.clients.length}</b> reported clients</span><span><b>${model.ids.length}</b> radios / <b>${model.bsses.length}</b> BSSs</span>`;
 $('topologyRefresh').disabled=source!=='live'||!state.controller_online;
 const signature=JSON.stringify([model.nodes.map(n=>[n.id,n.detail]),model.links,mesh.expanded]);
 if(signature===topologySignature){meshWake();return;}
 topologySignature=signature;
 const old=topologyNodes;topologyNodes=new Map();
 for(const spec of model.nodes){const prev=old.get(spec.id);topologyNodes.set(spec.id,{...spec,x:prev?.x??spec.x,y:prev?.y??spec.y,vx:prev?.vx||0,vy:prev?.vy||0,pinned:prev?.pinned||false});}
 const changed=JSON.stringify([...old.keys()])!==JSON.stringify([...topologyNodes.keys()]);
 mesh.links=model.links;meshMarkup();topologyInspect();
 if(changed){for(let i=0;i<160;i++)meshStep();meshFit();}
 meshWake();
}
function meshStep(){
 const nodes=[...topologyNodes.values()];for(const n of nodes){n.fx=0;n.fy=0;}
 for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
  const a=nodes[i],b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y;if(Math.abs(dx)+Math.abs(dy)<.01){dx=1;dy=.7;}
  const d=Math.hypot(dx,dy),f=Math.min(10,18000/(d*d));a.fx-=f*dx/d;a.fy-=f*dy/d;b.fx+=f*dx/d;b.fy+=f*dy/d;
 }
 for(const l of mesh.links){const a=topologyNodes.get(l.a),b=topologyNodes.get(l.b),dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,rest=l.kind==='membership'?190:265,f=(d-rest)*.018;a.fx+=f*dx/d;a.fy+=f*dy/d;b.fx-=f*dx/d;b.fy-=f*dy/d;}
 let speed=0;
 for(const n of nodes){if(n.pinned||mesh.drag?.id===n.id){n.vx=n.vy=0;continue;}n.fx+=(500-n.x)*.0005;n.fy+=(310-n.y)*.0005;n.vx=Math.max(-12,Math.min(12,(n.vx+n.fx)*.8));n.vy=Math.max(-12,Math.min(12,(n.vy+n.fy)*.8));n.x+=n.vx;n.y+=n.vy;speed+=Math.abs(n.vx)+Math.abs(n.vy);}
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
function meshWake(){if(mesh.raf||mesh.paused||activeTab!=='topology'||document.hidden)return;let frames=0;const tick=()=>{mesh.raf=0;if(mesh.paused||activeTab!=='topology'||document.hidden)return;const speed=meshStep();meshPaint();if(speed>.02||mesh.drag){frames++;if(frames<1800)mesh.raf=requestAnimationFrame(tick);}};mesh.raf=requestAnimationFrame(tick);}
function meshFit(){const nodes=[...topologyNodes.values()];if(!nodes.length)return;const minx=Math.min(...nodes.map(n=>n.x))-120,maxx=Math.max(...nodes.map(n=>n.x))+120,miny=Math.min(...nodes.map(n=>n.y))-90,maxy=Math.max(...nodes.map(n=>n.y))+120;mesh.view.k=Math.min(1.6,900/(maxx-minx),570/(maxy-miny));mesh.view.x=500-(minx+maxx)/2*mesh.view.k;mesh.view.y=325-(miny+maxy)/2*mesh.view.k;meshPaint();}
function meshPoint(e){const point=$('topologyGraph').createSVGPoint();point.x=e.clientX;point.y=e.clientY;return point.matrixTransform($('topologyGraph').getScreenCTM().inverse());}
function meshZoom(f,point={x:500,y:325}){const k=Math.max(.2,Math.min(3,mesh.view.k*f)),ratio=k/mesh.view.k;mesh.view.x=point.x-(point.x-mesh.view.x)*ratio;mesh.view.y=point.y-(point.y-mesh.view.y)*ratio;mesh.view.k=k;meshPaint();}
const graph=$('topologyGraph');
graph.addEventListener('pointerdown',e=>{if(e.button!==0||mesh.drag)return;const p=meshPoint(e),target=e.target.closest('[data-node]'),id=target?.dataset.node;mesh.drag={id,pointer:e.pointerId,x:p.x,y:p.y,moved:0};if(id)meshSelect(id);graph.setPointerCapture(e.pointerId);meshWake();});
graph.addEventListener('pointermove',e=>{const drag=mesh.drag;if(!drag||drag.pointer!==e.pointerId)return;const p=meshPoint(e),dx=p.x-drag.x,dy=p.y-drag.y;drag.moved+=Math.abs(dx)+Math.abs(dy);if(drag.id){const n=topologyNodes.get(drag.id);if(n){n.x+=dx/mesh.view.k;n.y+=dy/mesh.view.k;n.vx=n.vy=0;}}else{mesh.view.x+=dx;mesh.view.y+=dy;}drag.x=p.x;drag.y=p.y;meshPaint();meshWake();});
function meshRelease(e){if(mesh.drag?.pointer!==e.pointerId)return;mesh.drag=null;if(graph.hasPointerCapture(e.pointerId))graph.releasePointerCapture(e.pointerId);meshWake();}
graph.addEventListener('pointerup',meshRelease);graph.addEventListener('pointercancel',meshRelease);
graph.addEventListener('dblclick',e=>{const id=e.target.closest('[data-node]')?.dataset.node;if(id)meshPin(id);});
graph.addEventListener('wheel',e=>{e.preventDefault();meshZoom(Math.exp(-e.deltaY*.0015),meshPoint(e));},{passive:false});
graph.addEventListener('keydown',e=>{const id=e.target.closest('[data-node]')?.dataset.node;if(!id)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();meshSelect(id);}if(e.key.toLowerCase()==='p'){e.preventDefault();meshPin(id);}});
$('meshExpand').onchange=e=>{mesh.expanded=e.target.checked;topologySignature='';renderTopology();};
$('meshZoomIn').onclick=()=>meshZoom(1.2);$('meshZoomOut').onclick=()=>meshZoom(1/1.2);$('meshFit').onclick=meshFit;
$('meshReset').onclick=()=>{topologyNodes.clear();topologySignature='';renderTopology();};
function meshMotionLabel(){$('meshMotion').textContent=mesh.paused?'Resume motion':'Pause motion';$('meshMotion').setAttribute('aria-pressed',String(mesh.paused));}
$('meshMotion').onclick=()=>{mesh.paused=!mesh.paused;meshMotionLabel();meshWake();};meshMotionLabel();
$('topologyRefresh').onclick=async()=>{try{await send('topology');}catch(e){toast(e.message,true);}};
document.addEventListener('visibilitychange',meshWake);
