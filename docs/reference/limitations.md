# Limitations

[Documents](../README.md)

What the lab is not, and what its evidence does and does not show.

- Live testing covered a TP-Link RE653BE. Profile 1/2 advertisement is a lab persona, not a claim of conformance.
- Lower-band SSID provisioning worked. The agent did not supply a 6 GHz M1. A manually enabled 6 GHz BSS supported a Mac connection and local throughput test with onboarding replies paused. **Controller-based 6 GHz provisioning remains unverified.**
- No DPP, full MLO configuration or traffic separation. Wireless backhaul is limited to a fronthaul BSS that doubles as backhaul BSS, and further agents must be admitted by hand; see [a second extender](../guides/second-extender.md). Not yet tested live.
- Fragmented inbound CMDUs are rejected. Unknown TLVs remain visible as raw bytes.
- Agent topology is reported evidence, not independent RF capture. Speed tests measure browser payload throughput across the entire Ethernet/Wi-Fi path, not radio PHY speed.
- The panel is intended for an isolated/trusted lab. Host/client allowlists and a per-process request token are not user authentication or TLS. Loopback is the default.
- Raw captures and logs can contain client identities and sensitive protocol material. Runtime data is gitignored and is not included in this repository.
