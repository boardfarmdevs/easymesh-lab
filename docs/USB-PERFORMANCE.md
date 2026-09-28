# USB client performance findings

Observed 2026-09-28 with two MT7925U USB Wi-Fi clients, a Realtek 2.5 GbE adapter, an Ubuntu LXD VM, and a TP-Link RE653BE. These are single-lab observations, not product benchmarks.

## Discovery-related interruptions

Ethernet carrier and wireless associations repeatedly dropped after the controller's periodic discovery/response exchange. With the controller stopped, periodic drops ceased. A single topology discovery with no responder did not cause a drop within 24 seconds; with the controller responding, another discovery caused a drop after approximately 12 seconds. Suppressing announcements while retaining normal queries stopped the periodic pattern. The exact incompatible field/behavior has not been isolated; this does not establish a firmware defect.

`--discovery-interval 0` is an explicit diagnostic workaround for an already known agent. The default remains 60 seconds. It changes normal discovery behavior and is not a general substitute for standards-compliant discovery. Preserve this distinction when comparing implementations.

## Guest versus host

The same physical Wi-Fi adapter on 6 GHz / 160 MHz / WPA3-SAE measured approximately 74/65 Mbps download/upload inside the VM with capture disabled, versus 739/446 Mbps directly on the host using the same wired VM iperf endpoint. Four TCP streams, 20 measured seconds, two-second warmup omitted. The host and guest environments differ, so this does not isolate virtualization from every driver/scheduling difference. Host upload still had substantial TCP retransmissions.

Upgrading the guest from 6.8.0-142 to 7.0.0-34 produced about 72/43 Mbps for client A and 68/43 Mbps for client B. Another lab/browser workload was active on the host and the guest recorded roughly 15–22% CPU steal in several tests. These measurements are not a clean causal kernel comparison. Both environments reported the same MT7925 firmware build (20260605184805).

The new-kernel client-to-client test stalled, with repeated virtual xHCI `Event dma ... status 13 not part of TD` errors. Association remained reported while traffic failed. The exact kernel/QEMU/scheduling cause is unresolved. The lab was returned to 6.8.0-142 and client communication, panel, capture and WPA3 associations were verified.

The tested lab keeps both kernels installed and selects the older one through `/etc/default/grub.d/99-easymesh-tested-kernel.cfg`. Remove that local override and run `update-grub` to resume selection of the newest installed kernel. This is local diagnostic state, not a recommended permanent version pin for deployments.

Next: repeat on an idle host and isolate the individual-device USB passthrough path; separately minimize the controller/agent exchange that triggers resets. Capture-off testing alone did not restore throughput. Keep TCP goodput, PHY rate, client-side signal, AP-side RCPI and reported association state separate.
