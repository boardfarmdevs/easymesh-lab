import unittest
from client_telemetry import signal, identify, client_views
from device_observer import hints
from protocol import decode_value
from scapy.all import Ether, IP, UDP, DNS, DNSRR, BOOTP, DHCP

MAC='02:00:00:00:00:11';BSS='02:00:00:00:00:22'
class TelemetryTests(unittest.TestCase):
    def test_rcpi_bounds_and_missing_values(self):
        self.assertEqual(signal(100)['dbm'],-60)
        self.assertEqual(signal(86)['color'],'green')
        self.assertEqual(signal(70)['color'],'yellow')
        self.assertEqual(signal(69)['color'],'red')
        for value in (221,254,255,None,-1):self.assertIsNone(signal(value)['dbm'])
        self.assertEqual(signal(0)['bound'],'at_most');self.assertEqual(signal(220)['bound'],'at_least')
    def test_telemetry_does_not_reuse_old_bss_or_old_association(self):
        state={'last_agent_at':1000,'observations':{'clients':{'type':0x84,'time':1000,'fields':{'bss':[{'bssid':BSS,'clients':[{'station':MAC,'associated_seconds':100}]}]}},'metric':{'type':0x96,'time':999,'fields':{'station':MAC,'bss':[{'bssid':BSS,'uplink_rcpi':100,'measurement_age_ms':2000,'uplink_mbps':0}]}}}}
        v=client_views(state,now=1000)[MAC];self.assertFalse(v['stale']);self.assertEqual(v['age_seconds'],3);self.assertIsNone(v['snr_db']);self.assertIsNone(v['uplink_mbps'])
        state['observations']['metric']['fields']['bss'][0]['bssid']='02:00:00:00:00:33'
        self.assertIsNone(client_views(state,now=1000)[MAC]['dbm'])
        state['observations']['metric']['fields']['bss'][0]['bssid']=BSS
        state['observations']['clients']['fields']['bss'][0]['clients'][0]['associated_seconds']=1
        state['observations']['metric']['fields']['bss'][0]['measurement_age_ms']=5000
        self.assertTrue(client_views(state,now=1000)[MAC]['stale'])
        self.assertEqual(client_views(state,now=1100)[MAC]['color'],'gray')
    def test_identity_is_inferred_and_conflicts_visible(self):
        e=[{'kind':'mdns_model','value':'MacBookAir10,1','time':99}]
        v=identify(e,100);self.assertEqual(v['label'],'Mac laptop');self.assertTrue(v['inferred'])
        self.assertEqual(identify([{'kind':'browser_user_agent','value':'Mozilla Macintosh','time':99}],100)['label'],'Apple client (Mac or iPad)')
        mixed=[{'kind':'mdns_hostname','value':'Test-MacBook.local','time':99},{'kind':'browser_user_agent','value':'Macintosh','time':99}]
        self.assertEqual(identify(mixed,100)['label'],'Mac laptop')
        e.append({'kind':'mdns_model','value':'iPhone13,1','time':99})
        self.assertEqual(identify(e,100)['confidence'],'unknown')
        self.assertEqual(identify(e,90000)['label'],'Unknown device')
    def test_passive_evidence_not_queries_or_other_devices(self):
        p=Ether(src=MAC)/IP()/UDP(sport=5353,dport=5353)/DNS(qr=1,an=[DNSRR(rrname='Test._device-info._tcp.local.',type='TXT',rdata=[b'model=MacBookAir10,1'])])
        self.assertEqual(hints(p,{MAC}),[(MAC,'mdns_model','MacBookAir10,1')])
        self.assertEqual(hints(p,set()),[])
        p[DNS].qr=0;self.assertEqual(hints(p,{MAC}),[])
        d=Ether(src=MAC)/IP()/UDP(sport=68,dport=67)/BOOTP(op=1,chaddr=bytes.fromhex(MAC.replace(':','')))/DHCP(options=[('hostname','Test-iPhone'),'end'])
        self.assertEqual(hints(d,{MAC})[0][1],'dhcp_hostname')
        d[BOOTP].op=2;self.assertEqual(hints(d,{MAC}),[])
    def test_rcpi_decoder_unavailable(self):
        raw=bytes.fromhex(MAC.replace(':',''))+b'\1'+bytes.fromhex(BSS.replace(':',''))+b'\0'*12+b'\xff'
        self.assertIsNone(decode_value(0x96,raw)['bss'][0]['estimated_uplink_dbm'])

if __name__=='__main__':unittest.main()
