# Teaching panel

[Documents](../README.md)

| View | Learning task |
| --- | --- |
| Live wire | Inspect CMDU headers, TLV boundaries, raw bytes, request/response MIDs |
| Command studio | Preview a command, send it, distinguish ACK from an actual response |
| Radios and telemetry | Compare capabilities, operational BSSs, client and link metrics |
| Topology | Expand controller → agent → radio → BSS → client; drag/pin nodes |
| Speed test | Register an open client browser, start a local transfer, inspect results |
| Learn / replay | Review a local capture and the protocol dictionary |

Unknown fields remain available as hex. Previews do not transmit. M2 credentials and authenticators cannot be previewed as actual wire bytes before receiving the enrollee M1.

A queued command is not success. `sent`, `acknowledged`, `response_received`, `no_response` and operational-SSID confirmation represent different evidence. A response does not prove that a steering request moved a client. Check later topology/client reports and their timestamps.

The topology uses spring forces, draggable nodes, zoom, pinning and optional motion. Radio/BSS membership is not a measured Ethernet link. Old associations are labeled stale. Metrics and replay views are not evidence that a client is currently connected.

## Pause controls

- Pause view freezes the browser timeline only.
- Pause periodic queries stops topology/AP capability polling; other controller traffic continues.
- `touch onboarding.paused` suppresses autoconfiguration Search/M1 responses and transmitted Response/WSC/Renew messages. Discovery, topology, metrics, and capture continue. Remove the marker to resume. Check `onboarding_paused` in `/api/state`.

Do not interpret an onboarding command as applied while that marker exists. The command can time out unconfirmed.

## Recorded sessions

Create a local `replays/` directory and place `.pcap` or `.pcapng` files there; restart the panel to discover them. No captures ship with the repository. Replay direction uses the current controller/target identities when known and otherwise labels it unknown. Offline replay cannot transmit commands. The live radio view still represents the live agent.

## Speed measurements

The client opens http://10.203.88.1:8080. The panel sends a job to that cooperating browser, which runs download/upload and reports results. The endpoint checks a session token and peer IP. Browser sessions expire when polling stops.

Transfers use two HTTP streams for about six seconds per direction, capped at 128 MiB. Latency is the median of five HTTP requests, not ICMP ping. Browser timing, host CPU, Ethernet, USB and Wi-Fi affect results. The 128 MiB cap may end fast downloads before six seconds. Host-local tests are labeled separately from client-path results.

## Experimental 6 GHz

Enable 6 GHz / WPA3 selects the experimental Profile 2 persona and requests onboarding for 2.4/5/6 GHz. A valid 6 GHz M1 must advertise the relevant band and SAE/AES capabilities. The implementation refuses WPA2 fallback for a known 6 GHz radio.

`bss_present_not_controller_confirmed` means the agent reports a BSS but the controller has not established that its own current credentials were applied. Manual UI enablement is not controller onboarding. See EXPERIMENTS.md for the observed device behavior.
