# A second extender on a wireless backhaul

Experimental. The first extender (the RE653BE on USB Ethernet, the controller's
`--target`) stays the **primary agent** and behaves exactly as before. A second
extender, a TP-Link RE715X (hardware 2.6, firmware 1.2.0 Build 20241210), was
onboarded by this controller on 29 September 2026: first over Ethernet, then
moved to a Wi-Fi backhaul to the RE653BE.

Powering a new extender on is not enough. From factory state it offers only its
own setup network, and the controller answers only agents it has admitted.

## What the controller does

| Step | Mechanism | Where |
| --- | --- | --- |
| The primary offers a backhaul | On the bands in `backhaul_bands` (never 6 GHz), either the fronthaul BSS doubles as backhaul (Multi-AP extension `0x60`), or, with `backhaul_ssid`/`backhaul_password`, each radio gets a second M2 for a separate backhaul BSS (`0x40`) | `controller.py set-backhaul` |
| The new agent is noticed | Its 1905 messages carry its own AL MAC. Unknown AL MACs are recorded under `pending_agents` and **never answered** | Panel status line: *N pending* |
| You admit it | Its AL MAC is added to `agents` in `config.json` | Panel: *Admit an agent* (pre-filled from the first pending agent) |
| Onboarding | Autoconfiguration response and M2s per radio, addressed to that agent; its own status, BSSs, interfaces and clients | `state.json` `agents`, `topology`; Topology tab |
| Push-button (optional) | 1905 Push Button Event Notification (`0x000B`); Push Button Join Notifications (`0x000C`) are recorded | Panel: *Start push-button onboarding* |

Queries in the Command studio take an optional *Agent AL MAC*; blank addresses
the primary. Automatic topology, capability and client-metric polling cover
every admitted agent that has been seen.

## Procedure that worked

1. **Keep the primary's 5 GHz radio off DFS channels.** On channel 100 (160 MHz)
   the RE715X offered no 5 GHz host at all. A Channel Selection Request marking
   the DFS operating classes (118–123), the DFS 80 MHz centres and 160 MHz as
   non-operable moved the RE653BE to channel 40; it still reported a 160 MHz
   channel around it.
2. **Offer a separate backhaul** (inside the VM, as the `easymesh` user):

   ```sh
   /opt/easymesh-lab/.venv/bin/python /opt/easymesh-lab/controller.py set-backhaul --bands 5 --backhaul-ssid EasyMesh-Lab-BH
   ```

   The password is generated and kept in the private `config.json`. With it,
   the RE715X's backhaul STA joined only the hidden `EasyMesh-Lab-BH` BSS. With
   the combined style (`--combined`), the RE653BE split the BSS into a visible
   fronthaul and a hidden backhaul **with the same credentials**; after the
   RE653BE restarted its BSSs once, the RE715X's backhaul STA fell back onto the
   fronthaul BSS as a plain client and 1905 stopped.
3. **Resume onboarding** by removing `onboarding.paused` (after a backup of
   `config.json` and `state.json`). The primary answers with fresh M1s; expect
   a few minutes of repeated M1/M2 rounds before it settles. Check its SSIDs and
   the manually enabled 6 GHz BSS afterwards.
4. **Onboard the new extender over Ethernet.** Factory-reset it, then put an
   unmanaged switch between the controller's USB Ethernet adapter and the
   primary, and cable the new extender to the switch. (Never cable an extender
   that is also configured as a Wi-Fi repeater of the same network: that is a
   bridging loop.) Its agent searches for a controller within about a minute
   and appears as pending; admit it. The RE715X advertised Multi-AP Profile 3
   and a DPP chirp.
5. **Unplug its cable.** The RE715X's backhaul STA joined the RE653BE's hidden
   backhaul BSS within four seconds, and its 1905 traffic continued through the
   RE653BE. The Topology tab then shows a *Wi-Fi backhaul* link from the primary
   BSS it joined.

## Open problem: re-onboarding on a wireless backhaul

On the Wi-Fi backhaul the RE715X kept re-running onboarding, and each round
restarted its BSSs. In the 4.5 minutes after unplugging, its 5 GHz radio
received 104 M2s (the RE653BE 20). That radio also carries its own backhaul
STA, so applying an M2 drops its backhaul; after reconnecting it searches
again, is answered, and receives another M2. The RE653BE meanwhile dropped its
6 GHz clients about every two minutes.

Pausing onboarding stopped the loop, but about 20 seconds later the RE715X
left the backhaul: it gives up when its controller stops answering. Wired, with
onboarding answered, it was stable.

Next experiment: keep answering searches, but do not re-send an unchanged M2
(same configuration revision, SSIDs already confirmed) to a radio that carries
the agent's own backhaul STA, or rate-limit it; then watch whether the agent
keeps its backhaul.

State left on 29 September 2026: onboarding paused, the RE715X unplugged and
off the backhaul, the RE653BE on 5 GHz channel 40 with the separate backhaul.

## What did not work with these extenders

- **Push-button onboarding.** The RE653BE ignored the controller's Push Button
  Event Notification, and its own WPS button apparently makes it look for an
  upstream network rather than open WPS for a new node.
- **Extending the network from the new extender's setup page.** It joins the
  visible fronthaul BSS as a plain repeater; no 1905 reaches the controller.

## Limits

- The controller's own 1905 neighbor stays the primary agent; the new agent is
  reached through it or through the shared wired segment.
- The RE653BE does not list 1905 neighbors in its topology responses, and does
  not advertise the standard Multi-AP element in beacons; roles are inferred
  from the M2s and from its TP-Link vendor element.
- Whether a retail extender's EasyMesh firmware accepts a third-party
  controller is part of the experiment, not a claim.
