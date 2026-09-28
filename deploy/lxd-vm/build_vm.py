#!/usr/bin/env python3
"""Build a new dedicated VM from this checkout's committed HEAD; never replace a VM."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
OST_REV = 'f4263546f50694a154fdd27a03000390949068df'

def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def output(*args):
    return subprocess.check_output(args, text=True).strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True)
    p.add_argument('--host-ip', required=True)
    p.add_argument('--guest-ip', required=True)
    p.add_argument('--lab-mac', required=True, help='Permanent Ethernet adapter MAC')
    p.add_argument('--target', required=True, help='Agent AL MAC')
    p.add_argument('--controller-mac')
    p.add_argument('--allow-client', action='append', default=[])
    p.add_argument('--network', default='lxdbr0')
    p.add_argument('--pool', default='easymesh-lab-pool', help='Existing LXD storage pool')
    p.add_argument('--image', default='ubuntu:24.04', help='Ubuntu 24.04 VM image alias or fingerprint')
    p.add_argument('--nic-driver', choices=['r8152', 'cdc_ncm'], default='r8152')
    p.add_argument('--panel-port', type=int, default=8765)
    p.add_argument('--speed-port', type=int, default=8766)
    a = p.parse_args()
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9-]{0,62}', a.name):
        p.error('Invalid instance name')
    for mac in (a.lab_mac, a.target, a.controller_mac or a.lab_mac):
        if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', mac):
            p.error('MAC addresses must be lowercase colon-separated hex')
    for addr in (a.host_ip, a.guest_ip, *a.allow_client):
        ipaddress.IPv4Address(addr)
    if any(not 1024 <= port <= 65535 for port in (a.panel_port, a.speed_port)) or a.panel_port == a.speed_port:
        p.error('Use two distinct ports between 1024 and 65535')
    instances = json.loads(output('lxc', 'list', '--format=json'))
    if any(i['name'] == a.name for i in instances):
        p.error('Instance exists; choose a new name. Existing labs are never overwritten.')
    gateway = ipaddress.IPv4Interface(output('lxc', 'network', 'get', a.network, 'ipv4.address'))
    guest = ipaddress.IPv4Address(a.guest_ip)
    if guest not in gateway.network or guest in (gateway.ip, gateway.network.network_address, gateway.network.broadcast_address):
        p.error('Guest IP must be a usable address in the managed network')
    leases = json.loads(output('lxc', 'network', 'list-leases', a.network, '--format=json'))
    if any(lease.get('address') == a.guest_ip for lease in leases):
        p.error('Guest IP already appears in network leases; select an unused IP')
    output('lxc', 'storage', 'show', a.pool)
    if output('git', '-C', str(ROOT), 'status', '--porcelain'):
        p.error('Commit source changes first; build uses committed HEAD only')
    revision = output('git', '-C', str(ROOT), 'rev-parse', 'HEAD')
    print(f'Building {a.name} from {revision}; no USB devices will be attached.', flush=True)
    # Empty profile list prevents inheriting host-specific USB/NIC devices.
    run('lxc', 'init', a.image, a.name, '--vm', '--no-profiles', '--storage', a.pool,
        '--network', a.network, '-c', 'limits.cpu=4', '-c', 'limits.memory=4GiB',
        '-c', 'boot.autostart=false', '-d', 'root,size=48GiB')
    run('lxc', 'config', 'device', 'set', a.name, 'eth0', f'ipv4.address={a.guest_ip}')
    run('lxc', 'start', a.name)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if subprocess.run(['lxc', 'exec', a.name, '--', 'true'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            break
        time.sleep(3)
    else:
        raise SystemExit('Guest agent timeout; VM retained for inspection')
    def guest_run(*args):
        return run('lxc', 'exec', a.name, '--', *args)
    guest_run('cloud-init', 'status', '--wait')
    guest_run('env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'update')
    guest_run('env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', '--no-install-recommends',
              'python3-venv', 'python3-pip', 'nginx', 'wireshark-common', 'ethtool', 'usbutils',
              'nftables', 'git', 'rsync', 'curl', 'linux-image-generic', 'iw', 'wpasupplicant', 'iperf3')
    kernel = output('lxc', 'exec', a.name, '--', 'uname', '-r')
    guest_run('env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', '--no-install-recommends', f'linux-modules-extra-{kernel}')
    guest_run('mkdir', '-p', '/opt/easymesh-lab')
    with tempfile.TemporaryDirectory(prefix='easymesh-build-') as tmp:
        archive = str(Path(tmp) / 'source.tar')
        run('git', '-C', str(ROOT), 'archive', '--format=tar', f'--output={archive}', 'HEAD')
        run('lxc', 'file', 'push', archive, f'{a.name}/tmp/easymesh-source.tar')
    guest_run('tar', '-xf', '/tmp/easymesh-source.tar', '-C', '/opt/easymesh-lab')
    guest_run('rm', '/tmp/easymesh-source.tar')
    guest_run('git', 'clone', 'https://github.com/openspeedtest/Speed-Test.git', '/opt/openspeedtest')
    guest_run('git', '-C', '/opt/openspeedtest', 'checkout', '--detach', OST_REV)
    args = ['python3', '/opt/easymesh-lab/deploy/lxd-vm/configure_guest.py',
            '--init-config', '--lab-mac', a.lab_mac, '--target', a.target,
            '--host-ip', a.host_ip, '--guest-ip', a.guest_ip,
            '--management-gateway', str(gateway.ip), '--nic-driver', a.nic_driver,
            '--panel-port', str(a.panel_port)]
    if a.controller_mac:
        args += ['--controller-mac', a.controller_mac]
    for client in a.allow_client:
        args += ['--allow-client', client]
    guest_run(*args)
    manifest = json.dumps({'source_commit': revision, 'openspeedtest_commit': OST_REV, 'image': a.image}, indent=2) + '\n'
    run('lxc', 'exec', a.name, '--', 'tee', '/opt/easymesh-lab/BUILD.json', input=manifest, text=True)
    for name, port, destination in [('lab-panel', a.panel_port, a.panel_port), ('lab-openspeedtest', a.speed_port, 3000)]:
        run('lxc', 'config', 'device', 'add', a.name, name, 'proxy', 'nat=true',
            f'listen=tcp:{a.host_ip}:{port}', f'connect=tcp:{a.guest_ip}:{destination}')
    guest_run('systemctl', 'start', 'easymesh-panel.service')
    print(f'Built {a.name}. Panel: http://{a.host_ip}:{a.panel_port}/')
    print('Onboarding paused; VM autostart off; physical USB handover is a separate step. See deploy/lxd-vm/README.md.')

if __name__ == '__main__':
    main()
