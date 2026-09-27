#!/usr/bin/env python3
"""Small DHCPv4 service for the isolated speed-test subnet. No gateway or DNS."""
import json,os,socket,struct,time
from pathlib import Path
BASE=Path(__file__).resolve().parent;SERVER='10.203.88.1';INTERFACE=None;LEASE=3600
MAGIC=b'\x63\x82\x53\x63'
def options(raw):
 out={};i=240
 while i<len(raw):
  code=raw[i];i+=1
  if code==255:break
  if code==0:continue
  if i>=len(raw):raise ValueError('Truncated DHCP option')
  n=raw[i];i+=1
  if i+n>len(raw):raise ValueError('Truncated DHCP value')
  out[code]=raw[i:i+n];i+=n
 return out

def packet(raw,kind,ip):
 h=bytearray(236);h[0:4]=bytes([2,1,6,0]);h[4:12]=raw[4:12];h[16:20]=socket.inet_aton(ip);h[20:24]=socket.inet_aton(SERVER);h[28:44]=raw[28:44]
 opt=b'\x35\x01'+bytes([kind])+b'\x36\x04'+socket.inet_aton(SERVER)
 if kind!=6:opt+=b'\x01\x04\xff\xff\xff\x00'+b'\x33\x04'+struct.pack('!I',LEASE)+b'\x3a\x04'+struct.pack('!I',LEASE//2)+b'\x3b\x04'+struct.pack('!I',LEASE*7//8)
 return bytes(h)+MAGIC+opt+b'\xff'

def run():
 owner=(BASE/'config.json').stat()
 (BASE/'speed').mkdir(exist_ok=True)
 os.chown(BASE/'speed',owner.st_uid,owner.st_gid)
 os.chmod(BASE/'speed',0o700)
 leases={};blocked={};path=BASE/'speed/leases.json'
 if path.exists():
  try:leases=json.loads(path.read_text())
  except ValueError:pass
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,INTERFACE.encode()+b'\0');s.bind(('',67))
 print('Python DHCP listening on '+INTERFACE+'; no gateway/DNS advertised',flush=True)
 while True:
  raw,peer=s.recvfrom(4096)
  try:
   if len(raw)<240 or raw[:3]!=b'\x01\x01\x06' or raw[236:240]!=MAGIC or raw[24:28]!=b'\0'*4:continue
   opt=options(raw);kind=opt.get(53,b'')[0];now=time.time();mac=raw[28:34].hex(':')
   if opt.get(54,socket.inet_aton(SERVER))!=socket.inet_aton(SERVER):continue
   leases={m:l for m,l in leases.items() if l['expires']>now};blocked={ip:t for ip,t in blocked.items() if t>now}
   used={l['ip'] for m,l in leases.items() if m!=mac}|set(blocked)
   if kind in (4,7):
    old=leases.pop(mac,None)
    if kind==4 and old:blocked[old['ip']]=now+600
   elif kind in (1,3):
    requested=socket.inet_ntoa(opt[50]) if len(opt.get(50,b''))==4 else socket.inet_ntoa(raw[12:16])
    pool=[f'10.203.88.{i}' for i in range(100,200)]
    if kind==3 and (requested not in pool or requested in used):
     if 54 in opt:s.sendto(packet(raw,6,'0.0.0.0'),('255.255.255.255',68))
     continue
    ip=requested if requested in pool and requested not in used else leases.get(mac,{}).get('ip')
    if not ip:ip=next((ip for ip in pool if ip not in used),None)
    if not ip:continue
    leases[mac]={'ip':ip,'expires':now+(LEASE if kind==3 else 60),'status':'bound' if kind==3 else 'offered','hostname':opt.get(12,b'').decode('utf8','replace')[:80],'updated_at':now}
    s.sendto(packet(raw,5 if kind==3 else 2,ip),('255.255.255.255',68));print(json.dumps({'event':'ack' if kind==3 else 'offer','mac':mac,'ip':ip}),flush=True)
   else:continue
   tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(leases));os.chown(tmp,owner.st_uid,owner.st_gid);os.chmod(tmp,0o600);os.replace(tmp,path)
  except (ValueError,IndexError,OSError) as e:print(type(e).__name__+': '+str(e),flush=True)
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--interface',required=True)
 INTERFACE=parser.parse_args().interface
 run()
