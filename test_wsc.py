from test_fixtures import synthetic_m1
import hashlib
import hmac
import struct
import unittest
import wsc
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

class WSC(unittest.TestCase):
    def test_independent_enrollee_decrypts_and_authenticates(self):
        self.assertEqual(self.roundtrip(2,0x20,False)[0x1049],bytes.fromhex('00372a000120060120'))
    def test_sae_6ghz_independent_enrollee(self):
        self.roundtrip(8,0x40,True)
    def test_backhaul_bands_mark_fronthaul_bss_as_backhaul_too(self):
        multi_ap=lambda band,auth,six,bands:self.roundtrip(band,auth,six,{'backhaul_bands':bands})[0x1049][-1]
        self.assertEqual(multi_ap(2,0x20,False,['5']),0x60)
        self.assertEqual(multi_ap(1,0x20,False,['5']),0x20)
        self.assertEqual(multi_ap(1,0x20,False,['2.4','5']),0x60)
        self.assertEqual(multi_ap(8,0x40,True,['2.4','5']),0x20)  # never on 6 GHz
    def test_backhaul_and_agent_settings_are_validated(self):
        base={'ssid':'x','password':'abcdefgh'}
        for bad in ({'backhaul_bands':['6']},{'backhaul_bands':'5'},{'agents':['02:00:00:00:02:3F']},{'agents':'02:00:00:00:02:3f'}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):wsc.validate_config({**base,**bad})
        wsc.validate_config({**base,'backhaul_bands':['2.4','5'],'agents':['02:00:00:00:02:3f']})
    def test_separate_backhaul_bss_gets_its_own_m2(self):
        separate={'backhaul_bands':['5'],'backhaul_ssid':'EasyMesh-Lab-BH','backhaul_password':'BackhaulSecret9'}
        front=self.roundtrip(2,0x20,False,separate,0)
        back=self.roundtrip(2,0x20,False,separate,1)
        self.assertEqual((front[0x1045],front[0x1049][-1]),(b'EasyMesh-Test',0x20))
        self.assertEqual((back[0x1045],back[0x1027],back[0x1049][-1]),(b'EasyMesh-Lab-BH',b'BackhaulSecret9',0x40))
        self.assertEqual(len(wsc.bss_settings({'ssid':'x','password':'abcdefgh',**separate},1)),1)  # 2.4 GHz not listed
        self.assertEqual(len(wsc.bss_settings({'ssid':'x','password':'abcdefgh',**separate,'backhaul_bands':['2.4','5']},8)),1)  # never 6 GHz
        base={'ssid':'EasyMesh-Test','password':'TestSecret123'}
        for bad in ({'backhaul_ssid':'BH'},{'backhaul_ssid':'EasyMesh-Test','backhaul_password':'abcdefgh'},{'backhaul_ssid':'BH','backhaul_password':'short'}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):wsc.validate_config({**base,**bad})
    def roundtrip(self,band,authentication,enabled,extra={},pick=0):
        params=dh.DHParameterNumbers(wsc.P,2).parameters()
        private=params.generate_private_key(); pub=private.public_key().public_numbers().y.to_bytes(192,'big')
        m1=b''.join(wsc.attr(t,b) for t,b in [(0x104a,b'\x10'),(0x1022,b'\x04'),(0x101a,b'E'*16),
             (0x1020,bytes.fromhex('020000000135')),(0x1032,pub),(0x103c,bytes([band])),(0x1004,authentication.to_bytes(2,'big')),(0x1010,b'\x00\x08')])
        config={'ssid':'EasyMesh-Test','password':'TestSecret123','enable_6ghz':enabled,**extra}
        if band==8:
            with self.assertRaises(ValueError):wsc.build_m2(m1,{**config,'enable_6ghz':False},b'R'*16)
            bad=m1.replace(wsc.attr(0x1004,b'\x00\x40'),wsc.attr(0x1004,b'\x00\x20'))
            with self.assertRaises(ValueError):wsc.build_m2(bad,config,b'R'*16)
        m2=wsc.build_m2s(m1,config,b'R'*16)[pick]; a=wsc.attrs(m2)
        self.assertEqual(a[0x103c],bytes([band]));self.assertEqual(a[0x1004],authentication.to_bytes(2,'big'))
        peer=dh.DHPublicNumbers(int.from_bytes(a[0x1032],'big'),params.parameter_numbers()).public_key()
        shared=private.exchange(peer)
        digest=lambda k,b:hmac.new(k,b,hashlib.sha256).digest()
        kdk=digest(hashlib.sha256(shared.rjust(192,b'\0')).digest(),b'E'*16+bytes.fromhex('020000000135')+a[0x1039])
        key=b''.join(digest(kdk,i.to_bytes(4,'big')+b'Wi-Fi Easy and Secure Key Derivation'+(640).to_bytes(4,'big')) for i in (1,2,3))
        self.assertEqual(a[0x1005],digest(key[:32],m1+m2[:-12])[:8])
        encrypted=a[0x1018]; dec=Cipher(algorithms.AES(key[32:48]),modes.CBC(encrypted[:16])).decryptor()
        padded=dec.update(encrypted[16:])+dec.finalize(); n=padded[-1]
        self.assertEqual(padded[-n:],bytes([n])*n)
        plain=padded[:-n]; c=wsc.attrs(plain)
        self.assertEqual(c[0x101e],digest(key[:32],plain[:-12])[:8])
        if pick==0:self.assertEqual(c[0x1045],b'EasyMesh-Test'); self.assertEqual(c[0x1027],b'TestSecret123')
        self.assertEqual(c[0x1003],authentication.to_bytes(2,'big')); self.assertEqual(a[0x101a],b'E'*16)
        altered=bytearray(m2); altered[10]^=1
        self.assertNotEqual(a[0x1005],digest(key[:32],m1+altered[:-12])[:8])
        return c
    def test_synthetic_m1_vendor_extensions(self):
        from pathlib import Path
        raw=synthetic_m1()
        a=wsc.inspect_m1(raw)
        self.assertEqual(a[0x1023],b'Test Agent')
        self.assertEqual(a[0x103c],b'\x02')
        m2=wsc.build_m2(raw,{'ssid':'Lab','password':'testPassword1'},b'R'*16)
        self.assertEqual(wsc.attrs(m2)[0x101a],a[0x101a])

    def test_bad_input(self):
        for bad in (b'\x10',b'\x10\x22\x00\x02\x04',wsc.attr(1,b'')*2):
            with self.assertRaises(ValueError):wsc.attrs(bad)
        for config in ({'ssid':'','password':'abcdefgh'},{'ssid':'x','password':'short'}):
            with self.assertRaises(ValueError):wsc.validate_config(config)

if __name__=='__main__':unittest.main()
