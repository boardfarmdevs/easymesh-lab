#!/usr/bin/env python3
"""Local, unprivileged Python HTTP server for the protocol workbench."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse, parse_qs
import uuid
import speed_store
from client_telemetry import client_views
from optimizer import advisory_report
from experiments import validate_steering
from controller import frame
from protocol import CATALOG,LOOKUP,build_command,decode_packet,MESSAGE_NAMES,TLV_NAMES
from wsc import validate_config

BASE=Path(__file__).resolve().parent
TOKEN=secrets.token_urlsafe(32)
REPLAYS={p.stem:p for p in sorted((BASE/'replays').glob('*')) if p.suffix in ('.pcap','.pcapng')}
REPLAY_CACHE={}

def read_json(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def state():
    s=read_json(BASE/'state.json',{})
    s['controller_online']=time.time()-s.get('heartbeat_at',0)<10
    s['agent_recent']=time.time()-s.get('last_agent_at',0)<90
    s['client_telemetry']=client_views(s,read_json(BASE/'run/device-evidence.json',{}),speed_store.sessions())
    s['managed_radio_observations']=read_json(BASE/'run/wifi-radio-observations.json',[])
    s['optimizer']=advisory_report(s['client_telemetry'],s)
    return s

def validate(name,params):
    if name not in LOOKUP or not isinstance(params,dict):raise ValueError('Invalid command or parameters')
    if name in ('set_ssid','reonboard','enable_6ghz'):
        c=read_json(BASE/'config.json',{})
        if name=='enable_6ghz':c.update(enable_6ghz=True,controller_profile=2)
        if name=='set_ssid':
            c['ssid']=params.get('ssid','')
            if params.get('password'):c['password']=params['password']
        validate_config(c)
    elif name=='polling':
        if params.get('enabled') not in ('true','false'):raise ValueError('Select true or false')
    else:
        current=state()
        if name=='steer':validate_steering(params,current,time.time())
        build_command(name,params,current)

def preview(name,params):
    validate(name,params);s=state();src=s.get('controller','02:00:00:00:00:01');dst=s.get('target','02:00:00:00:01:35')
    if name=='push_button':dst='01:80:c2:00:00:13'
    elif params.get('agent'):dst=str(params['agent']).strip().lower()
    if name in ('set_ssid','reonboard','enable_6ghz'):
        from responder import tlv,macbytes
        recipes=[(10,tlv(1,macbytes(src))+tlv(15,b'\0')+tlv(16,bytes([band]))) for band in ((0,1,3) if name=='enable_6ghz' or read_json(BASE/'config.json',{}).get('enable_6ghz') else (0,1))]
    else:recipes=build_command(name,params,s)
    flags=0xc0 if name=='push_button' else 0x80  # relayed multicast
    return {'packets':[decode_packet(frame(src,dst,k,0,b,flags)) for k,b in recipes],
            'note':'Preview only; message ID 0 is a placeholder. WSC nonces, keys and encrypted M2 are created only when the agent sends M1.' if name in ('set_ssid','reonboard','enable_6ghz') else 'Preview only. A fresh message ID is assigned when sent.',
            'expected':LOOKUP[name]['expected']}

class Handler(BaseHTTPRequestHandler):
    server_version='ProtocolLab/1.0'
    def log_message(self,format,*args):pass
    def allowed(self):
        return (self.client_address[0] in self.server.allowed_clients
                and self.headers.get('Host','') in self.server.allowed_hosts)
    def deny_access(self):
        detail={'error':'Host or client is not allowed',
                'client_ip':self.client_address[0],
                'requested_host':self.headers.get('Host',''),
                'accepted_hosts':sorted(self.server.allowed_hosts)}
        print(json.dumps(dict(event='access_denied',**detail)),flush=True)
        return self.send_json(detail,403)
    def send_bytes(self,data,ctype,status=200):
        self.send_response(status);self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        try:
            self.end_headers();self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):
            pass  # A browser can leave while a replay is being delivered.
    def send_json(self,obj,status=200):self.send_bytes(json.dumps(obj).encode(),'application/json',status)
    def do_GET(self):
        if not self.allowed():return self.deny_access()
        q=urlparse(self.path);params=parse_qs(q.query)
        try:
            if q.path=='/api/bootstrap':return self.send_json({'token':TOKEN,'catalog':CATALOG,'messages':MESSAGE_NAMES,'tlvs':TLV_NAMES,'state':state(),'replays':list(REPLAYS)})
            if q.path=='/api/state':return self.send_json(state())
            if q.path=='/api/history':
                history=[]
                for filename in ('client-history.previous.jsonl','client-history.jsonl'):
                    path=BASE/'run'/filename
                    if not path.exists():continue
                    with path.open('rb') as f:
                        start=max(0,path.stat().st_size-1500000);f.seek(start)
                        if start:f.readline()
                        for line in f:
                            try:history.append(json.loads(line))
                            except ValueError:pass
                return self.send_json({'events':history[-2000:],'limit':2000})
            if q.path=='/api/speed':return self.send_json(speed_store.snapshot())
            if q.path=='/api/events':
                p=BASE/'events.jsonl';events=[];cursor=0
                if p.exists():
                    size=p.stat().st_size;start=params.get('cursor',['tail'])[0]
                    cursor=max(0,size-300000) if start=='tail' else max(0,min(size,int(start)))
                    with p.open('rb') as f:
                        f.seek(cursor)
                        if start=='tail' and cursor:f.readline()
                        for _ in range(350):
                            before=f.tell();line=f.readline()
                            if not line or not line.endswith(b'\n'):f.seek(before);break
                            try:events.append(json.loads(line))
                            except ValueError:pass
                        cursor=f.tell()
                return self.send_json({'events':events,'cursor':cursor})
            if q.path=='/api/commands':
                files=sorted((BASE/'results').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]
                return self.send_json([read_json(p,{}) for p in files])
            if q.path=='/api/replay':
                name=params.get('name',['onboarding'])[0]
                if name not in REPLAYS:raise ValueError('Unknown replay')
                if name not in REPLAY_CACHE:
                    from scapy.all import PcapReader
                    events=[]
                    with PcapReader(str(REPLAYS[name])) as packets:
                        for i,p in enumerate(packets):
                            try:d=decode_packet(bytes(p))
                            except ValueError:continue
                            events.append({'id':f'{name}-{i}','time':float(p.time),'event':'packet','packet':d,'direction':'TX' if d['src']==state().get('controller') else 'RX' if d['src']==state().get('target') else 'unknown','origin':'recorded','frame_number':i+1})
                    REPLAY_CACHE[name]=events
                return self.send_json({'events':REPLAY_CACHE[name],'name':name})
            if q.path=='/api/download':
                name=params.get('name',['onboarding'])[0]
                if name not in REPLAYS:raise ValueError('Unknown capture')
                return self.send_bytes(REPLAYS[name].read_bytes(),'application/octet-stream')
            files={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/topology.js':'topology.js','/speed.js':'speed.js','/telemetry.js':'telemetry.js','/learning.js':'learning.js'}
            if q.path not in files:return self.send_json({'error':'Not found'},404)
            file=BASE/'panel'/files[q.path]
            return self.send_bytes(file.read_bytes(),mimetypes.guess_type(file)[0] or 'text/plain')
        except (ValueError,TypeError,KeyError,OSError) as e:return self.send_json({'error':str(e)},400)
    def do_POST(self):
        if not self.allowed():return self.deny_access()
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+host for host in self.server.allowed_hosts}:
            return self.send_json({'error':'Invalid origin'},403)
        if self.headers.get('X-Lab-Token')!=TOKEN:return self.send_json({'error':'Refresh the panel session'},403)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=16384:raise ValueError('Invalid request size')
            req=json.loads(self.rfile.read(n))
            if self.path=='/api/speed/start':return self.send_json(speed_store.enqueue(req.get('session')),202)
            name=req['name'];params=req.get('params',{})
            validate(name,params)
            if self.path=='/api/preview':return self.send_json(preview(name,params))
            if self.path!='/api/commands':return self.send_json({'error':'Not found'},404)
            if not state()['controller_online']:return self.send_json({'error':'Controller is offline. No command queued.'},409)
            id=uuid.uuid4().hex;path=BASE/'commands'/f'{id}.json';tmp=path.with_suffix('.tmp')
            fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:json.dump({'name':name,'params':params,'created_at':time.time()},f)
            os.replace(tmp,path);return self.send_json({'id':id,'status':'queued'},202)
        except (ValueError,TypeError,KeyError,OSError) as e:return self.send_json({'error':str(e)},400)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765)
    p.add_argument('--bind',default='127.0.0.1')
    p.add_argument('--allow-client',action='append',default=[],help='Additional allowed client IP')
    p.add_argument('--host',action='append',default=[],help='Additional accepted hostname or IP')
    args=p.parse_args()
    server=ThreadingHTTPServer((args.bind,args.port),Handler)
    server.allowed_clients={'127.0.0.1',*args.allow_client}
    server.allowed_hosts={f'{host}:{args.port}' for host in ['127.0.0.1','localhost',*args.host]}
    print(f'Protocol lab listening on {args.bind}:{args.port}',flush=True)
    server.serve_forever()
