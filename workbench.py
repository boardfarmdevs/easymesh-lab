"""File-queue bridge between unprivileged local web panel and raw Ethernet controller."""
import json
import os
from pathlib import Path
import time
import uuid
from protocol import build_command, decode_packet, EXPECT, LOOKUP
from wsc import validate_config
from experiments import SteeringTracker, validate_steering, observe_onboarding
from client_telemetry import client_views

BASE=Path(__file__).resolve().parent

def atomic(path,value,gid=None,uid=None):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f);f.write('\n')
    if gid is not None:
        os.chown(tmp,-1 if uid is None else uid,gid);os.chmod(tmp,0o640 if uid is None else 0o600)
    os.replace(tmp,path)

class Workbench:
    def __init__(self,controller):
        self.c=controller;self.gid=controller.args.config.stat().st_gid
        self.pending={};self.workflows={};self.command_id=None;self.next_heartbeat=0
        self.auto_poll=True
        self.steering=SteeringTracker(self.emit,self.result);self.next_history=0
        owner=controller.args.config.stat()
        for name in ('commands','results'):
            directory=BASE/name;directory.mkdir(exist_ok=True)
            os.chown(directory,owner.st_uid,owner.st_gid);os.chmod(directory,0o700)
        self.path=BASE/'events.jsonl'
        self.stream=self.path.open('a',buffering=1)
        os.chown(self.path,-1,self.gid);os.chmod(self.path,0o640)
        self.emit('notice',message='Controller session started',session=uuid.uuid4().hex)
        for path in (BASE/'results').glob('*.json'):
            try:
                old=json.loads(path.read_text());steering=old.get('steering',{})
                if steering.get('outcome') in ('awaiting_evidence','awaiting_association'):
                    self.result(path.stem,steering={**steering,'outcome':'tracking_interrupted_by_restart'})
            except (OSError,ValueError):continue
    def emit(self,event,**data):
        record=dict(id=uuid.uuid4().hex,time=time.time(),event=event,**data)
        self.stream.write(json.dumps(record)+'\n')
        if event=='client_sample' or event.startswith('steering_'):
            path=BASE/'run'/'client-history.jsonl'
            path.parent.mkdir(exist_ok=True)
            # Bounded private history: retain one previous 8 MiB segment.
            if path.exists() and path.stat().st_size>8*1024*1024:
                os.replace(path,path.with_suffix('.previous.jsonl'))
            with path.open('a') as out:out.write(json.dumps(record)+'\n')
            os.chown(path,-1,self.gid);os.chmod(path,0o640)
    def result(self,id,**data):
        path=BASE/'results'/f'{id}.json'
        old=json.loads(path.read_text()) if path.exists() else {'id':id,'created_at':time.time()}
        old.update(data,updated_at=time.time());atomic(path,old,self.gid)
    def packet(self,direction,raw):
        try:decoded=decode_packet(raw)
        except ValueError:return
        command=self.command_id
        if direction=='RX':
            key=decoded['mid'];p=self.pending.get(key)
            if p and decoded['kind'] in p['expected'] and decoded['src']==self.c.args.target:
                command=p['id'];ack=decoded['kind']==0x8000
                self.result(command,status='acknowledged' if ack else 'response_received',response_type=decoded['kind'],response_mid=key,
                            note='Receipt only; inspect result TLVs to determine acceptance or outcome.')
                if not ack:self.pending.pop(key,None)
            self.c.state['last_agent_at']=time.time()
            latest=self.c.state.setdefault('observations',{})
            for t in decoded['tlvs']:
                if t['type'] in (0x83,0x84,0x85,0x8b,0x8e,0x8f,0x94,0x96,0x98,0x9c,0xa2,0xa3,0x9f,0xa7):
                    f=t['fields'];identity=f.get('radio',f.get('bssid',f.get('station','all')))
                    latest[f"{t['type']:02x}:{identity}"]={'type':t['type'],'fields':f,'time':time.time()}
        elif command:
            self.pending[decoded['mid']]={'id':command,'expected':EXPECT.get(decoded['kind'],[]),'time':time.time()}
            path=BASE/'results'/f'{command}.json';old=json.loads(path.read_text())
            mids=old.get('mids',[])+[decoded['mid']]
            self.result(command,status='sent',mids=mids)
        observe_onboarding(self.c.state,direction,decoded,time.time())
        self.steering.packet(direction,decoded,command,time.time())
        self.emit('packet',direction=direction,packet=decoded,command_id=command,origin='manual' if command else 'automatic')
    def tick(self):
        now=time.time()
        self.steering.tick(now)
        if now>=self.next_history:
            bands={k:v.get('rf_bands') for k,v in self.c.state.get('radios',{}).items()}
            for obs in self.c.state.get('observations',{}).values():
                if obs.get('type')==0x85:
                    f=obs['fields'];classes=[c['class'] for c in f.get('operating_classes',[])]
                    if any(131<=c<=137 for c in classes):bands[f['radio']]=8
                    elif any(115<=c<=130 for c in classes):bands[f['radio']]=2
                    elif any(81<=c<=84 for c in classes):bands[f['radio']]=1
            self.emit('client_sample',clients=client_views(self.c.state,now=now),bss=self.c.state.get('operational_bss',[]),radios=bands)
            self.next_history=now+15
        for mid,p in list(self.pending.items()):
            if now-p['time']>30:
                path=BASE/'results'/f"{p['id']}.json"
                old=json.loads(path.read_text()) if path.exists() else {}
                if old.get('status')=='sent' and p['expected']:self.result(p['id'],status='no_response',note='No matching response in 30 seconds. This does not prove the command is unsupported.')
                self.pending.pop(mid,None)
        for id,w in list(self.workflows.items()):
            current=self.c.state
            fresh=all(x.get('revision',0)>=w['revision'] for x in current.get('radios',{}).values())
            if fresh and current.get('radios') and current.get('status')=='ssid_confirmed_in_agent_topology' and current.get('desired_ssid')==w['ssid']:
                self.result(id,status='confirmed',note='Desired SSID confirmed in the agent operational BSS report.');self.workflows.pop(id)
            elif now-w['time']>180:
                self.result(id,status='unconfirmed',note='No confirmed SSID state within 180 seconds; inspect the WSC/topology timeline.');self.workflows.pop(id)
        for path in sorted((BASE/'commands').glob('*.json'))[:5]:
            id=path.stem
            if len(id)!=32 or any(x not in '0123456789abcdef' for x in id) or path.is_symlink():continue
            try:
                if path.stat().st_size>16384:raise ValueError('Command too large')
                req=json.loads(path.read_text());name=req['name'];params=req.get('params',{})
                if name not in LOOKUP:raise ValueError('Unknown command')
                self.result(id,name=name,status='processing',title=LOOKUP[name]['title'])
                if name in ('set_ssid','reonboard','enable_6ghz') and (BASE/'onboarding.paused').exists():
                    raise ValueError('Onboarding is paused to preserve the manual 6 GHz BSS; resume it deliberately before reconfiguration.')
                self.command_id=id
                if name in ('set_ssid','reonboard','enable_6ghz'):
                    config=dict(self.c.config)
                    if name=='enable_6ghz':config.update(enable_6ghz=True,controller_profile=2)
                    if name=='set_ssid':
                        config['ssid']=params.get('ssid','')
                        if params.get('password'):config['password']=params['password']
                    validate_config(config);config['revision']+=1
                    owner=self.c.args.config.stat();atomic(self.c.args.config,config,owner.st_gid,owner.st_uid)
                    self.c.config=config;self.c.cache.clear();self.c.state['status']='renew_requested'
                    self.c.renew();self.c.checkpoint()
                    self.workflows[id]={'revision':config['revision'],'ssid':config['ssid'],'time':now}
                    self.result(id,status='awaiting_onboarding',note='Renew sent; waiting for M1/M2 and operational BSS confirmation.')
                elif name=='polling':
                    if str(params.get('enabled')) not in ('true','false'):raise ValueError('enabled must be true or false')
                    self.auto_poll=params['enabled']=='true';self.result(id,status='applied',note='Automatic queries '+('enabled' if self.auto_poll else 'paused'))
                else:
                    if name=='steer':validate_steering(params,self.c.state,time.time())
                    for kind,body in build_command(name,params,self.c.state):self.c.send(kind,body)
                self.emit('command',command_id=id,name=name,title=LOOKUP[name]['title'])
            except (ValueError,KeyError,TypeError,OSError) as e:
                self.result(id,status='error',error=str(e));self.emit('command_error',command_id=id,error=str(e))
            finally:
                self.command_id=None;path.unlink(missing_ok=True)
        if now>=self.next_heartbeat:
            self.c.state['heartbeat_at']=now;self.c.state['auto_poll']=self.auto_poll
            self.c.checkpoint();self.next_heartbeat=now+3
