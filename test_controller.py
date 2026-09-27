from test_fixtures import synthetic_m1
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import controller as c
from responder import parse, tlv, macbytes

class ControllerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        marker=patch.object(c,'ONBOARDING_PAUSE',Path(tmp.name)/'paused')
        marker.start();self.addCleanup(marker.stop)
    def test_paused_onboarding_preserves_monitoring(self):
        ctl=c.Controller.__new__(c.Controller)
        ctl.args=SimpleNamespace(controller='02:00:00:00:00:01',target='02:00:00:00:01:35')
        ctl.checkpoint=lambda:None
        seen=[];ctl.topology=lambda mid:seen.append(mid)
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'paused';marker.touch()
            with patch.object(c,'ONBOARDING_PAUSE',marker):
                for kind in (7,9):
                    ctl.handle(c.frame(ctl.args.target,ctl.args.controller,kind,1))
                for kind in (8,9,10):ctl.send(kind)
                ctl.handle(c.frame(ctl.args.target,ctl.args.controller,2,99))
        self.assertEqual(seen,[99])

    def test_client_polling_rotates_and_ignores_stale_associations(self):
        ctl=c.Controller.__new__(c.Controller);ctl.client_poll_cursor=0
        stations=[{'station':f'02:00:00:00:00:{i:02x}'} for i in range(10)]
        ctl.state={'observations':{'84:all':{'time':1000,'fields':{'bss':[{'clients':stations}]}}}}
        sent=[];ctl.send=lambda kind,body:sent.append((kind,body))
        with patch.object(c.time,'time',return_value=1000):
            ctl.poll_client_metrics();ctl.poll_client_metrics()
        self.assertEqual(len(sent),16)
        self.assertTrue(all(kind==0x800d for kind,_ in sent))
        self.assertEqual(len({body[-6:] for _,body in sent}),10)
        with patch.object(c.time,'time',return_value=1100):ctl.poll_client_metrics()
        self.assertEqual(len(sent),16)

    def test_topology_real_reports_and_truncation(self):
        value=bytes.fromhex('0302000000013800020000000137010200000002370c456173794d6573682d4c6162020000000136010200000002360c456173794d6573682d4c6162')
        bss=c.operational_bss(value)
        self.assertEqual([x['ssid'] for x in bss],['EasyMesh-Lab','EasyMesh-Lab'])
        self.assertEqual(bss[0]['radio'],'02:00:00:00:01:37')
        with self.assertRaises(ValueError):c.operational_bss(value[:-1])
    def test_m1_response_is_not_success_until_topology(self):
        ctl=c.Controller.__new__(c.Controller)
        ctl.args=SimpleNamespace(controller='02:00:00:00:00:01',target='02:00:00:00:01:35')
        ctl.config={'ssid':'EasyMesh-Lab','password':'TestSecret123','revision':1}
        ctl.uuid=b'R'*16; ctl.state={'radios':{},'operational_bss':[],'status':'waiting_for_agent'}
        ctl.cache={};ctl.last_response={};ctl.checkpoint=lambda:None
        sent=[];ctl.send=lambda *args,**kwargs:sent.append((args,kwargs))
        m1=synthetic_m1()
        radio=macbytes('02:00:00:00:01:37')
        pkt=c.frame(ctl.args.target,ctl.args.controller,9,42,tlv(0x85,radio+b'\x03\x00')+tlv(0x11,m1))
        ctl.handle(pkt)
        self.assertEqual(sent[0][0][0],9)
        self.assertEqual(ctl.state['status'],'m2_sent_awaiting_operational_bss')
        value=bytes.fromhex('01020000000137010200000002370c456173794d6573682d4c6162')
        ctl.handle(c.frame(ctl.args.target,ctl.args.controller,3,43,tlv(0x83,value)))
        self.assertEqual(ctl.state['status'],'ssid_confirmed_in_agent_topology')
        ctl.handle(c.frame(ctl.args.target,ctl.args.controller,3,44,tlv(0x83,b'\0')))
        self.assertNotEqual(ctl.state['status'],'ssid_confirmed_in_agent_topology')
    def test_atomic_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config.json';c.save(p,{'a':1});c.save(p,{'a':2})
            self.assertEqual(json.loads(p.read_text()),{'a':2})
            self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_6ghz_requires_new_radio_confirmation(self):
        ctl=c.Controller.__new__(c.Controller)
        ctl.args=SimpleNamespace(controller='02:00:00:00:00:01',target='02:00:00:00:01:35')
        ctl.config={'ssid':'Lab','revision':9,'enable_6ghz':True}
        ctl.state={'radios':{'02:00:00:00:01:37':{'rf_bands':2,'revision':9}}}
        ctl.checkpoint=lambda:None
        value=bytes.fromhex('0102000000013701020000000237034c6162')
        ctl.handle(c.frame(ctl.args.target,ctl.args.controller,3,1,tlv(0x83,value)))
        self.assertNotEqual(ctl.state['status'],'ssid_confirmed_in_agent_topology')
        ctl.state['observations']={'six':{'type':0x85,'fields':{'radio':'02:00:00:00:01:38','operating_classes':[{'class':131}]}}}
        manual=b'\x02'+value[1:]+bytes.fromhex('02000000013801020000000338064d616e75616c')
        ctl.handle(c.frame(ctl.args.target,ctl.args.controller,3,1,tlv(0x83,manual)))
        self.assertEqual(ctl.state['six_ghz_status'],'bss_present_not_controller_confirmed')
        self.assertEqual(ctl.state['six_ghz_bss_observed'][0]['ssid'],'Manual')
        ctl.state['radios']['02:00:00:00:01:38']={'rf_bands':8,'revision':9}
        value=b'\x02'+value[1:]+bytes.fromhex('02000000013801020000000238034c6162')
        ctl.handle(c.frame(ctl.args.target,ctl.args.controller,3,2,tlv(0x83,value)))
        self.assertEqual(ctl.state['six_ghz_status'],'confirmed_in_agent_topology')

    def test_6ghz_discovery_response_is_opt_in(self):
        from responder import response,MULTICAST
        host='02:00:00:00:00:01';agent='02:00:00:00:01:35'
        pkt=c.frame(agent,MULTICAST,7,30,tlv(1,macbytes(agent))+tlv(13,b'\0')+tlv(14,b'\x03')+tlv(0x81,b'\x01\x00'))
        self.assertIsNone(response(pkt,host,agent))
        msg=parse(response(pkt,host,agent,True))
        self.assertEqual(msg['tlvs'][16],[b'\x03'])
        self.assertEqual(parse(response(pkt,host,agent,True,2))['tlvs'][0xb3],[b'\x02'])

    def test_known_6ghz_radio_cannot_get_legacy_credentials(self):
        ctl=c.Controller.__new__(c.Controller)
        ctl.args=SimpleNamespace(controller='02:00:00:00:00:01',target='02:00:00:00:01:35')
        ctl.config={'ssid':'Lab','password':'TestSecret123','revision':1,'enable_6ghz':True}
        rid='02:00:00:00:01:38'
        ctl.state={'radios':{},'observations':{'85:'+rid:{'type':0x85,'fields':{'radio':rid,'operating_classes':[{'class':131}]}}}}
        # A known 6 GHz radio is mislabeled with this synthetic 5 GHz M1.
        m1=synthetic_m1()
        pkt=c.frame(ctl.args.target,ctl.args.controller,9,99,tlv(0x82,macbytes(rid))+tlv(0x11,m1))
        with self.assertRaisesRegex(ValueError,'refusing legacy credentials'):ctl.handle(pkt)

if __name__=='__main__':unittest.main()
