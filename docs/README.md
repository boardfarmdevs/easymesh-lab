# The protocol lab's documents

[Repository](../README.md) · [Site](https://vcpe.dev/easymesh-lab/)

The [site](https://vcpe.dev/easymesh-lab/) explains the lab and the protocol
it teaches. These documents go further:

| Document | Kind | What it covers |
| --- | --- | --- |
| [Client telemetry](concepts/client-telemetry.md) | concept | signal bars from the agents' RCPI, passive device hints, what stays unavailable |
| [Optimizer](concepts/optimizer.md) | concept | the controller-side advisory optimizer: its gates and its execution boundary |
| [Physical setup](guides/physical-setup.md) | guide | the Ethernet adapter, credentials, the namespace, the services; moving to another host |
| [Teaching panel](guides/teaching-panel.md) | guide | the panel's views, pause controls, recorded sessions, speed measurements, 6 GHz |
| [Experiments](guides/experiments.md) | guide | supervised steering, client history, guided protocol exercises, optimizer observation, 6 GHz diagnostics |
| [A second extender](guides/second-extender.md) | guide | onboarding a second agent through the first, on a wireless backhaul; the open problem |
| [USB Wi-Fi clients](guides/usb-wifi-clients.md) | guide | managed USB Wi-Fi stations in their own namespaces, iperf3, 6 GHz / WPA3 |
| [Limitations](reference/limitations.md) | reference | what the lab is not, and what its evidence does and does not show |
| [References](reference/references.md) | reference | the protocol and implementation references, and what is not included |
| [RE653BE experiments](records/re653be-experiments.md) | record | observed RE653BE behaviour: onboarding, SSID changes, 6 GHz, DHCP, throughput |
| [USB performance](records/usb-performance.md) | record | the 28 September 2026 USB client findings: discovery interruptions, guest versus host |

The lab VM's build and operation are next to its code, in
[deploy/lxd-vm/README.md](../deploy/lxd-vm/README.md).
