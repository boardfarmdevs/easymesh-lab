"""Evidence-based client telemetry. Never infer noise or hardware from an OUI."""
import time


def signal(rcpi):
    if not isinstance(rcpi, int) or not 0 <= rcpi <= 220:
        return {'dbm': None, 'bound': None, 'quality': 'unknown', 'color': 'gray'}
    dbm = rcpi / 2 - 110
    quality, color = ('good', 'green') if dbm >= -67 else ('fair', 'yellow') if dbm >= -75 else ('weak', 'red')
    return {'dbm': dbm, 'bound': 'at_most' if rcpi == 0 else 'at_least' if rcpi == 220 else None,
            'quality': quality, 'color': color}


def identify(evidence, now):
    evidence = [e for e in evidence if 0 <= now-e.get('time', 0) < 86400][-20:]
    candidates = []
    for e in evidence:
        text = str(e.get('value', '')).lower()
        kind = e.get('kind', '')
        if kind == 'mdns_model':
            if 'macbook' in text: candidates.append(('Mac laptop', 'medium', e))
            elif text.startswith('iphone'): candidates.append(('iPhone', 'medium', e))
            elif text.startswith('ipad'): candidates.append(('iPad', 'medium', e))
            elif text.startswith(('imac', 'macmini', 'macpro', 'macstudio')): candidates.append(('Mac desktop', 'medium', e))
        elif kind in ('dhcp_hostname', 'mdns_hostname'):
            if 'macbook' in text: candidates.append(('Mac laptop', 'low', e))
            elif 'iphone' in text: candidates.append(('iPhone', 'low', e))
            elif 'ipad' in text: candidates.append(('iPad', 'low', e))
        elif kind == 'browser_user_agent':
            if 'iphone' in text: candidates.append(('iPhone', 'medium', e))
            elif 'ipad' in text: candidates.append(('iPad', 'medium', e))
            elif 'macintosh' in text: candidates.append(('Apple client (Mac or iPad)', 'low', e))
    strong = [c for c in candidates if c[1] == 'medium']
    chosen = strong or candidates
    if any(c[0] in ('Mac laptop','Mac desktop','iPad') for c in chosen):
        chosen=[c for c in chosen if c[0]!='Apple client (Mac or iPad)']
    labels = {c[0] for c in chosen}
    if len(labels) > 1:
        label, confidence = 'Conflicting device hints', 'unknown'
    elif chosen:
        label, confidence, _ = chosen[0]
    else:
        label, confidence = 'Unknown device', 'unknown'
    return {'label': label, 'confidence': confidence, 'inferred': bool(chosen),
            'evidence': evidence, 'note': 'Self-reported hints can be renamed or spoofed. No exact hardware model verified.'}


def client_views(state, records=None, browser_sessions=(), now=None):
    now = time.time() if now is None else now
    obs = list(state.get('observations', {}).values())
    report = max((o for o in obs if o.get('type') == 0x84), key=lambda o:o.get('time', 0), default={})
    views = {}
    for bss in report.get('fields', {}).get('bss', []):
        for client in bss.get('clients', []):
            mac = client['station']; bssid = bss['bssid']; received = report.get('time', 0)
            association_start = received-client.get('associated_seconds', 0)
            candidates = sorted((o for o in obs if o.get('type') == 0x96 and o.get('fields', {}).get('station') == mac), key=lambda o:o.get('time', 0), reverse=True)
            metric = next(((o, link) for o in candidates for link in o['fields'].get('bss', []) if link.get('bssid') == bssid), None)
            out = {'station': mac, 'bssid': bssid, 'snr_db': None, 'noise_dbm': None,
                   'snr_reason': 'No compatible, co-timed signal and noise measurement reported.',
                   'signal_source': 'AP receive power from Associated STA Link Metrics TLV 0x96; RCPI / 2 - 110',
                   'perspective': 'AP receiving this client, not the client receiving the AP',
                   'rcpi': None, 'age_seconds': None, 'stale': True, **signal(None)}
            if metric:
                o, link = metric; measured = o['time']-link.get('measurement_age_ms', 0)/1000
                age = max(0, now-measured)
                stale = age > 60 or now-received > 90 or measured < association_start-2 or now-state.get('last_agent_at', 0)>90
                out.update(signal(link.get('uplink_rcpi')), rcpi=link.get('uplink_rcpi'), age_seconds=round(age, 1), stale=stale,
                           reported_at=o['time'], measurement_age_ms=link.get('measurement_age_ms'),
                           downlink_mbps=link.get('downlink_mbps') or None, uplink_mbps=link.get('uplink_mbps') or None)
                if stale: out.update(color='gray', quality='stale')
            evidence = list((records or {}).get(mac, {}).get('evidence', []))
            for session in browser_sessions:
                if session.get('mac') == mac and session.get('browser'):
                    evidence.append({'kind':'browser_user_agent', 'value':session['browser'], 'time':session.get('seen', 0), 'source':'Cooperating speed-test browser'})
            out['identity'] = identify(evidence, now)
            out['private_mac'] = bool(int(mac.split(':')[0], 16) & 2)
            views[mac] = out
    return views
