# Controller-side optimizer

[Documents](../README.md)

EasyMesh separates controller policy decisions from agent execution. This project models optimization as a Python component inside the controller application, not as another mesh agent. An agent sends measurements and executes controller steering requests; the client can decline or choose a different association.

`optimizer.py` supplies an advisory policy and an explicit execution boundary. The panel state includes `optimizer`, and the agent topology inspector shows why each client is being observed rather than moved. No automatic steering is enabled or transmitted by this component.

A recommendation requires:

- Fresh, unsaturated current-link power and at least 120 seconds association dwell.
- Current power below −72 dBm and a candidate at least 8 dB stronger.
- A measured candidate for the same station, within 60 seconds, using the same SSID and compatible security.
- A different target BSSID with channel/operating class and explicitly comparable measurements.
- At least 300 seconds since the previous requested move.

These are initial lab policy choices, not thresholds mandated by EasyMesh. Current-link RSSI alone cannot select a target. The live adapter currently supplies **no candidate measurements**, so the optimizer remains in observe mode. A future adapter must normalize beacon reports or unassociated-station measurements, verify security/capability compatibility, and account for receiver/band differences.

`queue_approved(proposal, enqueue, approved=True)` validates a fresh recommendation, checks cooldown, and calls an injected existing-controller command queue with a `steer` recipe. There is no automatic caller or browser endpoint that approves proposals. This is a tested extension boundary, not a deployed automatic steering loop. `observe_outcome` uses a fresh association report to distinguish observed target association from an unconfirmed result. ACK receipt is not success and temporal sequence alone does not prove causation.

Before enabling automatic execution with more clients, add multi-agent topology/command routing, candidate measurement adapters, persistent cooldown/history, target load/capacity and client capability checks, an enable/disable control, and a supervised trial. Test rejected steering, disappearing clients, stale reports, and repeated back-and-forth movement. Keep a command and outcome audit trail.
