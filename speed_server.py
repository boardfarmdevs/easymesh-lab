#!/usr/bin/env python3
"""Python HTTP throughput endpoint, bound only to the isolated client subnet."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,os,secrets,threading,time,uuid,math
from pathlib import Path
from urllib.parse import urlparse
import speed_store as store
BASE=Path(__file__).resolve().parent;BLOCK=os.urandom(256*1024);LIMIT=8*1024*1024;SLOTS=threading.BoundedSemaphore(8)

def peer_mac(ip):
 try:
  for line in Path('/proc/net/arp').read_text().splitlines()[1:]:
   cols=line.split()
   if cols[0]==ip and cols[2]!='0x0':return cols[3]
 except OSError:pass
 return None

class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 disable_nagle_algorithm=True
 def log_message(self,*args):pass
 def setup(self):super().setup();self.connection.settimeout(20)
 def reply(self,value,status=200,ctype='application/json'):
  data=json.dumps(value).encode() if ctype=='application/json' else value
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'");self.end_headers()
  try:self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):pass
 def guard(self):
  if self.headers.get('Host') not in ('10.203.88.1:8080','127.0.0.1:8080','localhost:8080'):raise ValueError('Use the lab endpoint address')
  if self.headers.get('Origin') not in (None,'http://10.203.88.1:8080','http://127.0.0.1:8080','http://localhost:8080'):raise ValueError('Invalid origin')
 def session(self):
  id=store.valid_id(self.headers.get('X-Speed-Session',''));s=store.read(store.BASE/'sessions'/f'{id}.json',{})
  if not s or not secrets.compare_digest(s.get('token',''),self.headers.get('X-Speed-Token','')) or s['ip']!=self.client_address[0]:raise ValueError('Reopen the client page to register')
  return s
 def body(self,maxsize=16384):
  n=int(self.headers.get('Content-Length','0'))
  if not 0<=n<=maxsize:raise ValueError('Request size exceeded')
  data=self.rfile.read(n)
  if len(data)!=n:raise ValueError('Incomplete body')
  return data
 def do_GET(self):
  try:
   self.guard();path=urlparse(self.path).path
   files={'/':'speed-client.html','/client.js':'speed-client.js','/client.css':'speed-client.css'}
   if path in files:
    ct={'/':'text/html','/client.js':'text/javascript','/client.css':'text/css'}[path]
    return self.reply((BASE/'panel'/files[path]).read_bytes(),ctype=ct)
   s=self.session()
   if path=='/poll':
    s.update(seen=time.time(),mac=peer_mac(s['ip']));store.atomic(store.BASE/'sessions'/f"{s['id']}.json",s)
    job=store.read(store.BASE/'jobs'/f"{s['id']}.json",{})
    return self.reply({'job':job if job.get('status')=='queued' else None,'mac':s['mac'],'ip':s['ip']})
   if path=='/ping':return self.reply({'time':time.time()})
   if path=='/download':
    if not SLOTS.acquire(blocking=False):return self.reply({'error':'Endpoint busy'},429)
    try:
     self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(LIMIT));self.send_header('Cache-Control','no-store');self.end_headers()
     for _ in range(LIMIT//len(BLOCK)):self.wfile.write(BLOCK)
    except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
    finally:SLOTS.release()
    return
   self.reply({'error':'Not found'},404)
  except (ValueError,KeyError,TypeError) as e:self.reply({'error':str(e)},400)
  except (BrokenPipeError,ConnectionResetError,TimeoutError):self.close_connection=True
 def do_POST(self):
  try:
   self.guard();path=urlparse(self.path).path
   if path=='/register':
    self.body();id=uuid.uuid4().hex;s={'id':id,'token':secrets.token_urlsafe(32),'ip':self.client_address[0],'mac':peer_mac(self.client_address[0]),'seen':time.time(),'browser':self.headers.get('User-Agent','')[:250]}
    store.atomic(store.BASE/'sessions'/f'{id}.json',s);return self.reply(s)
   s=self.session();id=s['id']
   if path=='/upload':
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<=LIMIT:raise ValueError('Upload size exceeded')
    remaining=n
    while remaining:
     block=self.rfile.read(min(65536,remaining))
     if not block:raise ValueError('Incomplete upload')
     remaining-=len(block)
    return self.reply({'received':n})
   body=json.loads(self.body() or b'{}')
   if path=='/begin':return self.reply(store.enqueue(id))
   job=store.read(store.BASE/'jobs'/f'{id}.json',{})
   if body.get('job')!=job.get('id') or not job:raise ValueError('Unknown test job')
   if path=='/running':
    if job.get('status')!='queued':raise ValueError('Job already started')
    job.update(status='running',started_at=time.time());store.atomic(store.BASE/'jobs'/f'{id}.json',job);return self.reply({'ok':True})
   if path=='/result':
    if job.get('status')!='running':raise ValueError('Job is not running')
    result={'id':job['id'],'session':id,'ip':s['ip'],'mac':peer_mac(s['ip']),'finished_at':time.time(),'scope':'host_selftest' if s['ip']=='10.203.88.1' else 'client_path','method':'Browser HTTP payload throughput; two parallel streams; no internet','status':'failed' if body.get('error') else 'complete'}
    if body.get('error'):result['error']=str(body['error'])[:300]
    else:
     for direction in ('download','upload'):
      data=body[direction];count=int(data['bytes']);duration=float(data['seconds'])
      if not 0<=count<=128*1024*1024 or not math.isfinite(duration) or not 0<duration<=60:raise ValueError('Invalid measurement')
      result[direction]={'bytes':count,'seconds':duration,'mbps':round(count*8/duration/1e6,2)}
     latency=float(body['latency_ms'])
     if not math.isfinite(latency) or not 0<=latency<=60000:raise ValueError('Invalid latency')
     result['http_latency_ms']=round(latency,2)
    store.atomic(store.BASE/'results'/f"{job['id']}.json",result);job.update(status=result['status']);store.atomic(store.BASE/'jobs'/f'{id}.json',job);return self.reply(result)
   self.reply({'error':'Not found'},404)
  except (ValueError,KeyError,TypeError) as e:self.close_connection=True;self.reply({'error':str(e)},400)
  except (BrokenPipeError,ConnectionResetError,TimeoutError):self.close_connection=True

def heartbeat():
 while True:store.atomic(store.BASE/'service.json',{'heartbeat':time.time(),'url':'http://10.203.88.1:8080','subnet':'10.203.88.0/24','internet':False});time.sleep(3)
if __name__=='__main__':
 for name in ('sessions','jobs','results'):(store.BASE/name).mkdir(parents=True,exist_ok=True)
 server=ThreadingHTTPServer(('10.203.88.1',8080),Handler);threading.Thread(target=heartbeat,daemon=True).start();print('Speed endpoint http://10.203.88.1:8080',flush=True);server.serve_forever()
