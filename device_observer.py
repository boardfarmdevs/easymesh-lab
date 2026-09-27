#!/usr/bin/env python3
"""Passive DHCP/mDNS identity hints, limited to agent-reported client MACs."""
import argparse
import json
import os
import time
import threading
from pathlib import Path
from scapy.all import BOOTP, DHCP, DNS, Ether, UDP, AsyncSniffer

BASE = Path(__file__).resolve().parent


def text(value):
    if isinstance(value, bytes): value = value.decode('utf-8', 'replace')
    return ''.join(c for c in str(value) if c.isprintable())[:180]


def hints(packet, allowed):
    if Ether not in packet or UDP not in packet: return []
    mac = packet[Ether].src.lower()
    if mac not in allowed: return []
    found = []
    if DHCP in packet and BOOTP in packet and packet[BOOTP].op == 1:
        if packet[BOOTP].chaddr[:6].hex(':') != mac: return []
        for option in packet[DHCP].options:
            if isinstance(option, tuple) and option[0] in ('hostname', 'vendor_class_id'):
                found.append((mac, 'dhcp_hostname' if option[0]=='hostname' else 'dhcp_vendor', text(option[1])))
    if DNS in packet and packet[UDP].sport == 5353 and packet[UDP].dport == 5353 and packet[DNS].qr == 1:
        dns = packet[DNS]
        for section in (dns.an, dns.ns, dns.ar):
            for rr in section:
                name = text(rr.rrname).rstrip('.')
                if rr.type in (1, 28) and name.lower().endswith('.local'):
                    found.append((mac, 'mdns_hostname', name))
                if rr.type == 16 and '_device-info._tcp.local' in name.lower():
                    values = rr.rdata if isinstance(rr.rdata, list) else [rr.rdata]
                    for value in values:
                        value = text(value)
                        if value.lower().startswith('model='): found.append((mac, 'mdns_model', value[6:]))
    return found


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--interface',required=True)
    args=parser.parse_args();owner=(BASE/'config.json').stat();path=BASE/'run/device-evidence.json'
    path.parent.mkdir(exist_ok=True)
    records={};allowed=set();last_reload=0;lock=threading.Lock()
    def receive(packet):
        nonlocal allowed,last_reload
        now=time.time()
        if now-last_reload>2:
            try:
                state=json.loads((BASE/'state.json').read_text())
                report=state.get('observations',{}).get('84:all',{})
                allowed={c['station'] for b in report.get('fields',{}).get('bss',[]) for c in b.get('clients',[])} if now-report.get('time',0)<90 else set()
            except (OSError,ValueError): allowed=set()
            last_reload=now
        try:
            with lock:
                for mac,kind,value in hints(packet,allowed):
                    entry=records.setdefault(mac,{'evidence':[]});e=entry['evidence']
                    e[:]=[x for x in e if not(x['kind']==kind and x['value']==value) and now-x['time']<86400]
                    e.append({'kind':kind,'value':value,'time':now,'source':'Passive DHCP/mDNS on dedicated Ethernet'})
                    del e[:-20]
        except (ValueError,AttributeError,IndexError,TypeError): pass
    sniffer=AsyncSniffer(iface=args.interface,filter='udp port 67 or udp port 68 or udp port 5353',prn=receive,store=False)
    sniffer.start()
    try:
        while True:
            time.sleep(3)
            with lock:
                records={k:v for k,v in records.items() if any(time.time()-e['time']<86400 for e in v['evidence'])}
                snapshot=json.dumps(records)
            tmp=path.with_suffix('.tmp')
            fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as f:f.write(snapshot)
            os.chown(tmp,owner.st_uid,owner.st_gid);os.replace(tmp,path)
    finally:sniffer.stop()

if __name__=='__main__':main()
