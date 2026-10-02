# Managed USB Wi-Fi test clients

[Documents](../README.md)

Two explicitly enrolled USB Wi-Fi adapters can act as real stations inside the lab VM. Each physical PHY is moved into its own network namespace. No veth, bridge, default route or NAT connects those namespaces. Client-to-client traffic must traverse the extender over the air. Same-radio tests consume airtime on both legs and are not equivalent to the wired-server OpenSpeedTest result.

## Deployment

Install `iw wpasupplicant iperf3` in the VM, plus the kernel USB Wi-Fi driver and its firmware. The current MT7925U adapters work with the installed Ubuntu kernel and firmware. On the LXD host, a single USB device selector passes matching adapters into the VM (including reconnects):

```sh
lxc config device add easymesh-lab wifi-clients usb vendorid=0846 productid=9072 required=false
```

Create `/etc/easymesh-wifi-clients.json` with the physical country and an explicit client allowlist. Example (replace MACs and BSSID with observed device values):

```json
{"country":"US","clients":[
  {"namespace":"wifi-client-a","mac":"02:00:00:00:00:01","address":"10.203.88.10/24","bssid":"02:00:00:00:01:01"},
  {"namespace":"wifi-client-b","mac":"02:00:00:00:00:02","address":"10.203.88.11/24","bssid":"02:00:00:00:01:01"}
]}
```

Reserve these static IPs outside the DHCP pools. Namespace names, addresses and BSSIDs are administrator-controlled configuration. The service enrolls only listed MACs; attaching an arbitrary Wi-Fi adapter does not authorize it to join. SSID/password are read from the private controller `config.json` at service startup. Runtime supplicant configs are mode 0600; never commit them.

Install `deploy/lxd-vm/easymesh-wifi-clients.service` into `/etc/systemd/system/`, run `systemctl daemon-reload`, then `systemctl enable --now easymesh-wifi-clients`. This runs `tools/wifi_clients.py` as root with automatic restart. The running lab has this service enabled. It discovers enrolled radios every five seconds; wpa_supplicant handles reassociation. Restart the service after configuration or credential changes. Specifying a BSSID pins the AP/band for a repeatable test; omit it to let the station choose a BSS. The initial deployment uses the observed 5 GHz BSSID for both clients. This is not an automatic steering policy.

Status and direct station evidence: `run/wifi-clients/status.json`. Supplicant logs and iperf JSON results live in the same directory. These records include client-side signal and negotiated radio information, separate from the extender's 1905 reports. They are not yet integrated into the panel's speed history. Associations appear through ordinary topology polling.

## Actual iperf3 test

Start a server in B, then test from A (run in separate terminals):

```sh
ip netns exec wifi-client-b iperf3 -s -1 -B 10.203.88.11
ip netns exec wifi-client-a iperf3 -c 10.203.88.11 -B 10.203.88.10 -P 4 -t 30 -O 3 -J
```

Restart the one-shot server and add `-R` to the client command for B-to-A. Report the receiver throughput and retransmissions. No iperf listener is exposed on VM management. To stop automatic joining, stop/disable `easymesh-wifi-clients.service`; its cleanup stops supplicants and returns PHYs to the VM default namespace. Remove the LXD `wifi-clients` device to return USB ownership to the host.

## 6 GHz / WPA3 configuration

The current deployment uses the observed 6 GHz BSSID with `security: "wpa3"` and `scan_freq: 6295` for both enrolled clients. The latter focuses discovery on the observed channel 69; update or remove it if the extender changes channel. WPA3 mode requires SAE, PMF, and supports SAE hash-to-element (`sae_pwe=2`); there is no WPA2 fallback. Verify `wpa_cli status` reports COMPLETED, SAE, pmf=2 and the 6 GHz frequency.

The manager publishes non-secret, current `iw dev wlan0 info` observations to `run/wifi-radio-observations.json`, readable by the panel. The topology maps these to an associated BSSID, labels the evidence as managed-client observation, and only uses samples younger than 30 seconds. These describe the client's operating width, not a fabricated 1905 report or maximum AP capability.

## Discovery interoperability diagnostic

The controller accepts `--discovery-interval SECONDS` (default 60; 0 disables periodic announcements). Use zero only as an explicit known-agent interoperability workaround. The running lab currently uses a systemd diagnostic drop-in with zero after reproducing Ethernet/Wi-Fi resets from a discovery/response exchange. Queries and responses remain active. This is not a general replacement for normal discovery. See private `run/wifi-clients/INVESTIGATION.md` for measured evidence and restoration steps.
