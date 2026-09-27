"""Controller-side steering policy scaffold. Advisory by default, no radio changes.

Candidate measurements must be supplied by a future beacon/unassociated-metrics
adapter. Current-link RCPI alone cannot establish a better target BSS.
"""
import math
import time


class Optimizer:
    def __init__(self, minimum_gain_db=8, weak_dbm=-72, dwell_seconds=120, cooldown_seconds=300):
        self.minimum_gain_db=minimum_gain_db; self.weak_dbm=weak_dbm
        self.dwell_seconds=dwell_seconds; self.cooldown_seconds=cooldown_seconds
        self.last_request={};self.pending={}

    def assess(self, client, candidates, now=None):
        now=time.time() if now is None else now
        def blocked(reason):return {'status':'observe','reason':reason,'station':client.get('station')}
        power=client.get('dbm')
        if client.get('stale',True) or power is None or not math.isfinite(power) or client.get('bound'):
            return blocked('Fresh, unsaturated current-link RCPI required')
        if client.get('associated_seconds',0)<self.dwell_seconds:return blocked('Minimum association dwell not reached')
        if now-self.last_request.get(client['station'],-1e12)<self.cooldown_seconds:return blocked('Steering cooldown active')
        if power>=self.weak_dbm:return blocked('Current signal does not justify steering')
        eligible=[]
        for target in candidates:
            if target.get('station')!=client['station'] or target.get('bssid')==client['bssid']:continue
            if target.get('ssid')!=client.get('ssid') or not target.get('security_compatible'):continue
            if target.get('source') not in ('client_beacon_report','unassociated_sta_metrics'):continue
            if not 0<=now-target.get('measured_at',0)<=60:continue
            candidate_power=target.get('dbm')
            if not isinstance(candidate_power,(int,float)) or not math.isfinite(candidate_power) or not -110<candidate_power<0:continue
            if candidate_power-power<self.minimum_gain_db:continue
            if not target.get('operating_class') or not target.get('channel'):continue
            # Cross-band/receiver calibration must be handled by the measurement adapter.
            if not target.get('comparable_to_current'):continue
            eligible.append(target)
        if not eligible:return blocked('No fresh, comparable, compatible target-BSS measurement')
        best=max(eligible,key=lambda t:t['dbm'])
        return {'status':'recommendation','station':client['station'],'source_bssid':client['bssid'],
                'target_bssid':best['bssid'],'operating_class':best['operating_class'],'channel':best['channel'],
                'gain_db':round(best['dbm']-power,1),'created_at':now,
                'reason':'Weak current signal and sufficiently stronger measured candidate',
                'execution':'Disabled; review and explicit approval required'}

    def queue_approved(self, proposal, enqueue, *, approved=False, now=None):
        """Execution boundary for a future UI/orchestrator; never called automatically.

Caller must re-evaluate measurements, current association and candidate
compatibility immediately before invoking this method. Record actual outcomes
from subsequent association reports, not from an ACK.
"""
        now=time.time() if now is None else now
        if not approved:raise PermissionError('Automatic steering is disabled')
        if proposal.get('status')!='recommendation' or not 0<=now-proposal.get('created_at',0)<=30:raise ValueError('Fresh recommendation required')
        station=proposal['station']
        if now-self.last_request.get(station,-1e12)<self.cooldown_seconds:raise ValueError('Steering cooldown active')
        params={'station':station,'bssid':proposal['source_bssid'],'target_bssid':proposal['target_bssid'],
                'opclass':proposal['operating_class'],'channel':proposal['channel']}
        from protocol import build_command
        build_command('steer',params,{})  # Validate before handing to the controller queue.
        result=enqueue('steer',params)
        self.last_request[station]=now
        self.pending[station]={'target_bssid':proposal['target_bssid'],'sent_at':now}
        return result

    def observe_outcome(self, station, bssid, observed_at):
        pending=self.pending.get(station)
        if not pending:return {'status':'no_pending_request'}
        if observed_at<=pending['sent_at']:return {'status':'awaiting_fresh_association'}
        if bssid==pending['target_bssid']:
            self.pending.pop(station)
            return {'status':'target_association_observed','note':'Association observed; this does not prove the request caused the move.'}
        if observed_at-pending['sent_at']>120:
            self.pending.pop(station)
            return {'status':'outcome_unconfirmed'}
        return {'status':'awaiting_target_association'}


def advisory_report(views, state, now=None):
    policy=Optimizer();out=[]
    associations={c['station']:c for o in state.get('observations',{}).values() if o.get('type')==0x84 for b in o['fields'].get('bss',[]) for c in b.get('clients',[])}
    bsses={b['bssid']:b for b in state.get('operational_bss',[])}
    for mac,view in views.items():
        client={**view,**associations.get(mac,{}),'ssid':bsses.get(view['bssid'],{}).get('ssid')}
        out.append(policy.assess(client,[],now))
    return {'mode':'advisory','automatic_steering':False,'clients':out,
            'next_requirement':'Candidate-BSS measurement adapter and multi-agent topology before enabling automatic execution.'}
