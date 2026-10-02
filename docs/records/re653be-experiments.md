# RE653BE experiment summary

[Documents](../README.md)

These are observations from one device/firmware configuration, not promises about all EasyMesh agents. Device identities, credentials, raw packets and browser sessions are omitted from this public summary; the original evidence is retained privately.

| Experiment | Observed outcome |
| --- | --- |
| 2.4/5 GHz WSC onboarding | Agent M1, encrypted controller M2, then expected SSID in operational BSS reports |
| SSID change | Renew and fresh M1/M2; new SSID confirmed by topology |
| 6 GHz capability | Radio advertised 6 GHz operating classes |
| Controller 6 GHz onboarding | No 6 GHz M1 observed, including experimental Profile 2 attempts |
| Manual 6 GHz enablement | BSS appeared; automatic lower-band reprovisioning coincided with disappearance |
| Onboarding responses paused | Manually enabled BSS persisted and accepted a Mac client |
| 6 GHz data path | Browser endpoint became reachable; agent reported matching 6 GHz client MAC |
| Local browser throughput | 315.69 Mbps host→Mac, 89.44 Mbps Mac→host, 8.8 ms HTTP latency |
| USB adapter on original host | 480 Mbps USB negotiation despite USB 3 host and adapter capability |
| Same adapter on comparison host | 5000 Mbps negotiation; lab migration and retest not yet performed |

The manually enabled BSS used a different SSID from the controller-provisioned lower bands. The Mac automatically returned to the lower-band network during one trial. Disabling Auto-Join for that network allowed a subsequent 6 GHz test. The exact fallback cause was not established.

The extender itself replied to DHCP requests, assigning addresses and advertising itself as gateway/DNS. Absence from the Python DHCP server's lease table therefore did not imply lack of an IP. Capture showed an address change following a NAK. Duplicate-address labels in analysis did not by themselves establish simultaneous ownership because the Mac used different private addresses for different SSIDs.

The successful speed test used a USB 2 connection and a browser HTTP method. It does not establish maximum 6 GHz radio capacity. WPA3 handshake details were not independently verified by RF capture, and controller-based 6 GHz provisioning is still unconfirmed.
