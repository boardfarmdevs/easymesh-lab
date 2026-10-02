import unittest
from experiments import SteeringTracker

STA='02:00:00:00:00:10';SOURCE='02:00:00:00:00:20';TARGET='02:00:00:00:00:30'
def packet(t,fields,mid=1):return {'mid':mid,'tlvs':[{'type':t,'fields':fields}]}
class SteeringEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.results={}
        self.tracker=SteeringTracker(lambda event,**data:self.events.append((event,data)),lambda id,**data:self.results.setdefault(id,{}).update(data))
        self.request=packet(0x9b,{'stations':[STA],'source_bssid':SOURCE,'targets':[{'bssid':TARGET}]})
        self.tracker.packet('TX',self.request,'command',100)
    def test_ack_is_not_outcome_and_wrong_station_report_is_ignored(self):
        self.tracker.packet('RX',{'mid':1,'tlvs':[]},'command',101)
        self.assertEqual(self.results['command']['steering']['outcome'],'awaiting_evidence')
        self.tracker.packet('RX',packet(0x9c,{'station':'other','source_bssid':SOURCE,'btm_status_code':0}),None,102)
        self.assertNotIn('btm_status_code',self.results['command']['steering'])
    def test_btm_acceptance_then_association(self):
        self.tracker.packet('RX',packet(0x9c,{'station':STA,'source_bssid':SOURCE,'btm_status_code':0},99),None,101)
        self.assertEqual(self.results['command']['steering']['outcome'],'awaiting_association')
        report=packet(0x84,{'bss':[{'bssid':TARGET,'clients':[{'station':STA}]}]})
        self.tracker.packet('RX',report,None,99)
        self.assertIn(STA,self.tracker.pending)
        self.tracker.packet('RX',report,None,105)
        self.assertEqual(self.results['command']['steering']['outcome'],'target_association_observed')
    def test_rejection_is_preserved_and_timeout_is_not_refusal(self):
        self.tracker.packet('RX',packet(0x9c,{'station':STA,'source_bssid':SOURCE,'btm_status_code':7}),None,101)
        self.tracker.tick(221)
        result=self.results['command']['steering']
        self.assertEqual(result['btm_status_code'],7)
        self.assertEqual(result['outcome'],'outcome_unconfirmed')
    def test_new_request_supersedes_old_and_late_topology_is_not_success(self):
        self.tracker.packet('TX',self.request,'second',110)
        self.assertEqual(self.results['command']['steering']['outcome'],'superseded')
        self.tracker.packet('RX',packet(0x84,{'bss':[{'bssid':TARGET,'clients':[{'station':STA}]}]}),None,231)
        self.tracker.tick(231)
        self.assertEqual(self.results['second']['steering']['outcome'],'outcome_unconfirmed')

class ValidationAndOnboardingTests(unittest.TestCase):
    def test_stale_association_and_same_target_rejected(self):
        from experiments import validate_steering
        s={'observations':{'a':{'type':0x84,'time':100,'fields':{'bss':[{'bssid':SOURCE,'clients':[{'station':STA}]}]}}},'operational_bss':[{'bssid':TARGET}]}
        params={'station':STA,'bssid':SOURCE,'target_bssid':TARGET}
        validate_steering(params,s,101)
        with self.assertRaisesRegex(ValueError,'Fresh source'):validate_steering(params,s,191)
        with self.assertRaisesRegex(ValueError,'different'):validate_steering({**params,'target_bssid':SOURCE},s,101)
    def test_paused_m1_evidence_is_credential_free(self):
        from experiments import observe_onboarding
        from test_fixtures import synthetic_m1
        s={}
        p={'kind':9,'tlvs':[{'type':0x82,'hex':TARGET.replace(':','')},{'type':0x11,'hex':synthetic_m1().hex()}]}
        observe_onboarding(s,'RX',p,100)
        record=s['onboarding_evidence']['m1_radios'][TARGET]
        self.assertEqual(record['rf_bands'],2)
        self.assertEqual(record['auth_flags'],'0020')
        self.assertNotIn('hex',record)
