# EasyMesh Protocol Lab

A Python IEEE 1905.1 / EasyMesh controller with a browser teaching panel. Inspect packets and TLVs, follow message IDs, draw topology, send protocol commands, and compare requested configuration with what an agent actually reports.

This is an experimental **single-agent** lab, not a certified or complete EasyMesh controller. It uses Python for the protocol and services, and vanilla JavaScript/HTML/CSS for the panel. Linux raw sockets require root for live operation; offline tests and the panel do not.

## Features

- Discovery, topology, AP capabilities, and WSC M1/M2 credential exchange.
- 2.4/5 GHz WPA2 provisioning, SSID changes, and re-onboarding.
- Opt-in experimental 6 GHz WPA3-SAE M2 encoding and Profile 2 advertisement.
- Packet timeline with decoded TLVs, raw hex, MID correlation, and command previews.
- Spring-layout topology with expandable radio/BSS nodes and client observations.
- Command actions for metrics, beacon queries, channel selection, steering, policy and raw TLVs. Device support varies; an ACK is not proof that an action took effect.
- Local browser speed tests initiated by the client or the controller panel. These require an open cooperating browser; IEEE 1905.1 cannot make an arbitrary client run this application test.
- Optional Python DHCP server, isolated network namespace, and independent full Ethernet capture.

## Build the LXD lab

Use the host checkout to [build a fresh VM](deploy/lxd-vm/README.md), including
the controller, panel, capture services and OpenSpeedTest. On rev120 the source
checkout is `/home/rev/easymesh-lab`; the VM runs its deployed copy at
`/opt/easymesh-lab`.

## Quick start: offline

Python 3.10 or newer:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -v test_wsc test_controller test_protocol test_speed test_telemetry test_optimizer
.venv/bin/python panel_server.py
```

Open http://127.0.0.1:8765. A fresh checkout has no live agent, credentials, or recorded captures. The unit tests use synthetic identities and a synthetic M1, including duplicate vendor extensions; they do not send network packets or require root.

Optional browser validation (starts its own loopback panel, without a device):

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tools/smoke_panel.py
```

For physical setup and migration to another host, follow [SETUP.md](docs/SETUP.md). The lab's client subnet is currently fixed at **10.203.88.0/24** and must not overlap another network on the lab host. Only the explicitly selected USB Ethernet interface goes into the isolated namespace.

## Learn and operate

See [WORKBENCH.md](docs/WORKBENCH.md) for panel behavior and [EXPERIMENTS.md](docs/EXPERIMENTS.md) for observed RE653BE behavior, the 6 GHz limitation, DHCP findings, and USB throughput comparison.

```bash
# Creates private config.json with a random password and UUID.
.venv/bin/python controller.py init --ssid EasyMesh-Lab
# Set a new SSID, preserving the generated password.
.venv/bin/python controller.py set-ssid --ssid My-Lab
# Optional replacement password, read from a private local file.
.venv/bin/python controller.py set-ssid --ssid My-Lab --password-file /path/to/private-password.txt
```

Configuration changes normally trigger re-onboarding. To temporarily suppress onboarding responses and renews while observing manual device settings:

```bash
touch onboarding.paused
# Remove this marker to resume onboarding. No restart is needed.
rm onboarding.paused
```

This marker does not pause topology/metrics traffic. The panel's display pause and periodic-query pause are different controls.

## Limitations and evidence

- Live testing covered a TP-Link RE653BE. Profile 1/2 advertisement is a lab persona, not a claim of conformance.
- Lower-band SSID provisioning worked. The agent did not supply a 6 GHz M1. A manually enabled 6 GHz BSS supported a Mac connection and local throughput test with onboarding replies paused. **Controller-based 6 GHz provisioning remains unverified.**
- No DPP, full MLO configuration, traffic separation, wireless backhaul configuration, or multiple-agent management.
- Fragmented inbound CMDUs are rejected. Unknown TLVs remain visible as raw bytes.
- Agent topology is reported evidence, not independent RF capture. Speed tests measure browser payload throughput across the entire Ethernet/Wi-Fi path, not radio PHY speed.
- The panel is intended for an isolated/trusted lab. Host/client allowlists and a per-process request token are not user authentication or TLS. Loopback is the default.
- Raw captures and logs can contain client identities and sensitive protocol material. Runtime data is gitignored and is not included in this repository.

## Signal telemetry and optimizer

Client nodes include RCPI-derived signal bars, measurement age, and inferred device labels from DHCP/mDNS and cooperating browser hints. Missing RSSI/SNR stays explicitly unavailable. See [TELEMETRY.md](docs/TELEMETRY.md).

A controller-side [optimizer scaffold](docs/OPTIMIZER.md) evaluates measurements in advisory mode. Automatic steering is disabled; candidate measurements and multi-agent support remain prerequisites.

## Source map

| Files | Purpose |
| --- | --- |
| `controller.py`, `responder.py`, `wsc.py` | Raw Ethernet protocol and WSC crypto |
| `protocol.py`, `protocol_names.json`, `workbench.py` | TLVs, command recipes, evidence and queues |
| `panel_server.py`, `panel/` | Teaching panel and client speed-test page |
| `lab_dhcp.py`, `speed_server.py`, `speed_store.py` | Local IP service and throughput endpoint |
| `test_*.py` | Offline validation and synthetic fixtures |

Protocol references and publication notes are in [REFERENCES.md](docs/REFERENCES.md). No license has been selected yet; add your chosen license before granting reuse rights.

See [Single-extender experiments and the 1905.1 oscilloscope](docs/LEARNING-LAB.md) for supervised steering, persistent client history, guided TLV exercises, optimizer observation and 6 GHz diagnostics.

See [LXD VM deployment](deploy/lxd-vm/README.md) for native services, USB ownership, OpenSpeedTest, isolation and rollback.

USB Wi-Fi clients: see [managed client namespaces and iperf3](docs/USB-WIFI-CLIENTS.md).
