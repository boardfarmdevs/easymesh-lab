'use strict';
let session,busy=false;const $=id=>document.getElementById(id),LIMIT=128*1024*1024,CHUNK=8*1024*1024;
async function api(path,body){const headers=session?{'X-Speed-Session':session.id,'X-Speed-Token':session.token}:{};if(body!==undefined)headers['Content-Type']='application/json';const r=await fetch(path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});if(!r.ok)throw Error((await r.json()).error||'Request failed');return r.json();}
async function measure(direction){
 const started=performance.now(),abort=new AbortController();let bytes=0,reserved=0,failed=null;
 const timer=setTimeout(()=>abort.abort(),6000),payload=direction==='upload'?new Uint8Array(CHUNK):null;
 if(payload)for(let i=0;i<payload.length;i+=65536)crypto.getRandomValues(payload.subarray(i,i+65536));
 const worker=async()=>{while(!abort.signal.aborted&&reserved<LIMIT){reserved+=CHUNK;try{
  const r=await fetch('/'+direction,{method:direction==='upload'?'POST':'GET',headers:{'X-Speed-Session':session.id,'X-Speed-Token':session.token},body:payload,signal:abort.signal,cache:'no-store'});
  if(!r.ok)throw Error('Transfer failed: '+r.status);
  if(direction==='download'){const reader=r.body.getReader();while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.length;}}
  else bytes+=(await r.json()).received;
 }catch(e){if(!abort.signal.aborted){failed=e;abort.abort();}break;}}};
 await Promise.all([worker(),worker()]);clearTimeout(timer);if(failed)throw failed;
 return {bytes,seconds:(performance.now()-started)/1000};
}
async function run(job){if(busy)return;busy=true;$('start').disabled=true;try{
 await api('/running',{job:job.id});$('status').textContent='Measuring local HTTP latency…';const pings=[];for(let i=0;i<5;i++){const t=performance.now();await api('/ping');pings.push(performance.now()-t);}const latency_ms=pings.sort((a,b)=>a-b)[2];$('latency').textContent=latency_ms.toFixed(1);
 $('status').textContent='Download: controller host → this client…';const download=await measure('download');$('download').textContent=(download.bytes*8/download.seconds/1e6).toFixed(1);
 $('status').textContent='Upload: this client → controller host…';const upload=await measure('upload');$('upload').textContent=(upload.bytes*8/upload.seconds/1e6).toFixed(1);
 await api('/result',{job:job.id,latency_ms,download,upload});$('status').textContent='Complete. Results are also in the controller panel.';
 }catch(e){$('status').textContent='Test failed: '+e.message;try{await api('/result',{job:job.id,error:e.message});}catch(_){} }finally{busy=false;$('start').disabled=false;}}
async function poll(){try{const d=await api('/poll');$('identity').textContent=d.ip+(d.mac?' · '+d.mac:'');if(d.job&&!busy)run(d.job);}catch(e){$('status').textContent=e.message;}}
$('start').onclick=async()=>{try{await api('/begin',{});await poll();}catch(e){$('status').textContent=e.message;}};
(async()=>{try{session=await api('/register',{});$('status').textContent='Ready. Start here or from the controller panel.';$('start').disabled=false;await poll();setInterval(poll,2000);}catch(e){$('status').textContent=e.message;}})();
