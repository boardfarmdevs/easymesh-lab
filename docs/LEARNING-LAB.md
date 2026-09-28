# Single-extender experiments and packet timing

The Live wire page includes an oscilloscope-style 1905.1 timing view. The Experiments page follows a five-step workflow: supervised steering, client history, guided protocol queries, optimizer observation, and 6 GHz diagnostics. Python owns packet handling, evidence and services; the browser renders the interactive views.

## 1. Supervised steering

Connect a client and query topology. Select the client and an alternate operational BSS in Experiments, then prepare the request in Command studio. When a fresh Operating Channel Report is available, its operating class and channel prefill the form. Otherwise those fields remain blank and must be verified; capability lists are not current channel reports. Review target SSID, security and client band support. Preview the packet, then send it.

Both the HTTP service and controller queue require a source association less than 90 seconds old and a different, observed target BSSID. This validation does not prove target coverage or client compatibility. Raw composition remains an advanced protocol exercise and bypasses the guided steering validation.

Evidence is deliberately separate:

- Command result: transmission, matching ACK or response, or no matching reply after 30 seconds.
- Agent BTM report: raw status code correlated by station, source BSSID and a 120-second window; it need not reuse the request MID. This is not an over-the-air capture of the client's BTM response.
- Outcome: a fresh association report places the station on the requested target, or the outcome remains unconfirmed after 120 seconds. A subsequent association does not prove the request caused it.

A second request for the same station supersedes tracking of the first. Overlapping requests can make late BTM reports ambiguous; avoid them in controlled experiments. Restart marks unfinished tracked requests as interrupted, rather than leaving them apparently pending forever. The request does not set disassociation-imminent and does not force a disconnect.

## 2. Client history

The controller records a snapshot every 15 seconds without a browser. `run/client-history.jsonl` retains up to 8 MiB plus one previous segment. The panel reads at most the last 1.5 MB of each segment and returns at most 2,000 records; this is a bounded recent history, not an unlimited database. Full controller events remain in `events.jsonl`.

The view plots RCPI-derived AP receive power and estimated downlink/uplink PHY rates. The table includes band/BSSID and stale/unknown states. No lines bridge stale data, changed BSSs, or gaps exceeding 30 seconds. RCPI endpoints are bounds rather than exact power samples and are excluded from the power line. Sampling time is the history timestamp; the underlying metric's age is retained in each record. SNR is unknown without a compatible signal/noise pair.

Steering markers share the power chart; completed cooperating-browser speed tests are marked and listed for the same client MAC. Throughput is HTTP payload throughput, separate from estimated PHY rate. Private MAC changes create separate histories; identity hints do not justify merging them.

## 3. Guided protocol learning

The experiment cards prepare topology, AP capability, associated-client metrics, client beacon measurement and steering forms. Each explains expected evidence and relevant TLVs. Opening a card or inspecting a preview sends nothing. The existing packet inspector retains raw frame bytes and decoded TLVs, including unknown TLVs and decode errors.

### Packet colors and time scale

Colors identify message families (topology, autoconfiguration discovery, WSC/renew, capabilities, metrics, steering, ACK, other), with the same colors in the packet list and legend. Direction is encoded by the lane. A rectangular pulse's rising edge marks the host timestamp; its fixed width is decorative and does not encode airtime or packet length. A white outline marks selection without changing the family color.

The timebase readout shows seconds, milliseconds or microseconds per major division. There are five major divisions, each split into five minor intervals. Presets range from 1 ms/div to 1 min/div; zoom updates the readout continuously. At sub-10-ms windows, axis labels show offsets from the window start. A/B cursors provide a separate elapsed-time readout.

### Oscilloscope controls

- Drag the background to pan; wheel zooms around the pointer.
- Plus/minus buttons or keys zoom; arrow keys pan. Fit includes all loaded, filtered packets. Follow latest resumes tracking the newest packet.
- Click a pulse or focus it and press Enter to inspect its TLVs.
- Shift-click two pulses for a capture-time delta.
- Existing direction, message/MAC/TLV and MID filters apply to both list and scope.

Controller TX, accepted agent RX, and other observed frames occupy separate lanes. Dotted links indicate matching MID within 30 seconds and are correlation aids, not confirmed protocol relationships; MID reuse, unsolicited messages and separately numbered BTM reports require inspection. Host timestamps include scheduling and processing: pulse widths do not represent airtime, and deltas are not propagation delay measurements.

Live memory is limited to 20,000 recent events. The initial API request tails recent data; it does not load an entire historical capture. Replay uses the selected saved capture. Unsupported or fragmented untagged 1905 frames delivered to the controller socket are preserved for inspection but are not processed as control messages. This is not a radio monitor capture or a guarantee of every frame on an unseen network segment. The separate wired pcap remains available for packet-level investigation.

## 4. Optimizer observation

Policy explanations now appear on Experiments. Automatic steering remains disabled. A second agent is not required to consider a different band on the same extender, but a fresh comparable target measurement, compatible SSID/security and channel evidence are required. Policy uses a weak-link threshold of -72 dBm, an 8 dB candidate gain, 120-second dwell and 300-second cooldown.

Candidate adaptation/calibration is not implemented: the production advisory report supplies no candidates and cannot recommend a target solely from current-link RCPI. The existing policy tests exercise eligible and ineligible synthetic candidates. Beacon reports from a client and receive-power reports from an AP are different perspectives; do not compare them as interchangeable dBm readings.

## 5. 6 GHz diagnostics

The panel separates advertised radio capability, recorded 6 GHz onboarding state and operational BSS. Bounded, credential-free discovery/M1 counters persist in state across restarts and continue while onboarding is paused. They start when this instrumentation is deployed; empty counters do not invalidate older captures. M1 summaries retain radio ID, RF/auth flags, manufacturer/model and timestamps, not keys or full WSC payloads.

Paused onboarding commands now return an explicit error before changing configuration revision. Previously a renew could be suppressed while its command appeared to await onboarding. The pause remains in effect so that diagnostics preserve a manually configured BSS.

The current investigation has not established whether missing 6 GHz M1 is caused by our incomplete controller or agent interoperability restrictions. Exact hardware/firmware inventory and a known-compatible controller comparison remain useful. An M2 encoder with SAE support and a Profile 2 advertisement are not a claim of full EasyMesh conformance.

## Validation

31 Python tests, including steering acceptance-vs-outcome, refusal/timeout, supersession, stale-source rejection and credential-free onboarding evidence. `tools/smoke_learning.py` tests actual browser pulse selection, time cursors, zoom, drag, history and guided forms with synthetic API responses and all mutations blocked. `tools/smoke_panel.py` covers all seven tabs and mobile layout. Physical steering still requires a freshly associated client; synthetic tests do not prove a particular phone will roam.

Protocol field reference: [Wireshark IEEE 1905.1](https://www.wireshark.org/docs/dfref/i/ieee1905.html). Implementation comparison for separately numbered BTM reports: [RDK unified-wifi-mesh steering](https://github.com/rdkcentral/unified-wifi-mesh/blob/main/src/em/steering/em_steering.cpp). These references do not establish RE653BE support for every command.
