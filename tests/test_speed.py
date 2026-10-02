import json,socket,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import lab_dhcp as dhcp
import speed_store as store
class SpeedTests(unittest.TestCase):
 def test_dhcp_no_route_or_dns_and_xid_preserved(self):
  req=bytearray(240);req[4:8]=b'test';req[28:34]=bytes.fromhex('020000000001')
  out=dhcp.packet(req,5,'10.203.88.100');o=dhcp.options(out)
  self.assertEqual(out[4:8],b'test');self.assertEqual(out[28:34],req[28:34]);self.assertEqual(socket.inet_ntoa(out[16:20]),'10.203.88.100')
  self.assertEqual(o[53],b'\x05');self.assertNotIn(3,o);self.assertNotIn(6,o)
  with self.assertRaises(ValueError):dhcp.options(b'\0'*240+b'\x35\x03\x01')
 def test_session_visibility_and_queue_limits(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(store,'BASE',Path(tmp)):
   for name in ('sessions','jobs','results'):(Path(tmp)/name).mkdir()
   id='a'*32;path=Path(tmp)/'sessions'/f'{id}.json';s={'id':id,'token':'private','seen':time.time(),'ip':'10.203.88.101'};store.atomic(path,s)
   self.assertNotIn('token',store.sessions()[0]);self.assertTrue(store.sessions()[0]['online'])
   self.assertEqual(store.enqueue(id)['status'],'queued')
   with self.assertRaises(ValueError):store.enqueue(id)
   s['seen']=time.time()-30;store.atomic(path,s)
   with self.assertRaises(ValueError):store.enqueue(id)
   with self.assertRaises(ValueError):store.enqueue('../config')
if __name__=='__main__':unittest.main()
