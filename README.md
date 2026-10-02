# easymesh-lab: the EasyMesh protocol on certified hardware

<!-- labs block: the same in every repository of the EasyMesh labs, but for the Site line -->
**Site:** <https://vcpe.dev/easymesh-lab/>
The [EasyMesh labs](https://mesh.vcpe.dev/) serve three
goals: EasyMesh optimizer development
([easymesh-optimizer](https://vcpe.dev/easymesh-optimizer/)) in a rich
virtual lab, on both stacks
([RDK EasyMesh](https://vcpe.dev/meta-cmf-bananapi-vcpe/),
[prplMesh](https://vcpe.dev/prplmesh-lab/)); unchanged OpenSync
pods as EasyMesh agents under a local controller, without the OpenSync cloud
([EMOSA](https://vcpe.dev/emosa-lab/), with the
[OpenSync lab](https://vcpe.dev/opensync-lab/)'s pods); and
EasyMesh on physical hardware
([Protocol lab](https://vcpe.dev/easymesh-lab/)). Two core
components carry them: the RF medium
([easymesh-medium](https://vcpe.dev/easymesh-medium/)) and EMOSA's
OVSDB ⇄ EasyMesh conversion. The rest is infrastructure, tools (the
[room builder](https://vcpe.dev/easymesh-room-builder/)) and learning
around them.
<!-- /labs block -->

A from-scratch Python IEEE 1905.1 / EasyMesh controller with a browser teaching panel,
driving real extenders (a TP-Link RE653BE, a second extender on its wireless backhaul)
and real clients. Inspect packets and TLVs, follow message IDs, draw the topology, send
protocol commands, and compare the configuration you asked for with what an agent
reports. It is an experimental multi-agent lab, not a certified or complete EasyMesh
controller ([its limitations](docs/reference/limitations.md)).

- Discovery, topology, AP capabilities, and WSC M1/M2 credential exchange.
- 2.4/5 GHz WPA2 provisioning, SSID changes, and re-onboarding.
- Opt-in experimental 6 GHz WPA3-SAE M2 encoding and Profile 2 advertisement.
- Packet timeline with decoded TLVs, raw hex, MID correlation, and command previews.
- Spring-layout topology with expandable radio/BSS nodes and client observations.
- Command actions for metrics, beacon queries, channel selection, steering, policy and raw TLVs. Device support varies; an ACK is not proof that an action took effect.
- Local browser speed tests initiated by the client or the controller panel. These require an open cooperating browser; IEEE 1905.1 cannot make an arbitrary client run this application test.
- Optional Python DHCP server, isolated network namespace, and independent full Ethernet capture.

## Components

| Part | What it is |
| --- | --- |
| `controller.py`, `responder.py`, `wsc.py` | the raw-Ethernet protocol and the WSC crypto |
| `protocol.py`, `protocol_names.json`, `workbench.py` | TLVs, command recipes, evidence and queues |
| `optimizer.py`, `experiments.py`, `client_telemetry.py`, `device_observer.py` | the advisory optimizer, the experiments, client telemetry and passive device hints |
| `panel_server.py`, [panel/](panel) | the teaching panel and the client speed-test page |
| `lab_dhcp.py`, `speed_server.py`, `speed_store.py` | the local IP service and the throughput endpoint |
| [deploy/lxd-vm/](deploy/lxd-vm/README.md) | the lab VM: build, native services, USB ownership, OpenSpeedTest, isolation and rollback |
| [tools/](tools) | the panel's browser smoke tests and the USB Wi-Fi client manager |
| [tests/](tests) | offline tests with synthetic identities and fixtures |
| [site/](site) | the explainer site |

Python 3.10 or newer for the protocol and services, vanilla JavaScript, HTML and CSS for
the panel. Live operation needs root for the raw sockets; the offline tests and the panel
do not. No license has been selected yet; add one before granting reuse rights.

## Getting started

Offline, without a device:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python panel_server.py            # http://127.0.0.1:8765
```

A fresh checkout has no live agent, credentials or recorded captures; the tests use
synthetic identities and a synthetic M1, send no packets and need no root. Browser
validation starts its own loopback panel:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tools/smoke_panel.py
```

With hardware: [build the lab VM](deploy/lxd-vm/README.md) on a Linux LXD host (it runs
its deployed copy at `/opt/easymesh-lab`), or follow the
[physical setup](docs/guides/physical-setup.md) on a host directly. The lab's client
subnet is fixed at **10.203.88.0/24** and must not overlap another network on the host;
only the selected USB Ethernet interface goes into the isolated namespace.

## Documentation

The [site](https://vcpe.dev/easymesh-lab/) explains the lab and the protocol
it teaches. The documents are indexed in [docs/README.md](docs/README.md): the teaching
panel, the experiments, a second extender, USB Wi-Fi clients, client telemetry, the
optimizer, the references and the recorded findings.
