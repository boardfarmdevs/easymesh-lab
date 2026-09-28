"""Correlate steering evidence without treating receipt as a successful roam."""
class SteeringTracker:
    def __init__(self, emit, result):
        self.emit=emit; self.result=result; self.pending={}

    def packet(self, direction, packet, command, now):
        for tlv in packet.get('tlvs', []):
            f=tlv.get('fields', {})
            if direction=='TX' and tlv['type']==0x9b and command:
                targets=f.get('targets', [])
                if len(f.get('stations', []))!=1 or len(targets)!=1:continue
                station=f['stations'][0]
                old=self.pending.pop(station,None)
                if old:self.finish(old,'superseded',now)
                item=dict(command_id=command, station=station, source_bssid=f['source_bssid'],
                          target_bssid=targets[0]['bssid'], sent_at=now, mid=packet['mid'])
                self.pending[station]=item
                self.result(command,steering={**item,'outcome':'awaiting_evidence'})
                self.emit('steering_request',**item)
            if direction!='RX':continue
            if tlv['type']==0x9c:
                item=self.pending.get(f.get('station'))
                if item and now-item['sent_at']<=120 and f.get('source_bssid')==item['source_bssid']:
                    item['btm_status_code']=f['btm_status_code']
                    item['btm_reported_at']=now
                    self.result(item['command_id'],steering={**item,'outcome':'awaiting_association'})
                    self.emit('steering_btm',**item,note='Agent-reported BTM status; station/source/time correlation, not proof of causation.')
            if tlv['type']==0x84:
                for b in f.get('bss',[]):
                    for client in b.get('clients',[]):
                        item=self.pending.get(client['station'])
                        if item and item['sent_at']<now<=item['sent_at']+120 and b['bssid']==item['target_bssid']:
                            self.finish(item,'target_association_observed',now)
                            self.pending.pop(client['station'],None)

    def finish(self,item,outcome,now):
        evidence={**item,'outcome':outcome,'observed_at':now}
        self.result(item['command_id'],steering=evidence)
        self.emit('steering_outcome',**evidence,note='Observed association does not prove the request caused the move; a timeout does not prove refusal.')

    def tick(self,now):
        for station,item in list(self.pending.items()):
            if now-item['sent_at']>120:
                self.finish(item,'outcome_unconfirmed',now);self.pending.pop(station)


def validate_steering(params,state,now):
    """Reject stale source selection; wire-format validation remains in protocol.py."""
    source=params.get('bssid','').lower();target=params.get('target_bssid','').lower()
    station=params.get('station','').lower()
    if source==target:raise ValueError('Choose a target BSSID different from the source')
    reports=[o for o in state.get('observations',{}).values() if o.get('type')==0x84]
    latest=max(reports,key=lambda o:o.get('time',0),default={})
    matches=any(b.get('bssid')==source and any(c.get('station')==station for c in b.get('clients',[]))
                for b in latest.get('fields',{}).get('bss',[]))
    if not matches or not 0<=now-latest.get('time',0)<90:
        raise ValueError('Fresh source association required; query topology and select the current client/BSSID')
    if target not in {b.get('bssid') for b in state.get('operational_bss',[])}:
        raise ValueError('Target BSSID has not been reported by this lab agent')


def observe_onboarding(state,direction,packet,now):
    """Keep bounded, credential-free evidence even while provisioning is paused."""
    if packet.get('kind') not in (7,8,9,10):return
    evidence=state.setdefault('onboarding_evidence',{'since':now,'messages':{},'search_bands':{},'m1_radios':{}})
    key=direction+':'+str(packet['kind'])
    evidence['messages'][key]=evidence['messages'].get(key,0)+1
    evidence['last_at']=now
    fields={t['type']:t for t in packet.get('tlvs',[])}
    if direction=='RX' and packet['kind']==7:
        band=fields.get(14,{}).get('hex','')[:2]
        if band in ('00','01','02','03'):
            evidence['search_bands'][band]=evidence['search_bands'].get(band,0)+1
    if direction!='RX' or packet['kind']!=9 or 0x11 not in fields:return
    from wsc import attrs
    try:
        a=attrs(bytes.fromhex(fields[0x11]['hex']))
        if a.get(0x1022)!=b'\x04':return
        raw=fields.get(0x82,fields.get(0x85,{})).get('hex','')[:12]
        if len(raw)!=12:return
        radio=':'.join(raw[i:i+2] for i in range(0,12,2))
        old=evidence['m1_radios'].get(radio,{})
        evidence['m1_radios'][radio]={'count':old.get('count',0)+1,'last_at':now,
            'rf_bands':int.from_bytes(a.get(0x103c,b''),'big'),
            'auth_flags':a.get(0x1004,b'').hex(),'manufacturer':a.get(0x1021,b'').decode('utf8','replace')[:128],
            'model':a.get(0x1023,b'').decode('utf8','replace')[:128]}
    except (ValueError,KeyError):return
