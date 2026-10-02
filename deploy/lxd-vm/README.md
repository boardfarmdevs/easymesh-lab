# LXD VM deployment

The complete lab runs in an Ubuntu 24.04 LXD virtual machine: controller,
web panel, observer, optimizer, history, ring capture, the cooperating-client
speed endpoint, and native nginx serving OpenSpeedTest. LXD on the host only
owns the VM, USB attachment and management port forwarding.

## Build from a clean host checkout

Clone this repository anywhere on the chosen host. Edit, test and commit
in that host checkout. `/opt/easymesh-lab` inside the VM is the deployed
runtime copy; new builds include committed source only, never host secrets,
captures, virtual environments or uncommitted changes. `BUILD.json` records
the source and OpenSpeedTest revisions. An existing VM is never overwritten.
The VM takes no automatic updates (the build masks apt's daily timers and holds
every snap): an unattended upgrade restarts services under a running lab.

Prerequisites: Linux with working LXD VM support, access to `lxc`, Python 3,
Git, a managed LXD bridge with DHCP, an existing storage pool, and internet
access for the build's Ubuntu/Python/OpenSpeedTest downloads. Network and storage pool names are explicit inputs, not assumed host defaults.
The default
image is Ubuntu 24.04; use `--image FINGERPRINT` to select an exact cached image.
Package repositories remain moving inputs; this is a reproducible procedure,
not a bit-identical image build. The lab subnet is fixed at 10.203.88.0/24.

For a new host, initialize LXD and select/create a bridge and pool appropriate
for that host. Inspect the resulting names with `lxc network list` and
`lxc storage list`; the builder does not change shared host networks:

```sh
lxd init
git clone https://github.com/boardfarmdevs/easymesh-lab.git
cd easymesh-lab
```

Select an unused management address and host ports, the host's own LAN IP,
the operator browser's IP, the Ethernet adapter's permanent MAC, and the
agent's AL MAC. Replace the uppercase placeholders below:

```sh
python3 deploy/lxd-vm/build_vm.py \
  --name mesh-lab --host-ip HOST_LAN_IP --guest-ip UNUSED_VM_IP \
  --network MANAGEMENT_BRIDGE --pool STORAGE_POOL \
  --lab-mac ADAPTER_MAC --target AGENT_AL_MAC \
  --allow-client BROWSER_IP
```

No specific host name, home directory, bridge name, pool name, USB adapter
model or management subnet is required. The gateway comes from the selected
LXD bridge. Normal kernel probing selects the USB driver; `--nic-driver r8152`
or `--nic-driver cdc_ncm` optionally verifies a known driver. Pass
`--controller-mac OLD_CONTROLLER_MAC` only when preserving a previous
controller identity while changing Ethernet adapters. Add `--panel-host DNS_NAME`
for any DNS aliases used in the browser. Repeat `--allow-client` for additional
operators. Use `--panel-port` and `--speed-port` when the default 8765/8766 ports
are occupied. The builder rejects an existing instance name and requires a
clean Git checkout. It attaches no host hardware automatically.

The builder creates a dedicated 4-vCPU/4-GiB/48-GiB VM, installs dependencies,
generates private credentials, configures isolation and services, installs
pinned OpenSpeedTest assets, and exposes the panel. USB devices are attached
only during the explicit handover below. Fresh onboarding is paused and VM
autostart is off. The runtime config is mode 0600; read it inside the guest
when you need the generated Wi-Fi password. A failed build remains available
for inspection; remove that new instance explicitly before retrying.

The guest installer also supports restoring a private `config.json` before
configuration; without `--init-config` it requires that file. It preserves
existing credentials and onboarding pause state. No DHCP server is started.

## Optional managed Wi-Fi clients

Follow [USB Wi-Fi clients](../../docs/guides/usb-wifi-clients.md) to install the
committed service and enroll specific adapter MACs in the private
`/etc/easymesh-wifi-clients.json`. USB attachment alone does not enroll a client.
The controller supports initial 2.4/5 GHz provisioning; the RE653BE's 6 GHz
configuration may still require its own UI. See [USB performance findings](../../docs/records/usb-performance.md).

## Cutover and exclusive ownership

Stop the identified host controller, panel, observer, speed endpoint and
capture gracefully. Back up their frozen files and hash the archive. Copy
that final archive to the guest before starting any guest lab writer.

Attach only the dedicated USB Ethernet adapter to the VM with LXD's `usb`
device type, using vendor ID, product ID **and serial**. For this deployment
USB ownership replaces the old host network namespace attachment. Check
`lsusb -t`, `ethtool lab0` and actual protocol exchange after handover; USB
passthrough is not an assurance of unchanged throughput.

```sh
lxc config device add VM extender-usb usb \
  vendorid=VENDOR productid=PRODUCT serial=SERIAL required=false
lxc exec VM -- systemctl start easymesh-lab.target
```

Configure LXD NAT proxy devices to the guest's static management address:
port 8765 for the panel, and host port 8766 to guest port 3000 for management
OpenSpeedTest. Preserve the existing panel hostname/ACL settings.

## Endpoints and service operation

- Panel: `http://HOST_LAN_IP:8765/`
- OpenSpeedTest **from a client joined to the extender**:
  `http://10.203.88.1:3000/?clean`
- OpenSpeedTest management-path test: `http://HOST_LAN_IP:8766/?clean`
- Existing cooperating-client endpoint: `http://10.203.88.1:8080/`

OpenSpeedTest is self-hosted and runs without client internet access. `clean`
disables upstream's default overhead adjustment. Its results appear in its
own page; they are not automatically ingested into the existing speed-job
history. The existing service remains available for controller-initiated
jobs with a cooperating browser. Tests through the management URL do **not**
measure the extender/client Wi-Fi path.

All runtime source and state live on the VM disk under `/opt/easymesh-lab`.
Services are `easymesh-{controller,panel,observer,speed,capture}.service`,
`easymesh-isolation.service` and `nginx.service`; the target is
`easymesh-lab.target`. View logs with `journalctl -u SERVICE`. The target is enabled; enable VM autostart after validation with
`lxc config set VM boot.autostart=true`. NIC-dependent services wait for the expected address and retry if
the USB adapter is temporarily absent. The panel remains reachable during
that wait. Onboarding is still paused if the migrated pause file exists.

New packet captures use `run/captures/`, with 32 files of up to 64 MiB each per invocation; files from earlier invocations are retained.
Migrated historical captures retain their original names under `run/`.
`events.jsonl` retains the existing event history; monitor disk usage over
long-running experiments. Guest IPv4/IPv6 forwarding is disabled and a
separate nftables forward chain drops forwarded traffic. `lab0` only exposes
ICMP, OpenSpeedTest and the cooperating-client endpoint at the IP layer.
IEEE 1905.1 remains raw Ethernet and is not routed into the management LAN.

## Validation and rollback

Verify all services, USB/link negotiation, incoming discovery and matched
query replies, preserved BSS/SSID state, growing captures, browser waveform
and experiments, OpenSpeedTest GET/POST/HEAD/OPTIONS, and a guest reboot.
Validate isolation separately from service reachability. A management-side
browser test validates software but does not substitute for a physical
Wi-Fi client test.

Keep the host archive and original checkout. To roll back, stop the guest
services, remove its management proxies and USB device, stop the VM, restore
the adapter to the original host namespace/address, and restart the exact
saved host commands. Do not run both controllers concurrently.

References: [LXD USB device](https://canonical.com/lxd/docs/latest/reference/devices_usb/),
[OpenSpeedTest](https://github.com/openspeedtest/Speed-Test),
[upstream nginx configuration](https://github.com/openspeedtest/Nginx-Configuration).
