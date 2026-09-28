#!/usr/bin/env python3
"""Install persistent lab services inside a dedicated Ubuntu LXD VM.

Run as root after copying the complete live checkout to /opt/easymesh-lab.
This does not move host devices or start onboarding.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import subprocess

BASE=Path('/opt/easymesh-lab')
def run(*args):subprocess.run(args,check=True)
def write(path,text,mode=0o644):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(mode)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--lab-mac',required=True);p.add_argument('--target',required=True)
    p.add_argument('--host-ip',required=True);p.add_argument('--guest-ip',required=True)
    p.add_argument('--allow-client',action='append',default=[])
    p.add_argument('--management-gateway',default='10.77.171.1')
    p.add_argument('--controller-mac',help='Optional runtime MAC; lab-mac remains the physical MAC')
    p.add_argument('--nic-driver',choices=['cdc_ncm','r8152'],default='r8152')
    p.add_argument('--panel-port',type=int,default=8765)
    p.add_argument('--init-config',action='store_true',help='Generate fresh credentials and pause onboarding')
    a=p.parse_args()
    if not 1024 <= a.panel_port <= 65535:p.error('Invalid panel port')
    if os.geteuid()!=0:raise SystemExit('Run as root inside the dedicated VM')
    for m in (a.lab_mac,a.target,a.controller_mac or a.lab_mac):
        if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',m):raise SystemExit('Invalid MAC address')
    for ip in (a.host_ip,a.guest_ip,a.management_gateway,*a.allow_client):ipaddress.IPv4Address(ip)
    if not (BASE/'config.json').exists() and not a.init_config:raise SystemExit('Supply private config or use --init-config')
    try:pwd.getpwnam('easymesh')
    except KeyError:run('useradd','--system','--create-home','--home-dir','/var/lib/easymesh','--shell','/bin/bash','easymesh')
    for name in ('run/captures','commands','results','speed'):(BASE/name).mkdir(parents=True,exist_ok=True)
    run('chown','-R','easymesh:easymesh',str(BASE))
    run('modinfo',a.nic_driver)  # Cloud images need linux-modules-extra for this USB NIC.
    run('modprobe',a.nic_driver)
    run('python3','-m','venv',str(BASE/'.venv'))
    run(str(BASE/'.venv/bin/pip'),'install','-r',str(BASE/'requirements.txt'))
    if not (BASE/'config.json').exists():
        run(str(BASE/'.venv/bin/python'),str(BASE/'controller.py'),'init')
        (BASE/'onboarding.paused').touch(mode=0o600)
    (BASE/'config.json').chmod(0o600)
    run('chown','-R','easymesh:easymesh',str(BASE))
    # The dedicated USB NIC is optional during boot; management remains reachable.
    write('/etc/netplan/90-easymesh-lab.yaml',f'''network:
  version: 2
  ethernets:
    lab0:
      match:
        macaddress: "{a.lab_mac}"
      set-name: lab0
      macaddress: "{a.controller_mac or a.lab_mac}"
      addresses: [10.203.88.1/24]
      dhcp4: false
      dhcp6: false
      accept-ra: false
      link-local: []
      optional: true
''',0o600)
    write('/etc/sysctl.d/90-easymesh-isolation.conf','net.ipv4.ip_forward=0\nnet.ipv6.conf.all.forwarding=0\n')
    run('sysctl','-p','/etc/sysctl.d/90-easymesh-isolation.conf')
    write('/etc/easymesh-isolation.nft','''table inet easymesh_isolation {
 chain forward { type filter hook forward priority -10; policy drop; }
 chain input { type filter hook input priority -10; policy accept;
  iifname "lab0" meta nfproto ipv6 drop
  iifname "lab0" ip protocol icmp accept
  iifname "lab0" tcp dport { 3000, 8080 } accept
  iifname "lab0" drop
 }
}
''')
    write('/etc/systemd/system/easymesh-isolation.service','''[Unit]
Description=Keep lab clients isolated from VM management and internet
Before=easymesh-lab.target
[Service]
Type=oneshot
ExecStartPre=-/usr/sbin/nft delete table inet easymesh_isolation
ExecStart=/usr/sbin/nft -f /etc/easymesh-isolation.nft
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
''')
    write('/etc/easymesh-lab.env',f'TARGET={a.target}\n',0o600)
    # Restart-on-failure covers delayed USB discovery and unplug/replug.
    write('/usr/local/libexec/easymesh-wait-link','''#!/usr/bin/python3
import json,subprocess,time
for _ in range(30):
 r=subprocess.run(['ip','-j','addr','show','dev','lab0'],capture_output=True,text=True)
 if r.returncode==0 and any(a.get('local')=='10.203.88.1' for i in json.loads(r.stdout) for a in i.get('addr_info',[])):break
 time.sleep(1)
else:raise SystemExit('Waiting for lab0 with 10.203.88.1')
''',0o755)
    units={
      'controller':('root',f'{BASE}/.venv/bin/python -u {BASE}/controller.py run --interface lab0 --target ${{TARGET}}',True),
      'observer':('root',f'{BASE}/.venv/bin/python -u {BASE}/device_observer.py --interface lab0',True),
      'speed':('easymesh',f'{BASE}/.venv/bin/python -u {BASE}/speed_server.py',True),
      'capture':('easymesh',f'/usr/bin/dumpcap -q -i lab0 -s 0 -b filesize:65536 -b files:32 -g -w {BASE}/run/captures/wired.pcapng',True),
      'panel':('easymesh',f'{BASE}/.venv/bin/python -u {BASE}/panel_server.py --bind 0.0.0.0 --port {a.panel_port} --host {a.host_ip} --host {a.guest_ip} --host rev120 --host easymesh-lab '+ ' '.join('--allow-client '+ip for ip in sorted(set([a.host_ip,a.guest_ip,a.management_gateway,*a.allow_client]))),False)
    }
    for name,(user,command,needs_link) in units.items():
        write(f'/etc/systemd/system/easymesh-{name}.service',f'''[Unit]
Description=EasyMesh {name}
After=network-online.target easymesh-isolation.service
Requires=easymesh-isolation.service
PartOf=easymesh-lab.target
StartLimitIntervalSec=0
[Service]
Type=simple
User={user}
Group=easymesh
WorkingDirectory={BASE}
EnvironmentFile=/etc/easymesh-lab.env
UMask=0027
{("AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN" + chr(10) + "CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN" + chr(10) + "NoNewPrivileges=true" if name=="capture" else "")}
{('ExecStartPre=/usr/local/libexec/easymesh-wait-link' if needs_link else '')}
ExecStart={command}
Restart=always
RestartSec=5
TimeoutStopSec=15
[Install]
WantedBy=easymesh-lab.target
''')
    write('/etc/systemd/system/easymesh-lab.target','''[Unit]
Description=EasyMesh protocol teaching lab
Wants=easymesh-controller.service easymesh-observer.service easymesh-speed.service easymesh-capture.service easymesh-panel.service nginx.service
After=network-online.target easymesh-isolation.service
Requires=easymesh-isolation.service
[Install]
WantedBy=multi-user.target
''')
    write('/etc/nginx/sites-available/openspeedtest','''server {
 listen 3000;
 server_name _;
 root /opt/openspeedtest;
 index index.html;
 client_max_body_size 35m;
 client_body_timeout 120s;
 send_timeout 120s;
 access_log off;
 gzip off;
 server_tokens off;
 sendfile on;
 tcp_nodelay on;
 error_page 405 =200 $uri;
 location / {
  add_header Cache-Control "no-store, no-cache, max-age=0, no-transform" always;
  add_header Access-Control-Allow-Origin "*" always;
  add_header Access-Control-Allow-Methods "GET, HEAD, POST, OPTIONS" always;
  add_header Access-Control-Allow-Headers "Content-Type, Cache-Control" always;
  etag off;
  if_modified_since off;
  if ($request_method = OPTIONS) { return 200; }
  try_files $uri $uri/ =404;
 }
}
''')
    default=Path('/etc/nginx/sites-enabled/default')
    if default.is_symlink():default.unlink()
    link=Path('/etc/nginx/sites-enabled/openspeedtest')
    if not link.exists():link.symlink_to('/etc/nginx/sites-available/openspeedtest')
    run('nginx','-t')
    run('netplan','apply')
    run('systemctl','daemon-reload')
    run('systemctl','enable','easymesh-isolation.service','easymesh-lab.target','nginx.service')
    run('systemctl','start','easymesh-isolation.service')
    run('systemctl','restart','nginx.service')
    print('Guest configured. Start easymesh-lab.target only after exclusive NIC handover.')
if __name__=='__main__':main()
