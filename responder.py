#!/usr/bin/env python3
"""Minimal 1905 discovery responder. No WSC M2/provisioning implementation."""
import argparse
import json
import signal
import socket
import struct
import time
from datetime import datetime, timezone

MULTICAST = '01:80:c2:00:00:13'

def macbytes(s):
    return bytes.fromhex(s.replace(':', ''))

def macstr(b):
    return ':'.join(f'{x:02x}' for x in b)

def tlv(kind, value):
    return struct.pack('!BH', kind, len(value)) + value

def parse(frame):
    if len(frame) < 22 or frame[12:14] != b'\x89\x3a':
        return None
    version, reserved, kind, mid, frag, flags = struct.unpack('!BBHHBB', frame[14:22])
    if version != 0 or frag != 0 or not flags & 0x80:
        raise ValueError('unsupported version or fragmented CMDU')
    values = {}; pos = 22
    while pos + 3 <= len(frame):
        t, n = struct.unpack('!BH', frame[pos:pos+3]); pos += 3
        if pos + n > len(frame):
            raise ValueError('truncated TLV')
        if t == 0:
            if n != 0:
                raise ValueError('invalid EOM')
            return dict(src=macstr(frame[6:12]), dst=macstr(frame[:6]), kind=kind,
                        mid=mid, flags=flags, tlvs=values)
        values.setdefault(t, []).append(frame[pos:pos+n]); pos += n
    raise ValueError('missing EOM')

def response(frame, controller, target, enable_6ghz=False, profile=1):
    msg = parse(frame)
    if not msg or msg['src'] != target or msg['kind'] != 7:
        return None
    if msg['dst'] not in (MULTICAST, controller):
        return None
    v = msg['tlvs']
    if any(len(v.get(k, [])) != 1 for k in (1, 13, 14, 0x81)):
        return None
    if v[1][0] != macbytes(target) or v[13][0] != b'\x00':
        return None
    band = v[14][0]
    services = v[0x81][0]
    if band not in ((b'\x00',b'\x01',b'\x03') if enable_6ghz else (b'\x00',b'\x01')) or not services:
        return None
    if services[0] != len(services)-1 or 0 not in services[1:]:
        return None
    # Laboratory persona; source Ethernet MAC is controller AL MAC.
    body = (tlv(0x0f, b'\x00') + tlv(0x10, band) +
            tlv(0x80, b'\x01\x00') + tlv(0xb3, bytes([profile])) + tlv(0, b''))
    header = struct.pack('!BBHHBB', 0, 0, 8, msg['mid'], 0, 0x80)
    out = macbytes(target) + macbytes(controller) + b'\x89\x3a' + header + body
    return out.ljust(60, b'\x00')

def log(event, **fields):
    print(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), event=event, **fields)), flush=True)

def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--interface', default=None)
    a.add_argument('--target', default=None)
    a.add_argument('--controller', default=None)
    a.add_argument('--replay'); a.add_argument('--output')
    args = a.parse_args()
    if not args.target:raise SystemExit('--target is required')
    if args.replay and not args.controller:raise SystemExit('--controller is required for replay')
    if args.replay:
        from scapy.all import PcapReader, wrpcap, Ether
        packets = []
        with PcapReader(args.replay) as reader:
            for p in reader:
                out = response(bytes(p), args.controller, args.target)
                if out:
                    packets.append(Ether(out))
        if not packets:
            raise SystemExit('No matching searches in replay')
        wrpcap(args.output, packets)
        log('offline_validation', generated_responses=len(packets), output=args.output)
        return
    if not args.interface:raise SystemExit('--interface is required')
    actual = open('/sys/class/net/' + args.interface + '/address').read().strip()
    if args.controller is None:args.controller=actual
    if actual != args.controller:
        raise SystemExit('Controller MAC must match interface MAC')
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x893a))
    s.bind((args.interface, 0)); s.settimeout(1)
    # Receive the 1905 multicast group without relying on dumpcap promiscuity.
    membership = struct.pack('IHH8s', socket.if_nametoindex(args.interface), 0, 6, macbytes(MULTICAST))
    s.setsockopt(263, 1, membership)
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    last = {}
    log('ready', interface=args.interface, target=args.target, controller=args.controller,
        profile=1, scope='discovery responses only; no WSC M2 or credentials')
    try:
        while running:
            try:
                frame, address = s.recvfrom(65535)
            except socket.timeout:
                continue
            if address[2] == socket.PACKET_OUTGOING:
                continue
            try:
                msg = parse(frame)
                if not msg or msg['src'] != args.target:
                    continue
                log('rx', kind=f"0x{msg['kind']:04x}", mid=msg['mid'], src=msg['src'],
                    tlvs={f'0x{k:02x}': [x.hex() for x in vals] for k, vals in msg['tlvs'].items()})
                out = response(frame, args.controller, args.target)
                if out:
                    band = msg['tlvs'][14][0][0]; now = time.monotonic()
                    if now - last.get(band, -100) < 1:
                        continue
                    s.send(out); last[band] = now
                    log('tx_autoconfig_response', mid=msg['mid'], band=band, frame_hex=out.hex())
                if msg['kind'] == 9:
                    log('wsc_received', note='Recorded only; no M2 sent')
            except ValueError as exc:
                log('parse_rejected', reason=str(exc))
    finally:
        s.close(); log('stopped')

if __name__ == '__main__':
    main()
