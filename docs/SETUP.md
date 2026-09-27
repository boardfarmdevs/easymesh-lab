# Physical setup and host migration

Use a dedicated Ethernet adapter connected directly to one lab agent. Keep the host's management interface outside the namespace. This setup provides no NAT, default route, or internet forwarding.

## 1. Install and identify the interface

Install Python 3.10+, venv support, iproute2, and dumpcap using your distribution's packages. Create the virtual environment and install requirements as shown in the README.

```bash
ip -brief link
lsusb -t
```

A USB 3 adapter should show `5000M` or higher. Ethernet link speed and USB bus speed are separate limits.

Run subsequent commands from the repository root. Fill in your actual dedicated interface and the agent's AL MAC (from a capture or discovery), not its Wi-Fi BSSID:

```bash
LAB_ROOT="$PWD"
LAB_IFACE="YOUR_USB_INTERFACE"
LAB_AGENT="YOUR_AGENT_AL_MAC"
LAB_PY="$LAB_ROOT/.venv/bin/python"
```

Ensure NetworkManager or another network manager does not configure this dedicated interface automatically. Do not apply that change to the host's management interface.

## 2. Configure private credentials

```bash
"$LAB_PY" controller.py init --ssid EasyMesh-Lab
mkdir -p run
```

`config.json` is mode 0600 and excluded from Git. Read the generated password locally when joining a client. Do not paste it into a committed document.

To preserve manually enabled 6 GHz settings during observation, create `onboarding.paused` before starting the controller. Remove it when deliberately testing controller onboarding.

## 3. Create the namespace

Run once; if `easymesh-lab` already exists, inspect it before reusing it.

```bash
sudo ip netns add easymesh-lab
sudo ip link set "$LAB_IFACE" down
sudo ip link set "$LAB_IFACE" netns easymesh-lab
sudo ip netns exec easymesh-lab ip link set lo up
sudo ip netns exec easymesh-lab ip address add 10.203.88.1/24 dev "$LAB_IFACE"
sudo ip netns exec easymesh-lab ip link set "$LAB_IFACE" up
```

The fixed subnet must be unused elsewhere on this host. No gateway/DNS is supplied by the optional Python DHCP server.

## 4. Start services in separate terminals

Use the same `LAB_ROOT`, `LAB_IFACE`, `LAB_AGENT`, and `LAB_PY` values in each terminal. Foreground operation makes stopping each service with Ctrl-C straightforward.

```bash
# Full capture: shell writes the file as your user; dumpcap captures as root.
sudo ip netns exec easymesh-lab dumpcap -i "$LAB_IFACE" -s 0 -w - > run/wired.pcapng
```

Choose a new capture filename for each run; shell redirection overwrites an existing file.

```bash
sudo ip netns exec easymesh-lab "$LAB_PY" controller.py run \
  --interface "$LAB_IFACE" --target "$LAB_AGENT"
```

The controller reads its source MAC from the selected interface; `--controller` can explicitly verify it. Only traffic from the configured target agent is handled. Use the default `config.json` and `state.json` paths with the panel, which reads those files from the repository root.

```bash
# Optional: use only after checking that the agent is not already serving DHCP.
sudo ip netns exec easymesh-lab "$LAB_PY" lab_dhcp.py --interface "$LAB_IFACE"
```

The RE653BE was observed serving its own DHCP leases. Do not blindly run two competing DHCP services. The Python service uses .100–.199, but non-overlapping pools alone do not prevent conflicting gateway/DNS information.

```bash
# Run the speed endpoint as your normal user, inside the namespace.
sudo ip netns exec easymesh-lab sudo -u "$(id -un)" "$LAB_PY" "$LAB_ROOT/speed_server.py"
# Run the panel unprivileged, outside the namespace.
"$LAB_PY" panel_server.py
```

Join the agent Wi-Fi and open **http://10.203.88.1:8080** on the client. Keep it open to accept panel-initiated tests. This is a local test; internet access is unnecessary.

For a browser on another management host, specify both the server name/IP used in the URL and the browser source IP:

```bash
"$LAB_PY" panel_server.py --bind 0.0.0.0 \
  --host YOUR_LAB_HOST_IP --allow-client YOUR_BROWSER_IP
```

Open `http://YOUR_LAB_HOST_IP:8765`. For a Host/client rejection, check those two values; refresh after restarting the server to obtain a new request token.

Optional passive device identification: run `device_observer.py --interface "$LAB_IFACE"` using the same privileged namespace/interpreter invocation as the controller. See [TELEMETRY.md](TELEMETRY.md). Stop this observer along with the other services before unplugging the adapter.

## 5. Move to another host

Clone/copy only this source repository, recreate its venv, identify the new interface, and repeat the namespace setup. The hardware MAC may remain the same; Linux interface names and USB speed must be checked again. Generate new credentials or transfer the private config separately through a trusted channel. Captures, old queues, state, sessions, PIDs and logs are not migration inputs.

Unplugging USB removes the interface and interrupts capture/controller operation. Stop any remaining DHCP/speed services, reconnect, move the new interface into the namespace, restore its address, and restart the services. Never rely on old PID files after a host move.

## 6. Stop and restore

Stop foreground controller, DHCP, speed server and capture with Ctrl-C. Keep the capture file. Verify no lab processes remain before moving the interface back:

```bash
sudo ip netns exec easymesh-lab ip address flush dev "$LAB_IFACE"
sudo ip netns exec easymesh-lab ip link set "$LAB_IFACE" down
sudo ip netns exec easymesh-lab ip link set "$LAB_IFACE" netns 1
sudo ip netns delete easymesh-lab
```

Do not delete a namespace used by other work. Restore network-manager ownership of the adapter if you disabled it earlier.
