# Client telemetry and identification

The controller polls Associated STA Link Metrics (0x800d) for up to eight reported clients every 15 seconds, rotating through larger lists. Turning off periodic queries also stops this polling. No steering or configuration change is part of telemetry polling.

Client cards and topology nodes show signal bars. The signal source is the agent's uplink RCPI in Associated STA Link Metrics TLV 0x96: AP receive power, not the phone's measurement of the AP. For values 1–219, power is RCPI/2 − 110 dBm with 0.5 dB encoding steps. Zero and 220 are saturation bounds; 221–254 are reserved and 255 is unavailable. This is an RCPI-derived power estimate, not a calibrated independent RSSI measurement.

Display colors are green at −67 dBm or stronger, yellow from −75 to below −67, and red below −75. These are UI thresholds, not EasyMesh requirements. Missing or stale readings are gray. Age includes the agent's measurement-age field; data from another BSSID or before a new association is not presented as current. Link rates are agent-reported estimates, separate from browser throughput.

SNR remains unavailable unless a compatible signal/noise pair is supplied. The current client-metrics TLV does not include noise. Radio channel utilization is not noise. An unrelated radio noise sample or sniffer RSSI must not be subtracted to invent client SNR. Wireless radios/BSSs do not have a meaningful standalone signal strength; the displayed bars belong to measured client links.

## Passive device hints

`device_observer.py` uses Scapy to listen only for DHCP and mDNS on the dedicated interface. It accepts hints only from MACs in fresh agent client reports. DHCP hostnames, vendor strings, mDNS hostnames and `_device-info._tcp` model advertisements are stored in ignored `run/device-evidence.json`, with source and timestamp. The panel also considers the user agent supplied by the cooperating speed-test browser. It does not decrypt HTTPS or inspect application payloads.

Launch in a separate terminal inside the lab namespace:

```bash
sudo ip netns exec easymesh-lab .venv/bin/python device_observer.py --interface YOUR_USB_INTERFACE
```

Use the absolute interpreter/script paths when launching from another directory. Stop with Ctrl-C before moving the interface. The observer requires the private config to set evidence-file ownership and an active controller state. It starts with an empty evidence set; only new traffic is learned.

Device labels are inferred, with evidence and confidence in the topology inspector. A hostname containing MacBook is a weak hint; an explicit model advertisement is stronger but still self-reported. An iPad desktop browser can claim Macintosh, so that alone is labeled “Apple client (Mac or iPad).” Private/local MAC addresses do not reveal a manufacturer OUI, and addresses on separate SSIDs are not automatically linked to one person/device. Expired hints are ignored after 24 hours.

## Live limitations

Initial client-metrics queries in the manually enabled 6 GHz RE653BE session received no matching response. After periodic polling was deployed, the agent did return client RCPI; one live sample was 106 (approximately −57 dBm, green). No noise/SNR measurement was supplied. The cause of the initial non-response was not established, and onboarding remained paused throughout. Resuming credential provisioning solely to obtain metrics can disrupt the working manual BSS.

References: [Wireshark RCPI field correction](https://gitlab.com/wireshark/wireshark/-/merge_requests/4972/commits), [1905 field dictionary](https://www.wireshark.org/docs/dfref/i/ieee1905.html), [Apple private Wi-Fi addresses](https://support.apple.com/en-ie/102509).
