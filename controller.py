#!/usr/bin/env python3
"""Single-agent Python EasyMesh lab controller: discovery, WSC, topology and renew."""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import struct
import time
import uuid
from responder import parse, response, tlv, macbytes, macstr, log, MULTICAST
from wsc import build_m2, inspect_m1, validate_config
from workbench import Workbench
from protocol import decode_value

BASE=Path(__file__).resolve().parent
ONBOARDING_PAUSE=BASE/'onboarding.paused'

def save(path,value):
    tmp=path.with_suffix(path.suffix+f'.{os.getpid()}.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as out:json.dump(value,out,indent=2); out.write('\n')
    os.replace(tmp,path)

def frame(src,dst,kind,mid,body=b'',flags=0x80):
    return (macbytes(dst)+macbytes(src)+b'\x89\x3a'+struct.pack('!BBHHBB',0,0,kind,mid,0,flags)+body+tlv(0,b'')).ljust(60,b'\0')

def operational_bss(value):
    pos=1; result=[]
    if not value:raise ValueError('empty operational BSS')
    for _ in range(value[0]):
        if pos+7>len(value):raise ValueError('short radio')
        radio=macstr(value[pos:pos+6]); count=value[pos+6]; pos+=7
        for _ in range(count):
            if pos+7>len(value):raise ValueError('short BSS')
            bssid=macstr(value[pos:pos+6]); size=value[pos+6]; pos+=7
            if pos+size>len(value):raise ValueError('short SSID')
            result.append(dict(radio=radio,bssid=bssid,ssid=value[pos:pos+size].decode('utf8','replace'))); pos+=size
    if pos!=len(value):raise ValueError('extra operational BSS bytes')
    return result

class Controller:
    def __init__(self,args):
        self.lock=open(BASE/'controller.lock','w')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.args=args; self.config=json.loads(args.config.read_text()); validate_config(self.config)
        self.uuid=uuid.UUID(self.config['uuid']).bytes
        self.state={'controller':args.controller,'target':args.target,'profile':1,'radios':{},'operational_bss':[], 'status':'waiting_for_agent'}
        if args.state.exists():
            old=json.loads(args.state.read_text())
            if old.get('target')==args.target:
                self.state['radios']=old.get('radios',{})
                if old.get('onboarding_evidence'):self.state['onboarding_evidence']=old['onboarding_evidence']
        self.cache={}; self.last_response={}; self.next_query=0; self.next_discovery=0; self.next_client_metrics=0; self.client_poll_cursor=0
        self.mid=secrets.randbelow(65536); self.running=True; self.known=False
        self.sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(0x893a))
        self.sock.bind((args.interface,0)); self.sock.settimeout(1)
        self.sock.setsockopt(263,1,struct.pack('IHH8s',socket.if_nametoindex(args.interface),0,6,macbytes(MULTICAST)))
        self.workbench=Workbench(self)
    def send(self,kind,body=b'',mid=None,dst=None):
        if kind in (8,9,10) and ONBOARDING_PAUSE.exists():
            log('onboarding_tx_suppressed',kind=f'0x{kind:04x}'); return
        if mid is None:self.mid=(self.mid+1)&65535; mid=self.mid
        raw=frame(self.args.controller,dst or self.args.target,kind,mid,body)
        self.sock.send(raw)
        if hasattr(self,'workbench'):self.workbench.packet('TX',raw)
        log('tx',kind=f'0x{kind:04x}',mid=mid,bytes=len(raw))
    def checkpoint(self):
        self.state['onboarding_paused']=ONBOARDING_PAUSE.exists()
        self.state['desired_ssid']=self.config['ssid']; self.state['updated_at']=time.time()
        self.state['enable_6ghz']=self.config.get('enable_6ghz',False)
        self.state['profile']=self.config.get('controller_profile',1)
        self.state['interface']=self.args.interface
        save(self.args.state,self.state)
        os.chown(self.args.state, -1, self.args.config.stat().st_gid)
        os.chmod(self.args.state, 0o640)
    def topology(self,mid):
        mac=macbytes(self.args.controller)
        # Device Info: AL MAC, one Ethernet interface, IEEE 802.3ab gigabit media 0x0001.
        info=mac+b'\x01'+mac+b'\x00\x01\x00'
        self.send(3,tlv(3,info)+tlv(4,b'\x00')+tlv(7,mac+macbytes(self.args.target)+b'\x00')+tlv(0x80,b'\x01\x00')+tlv(0xb3,bytes([self.config.get('controller_profile',1)])),mid)
    def link_metrics(self,mid,query):
        if not query or query[0] not in (0,1):raise ValueError('invalid metric query')
        expected=2 if query[0]==0 else 8
        if len(query)!=expected:raise ValueError('invalid metric query length')
        if query[0]==1 and query[1:7]!=macbytes(self.args.target):
            self.send(6,tlv(0x0c,b'\x00'),mid); return
        direction=query[-1]
        if direction not in (0,1,2):raise ValueError('invalid metric direction')
        root=Path('/sys/class/net')/self.args.interface
        def counter(name):return int((root/'statistics'/name).read_text())&0xffffffff
        try:rate=max(0,min(65535,int((root/'speed').read_text())))
        except (ValueError,OSError):rate=0
        local=macbytes(self.args.controller); peer=macbytes(self.args.target)
        prefix=local+peer; interfaces=local+peer+b'\x00\x01'
        body=b''
        if direction in (0,2):
            # No throughput/availability measurement: encode zeros, actual PHY speed separately.
            body+=tlv(9,prefix+interfaces+struct.pack('!BIIHHH',0,counter('tx_errors'),counter('tx_packets'),0,0,rate))
        if direction in (1,2):
            body+=tlv(10,prefix+interfaces+struct.pack('!IIB',counter('rx_errors'),counter('rx_packets'),255))
        self.send(6,body,mid)

    def handle(self,raw):
        try:m=parse(raw)
        except ValueError:
            if hasattr(self,'workbench'):self.workbench.packet('unknown',raw)
            raise
        if not m or m['src']!=self.args.target or m['dst'] not in (MULTICAST,self.args.controller):
            if m and m['src']!=self.args.controller and hasattr(self,'workbench'):
                self.workbench.packet('unknown',raw)
            return
        self.known=True; v=m['tlvs']; kind=m['kind']
        if hasattr(self,'workbench'):self.workbench.packet('RX',raw)
        log('rx',kind=f'0x{kind:04x}',mid=m['mid'],tlvs={f'0x{k:02x}':[x.hex() for x in vals] for k,vals in v.items()})
        if kind in (7,9) and ONBOARDING_PAUSE.exists():
            log('onboarding_paused',kind=f'0x{kind:04x}',mid=m['mid'])
            self.checkpoint(); return
        if kind==7:
            out=response(raw,self.args.controller,self.args.target,self.config.get('enable_6ghz',False),self.config.get('controller_profile',1))
            if out:
                band=v[14][0][0]; now=time.monotonic()
                if now-self.last_response.get(band,-100)>=1:
                    self.sock.send(out); self.last_response[band]=now
                    if hasattr(self,'workbench'):self.workbench.packet('TX',out)
                    log('autoconfig_response',band=band,mid=m['mid'])
        elif kind==2:self.topology(m['mid'])
        elif kind==5:
            if len(v.get(8,[]))!=1:raise ValueError('missing metric query TLV')
            self.link_metrics(m['mid'],v[8][0])
        elif kind==9:
            if len(v.get(0x11,[]))!=1:raise ValueError('expected one WSC M1')
            m1=v[0x11][0]; a=inspect_m1(m1)
            radio_fields=v.get(0x85) or v.get(0x82)
            if not radio_fields or len(radio_fields[0])<6:raise ValueError('M1 lacks radio identity')
            radio=radio_fields[0][:6]; rid=macstr(radio)
            caps=decode_value(0x85,v[0x85][0]) if 0x85 in v else next((o['fields'] for o in self.state.get('observations',{}).values() if o.get('type')==0x85 and o['fields'].get('radio')==rid),{})
            known_six=any(131<=op['class']<=137 for op in caps.get('operating_classes',[])) or self.state['radios'].get(rid,{}).get('rf_bands')==8
            if known_six and a[0x103c][0]!=8:
                raise ValueError('6 GHz radio has inconsistent WSC RF band; refusing legacy credentials')
            key=hashlib.sha256(m1+radio+str(self.config['revision']).encode()).hexdigest()
            if key not in self.cache:
                self.cache[key]=build_m2(m1,self.config,self.uuid)
                if len(self.cache)>64:self.cache.pop(next(iter(self.cache)))
            m2=self.cache[key]
            self.send(9,tlv(0x82,radio)+tlv(0x11,m2))
            self.state['radios'][rid]={'rf_bands':a[0x103c][0], 'ssid_sent':self.config['ssid'],
                'security_sent':'WPA3-SAE' if a[0x103c][0]==8 else 'WPA2-PSK',
                'revision':self.config['revision'],'m2_sent_at':time.time(),
                'manufacturer':a.get(0x1021,b'').decode('utf8','replace'),
                'model':a.get(0x1023,b'').decode('utf8','replace')}
            self.state['status']='m2_sent_awaiting_operational_bss'; self.next_query=time.monotonic()+5
            log('m2_sent',radio=rid,ssid=self.config['ssid'],revision=self.config['revision'])
        elif kind==3:
            if 0x83 in v:
                bss=[]
                for value in v[0x83]:bss.extend(operational_bss(value))
                self.state['operational_bss']=bss
                configured=set(self.state['radios'])
                matched={x['radio'] for x in bss if x['ssid']==self.config['ssid']}
                six_sent={rid for rid,r in self.state['radios'].items() if r.get('rf_bands')==8 and r.get('revision')==self.config['revision']}
                six_expected={o['fields']['radio'] for o in self.state.get('observations',{}).values() if o.get('type')==0x85 and any(131<=c['class']<=137 for c in o['fields'].get('operating_classes',[]))}
                six_ok=not self.config.get('enable_6ghz',False) or bool(six_sent and six_sent<=matched and six_expected<=six_sent)
                self.state['six_ghz_bss_observed']=[x for x in bss if x['radio'] in six_expected or x['radio'] in six_sent]
                self.state['six_ghz_status']='confirmed_in_agent_topology' if self.config.get('enable_6ghz',False) and six_ok else 'bss_present_not_controller_confirmed' if self.state['six_ghz_bss_observed'] else 'awaiting_6ghz_bss' if self.config.get('enable_6ghz',False) else 'not_requested'
                if configured and configured<=matched and six_ok:
                    self.state['status']='ssid_confirmed_in_agent_topology'
                elif configured:
                    self.state['status']='m2_sent_awaiting_operational_bss'
                log('operational_bss',bss=bss,status=self.state['status'])
        elif kind==0x8002:
            self.state['capabilities_received_at']=time.time()
        elif kind==1:
            self.next_query=time.monotonic()+1
        self.checkpoint()
    def poll_client_metrics(self):
        report=self.state.get('observations',{}).get('84:all',{})
        if time.time()-report.get('time',0)>90:return
        stations=sorted({c['station'] for b in report.get('fields',{}).get('bss',[]) for c in b.get('clients',[])})
        # Bound each batch and rotate fairly for larger client sets.
        if not stations:return
        start=self.client_poll_cursor%len(stations)
        for i in range(min(8,len(stations))):
            self.send(0x800d,tlv(0x95,macbytes(stations[(start+i)%len(stations)])))
        self.client_poll_cursor=(start+8)%len(stations)

    def renew(self):
        for band in ((0,1,3) if self.config.get('enable_6ghz',False) else (0,1)):
            self.send(0x0a,tlv(1,macbytes(self.args.controller))+tlv(0x0f,b'\x00')+tlv(0x10,bytes([band])))
    def run(self):
        def stop(*_):self.running=False
        signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)
        log('controller_ready',ssid=self.config['ssid'],profile=self.config.get('controller_profile',1),scope='WPA2 on 2.4/5 GHz; optional experimental WPA3-SAE on 6 GHz',enable_6ghz=self.config.get('enable_6ghz',False))
        self.checkpoint()
        try:
            while self.running:
                now=time.monotonic()
                self.workbench.tick()
                # Atomic config updates trigger WSC renewal, not a direct SSID packet.
                try:
                    config=json.loads(self.args.config.read_text()); validate_config(config)
                    if config['revision']!=self.config['revision']:
                        self.config=config; self.cache.clear(); self.state['status']='renew_requested'
                        self.renew(); self.checkpoint(); log('config_reloaded',ssid=config['ssid'],revision=config['revision'])
                except (ValueError,KeyError) as e:log('config_rejected',reason=str(e))
                if getattr(self.args,'discovery_interval',60)>0 and now>=self.next_discovery:
                    mac=macbytes(self.args.controller)
                    self.send(0,tlv(1,mac)+tlv(2,mac),dst=MULTICAST); self.next_discovery=now+getattr(self.args,'discovery_interval',60)
                if self.workbench.auto_poll and self.known and now>=self.next_query:
                    self.send(2); self.send(0x8001); self.next_query=now+30
                if self.workbench.auto_poll and self.known and now>=self.next_client_metrics:
                    self.poll_client_metrics(); self.next_client_metrics=now+15
                try:
                    raw,addr=self.sock.recvfrom(65535)
                    if addr[2]!=socket.PACKET_OUTGOING:self.handle(raw)
                except socket.timeout:pass
                except ValueError as e:log('rejected',reason=str(e))
        finally:self.sock.close(); self.checkpoint(); log('controller_stopped')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','run','set-ssid','status'])
    p.add_argument('--config',type=Path,default=BASE/'config.json')
    p.add_argument('--state',type=Path,default=BASE/'state.json')
    p.add_argument('--interface',default=None)
    p.add_argument('--controller',default=None)
    p.add_argument('--target',default=None)
    p.add_argument('--discovery-interval',type=float,default=60,help='Topology discovery announcement interval in seconds; 0 disables announcements for interoperability diagnosis')
    p.add_argument('--ssid'); p.add_argument('--password-file',type=Path)
    a=p.parse_args()
    if a.command=='init':
        if a.config.exists():raise SystemExit('Config already exists')
        c=dict(ssid=a.ssid or 'EasyMesh-Lab',password=secrets.token_urlsafe(15),revision=1,uuid=str(uuid.uuid4()))
        if a.password_file:c['password']=a.password_file.read_text().rstrip('\n')
        validate_config(c); save(a.config,c); print(f'Created {a.config}; SSID {c["ssid"]}; password stored only in config')
    elif a.command=='set-ssid':
        c=json.loads(a.config.read_text())
        if not a.ssid:raise SystemExit('--ssid required')
        c['ssid']=a.ssid
        if a.password_file:c['password']=a.password_file.read_text().rstrip('\n')
        validate_config(c); c['revision']+=1; save(a.config,c); print('Config updated; running controller will renew onboarding')
    elif a.command=='status':print(a.state.read_text())
    else:
        if not a.interface or not a.target:raise SystemExit('run requires --interface and --target (agent AL MAC)')
        actual=Path('/sys/class/net',a.interface,'address').read_text().strip()
        if a.controller is None:a.controller=actual
        if actual!=a.controller:raise SystemExit('Interface MAC mismatch')
        Controller(a).run()

if __name__=='__main__':main()
