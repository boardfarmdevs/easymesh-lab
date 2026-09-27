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
        self.roundtrip(2,0x20,False)
    def test_sae_6ghz_independent_enrollee(self):
        self.roundtrip(8,0x40,True)
    def roundtrip(self,band,authentication,enabled):
        params=dh.DHParameterNumbers(wsc.P,2).parameters()
        private=params.generate_private_key(); pub=private.public_key().public_numbers().y.to_bytes(192,'big')
        m1=b''.join(wsc.attr(t,b) for t,b in [(0x104a,b'\x10'),(0x1022,b'\x04'),(0x101a,b'E'*16),
             (0x1020,bytes.fromhex('020000000135')),(0x1032,pub),(0x103c,bytes([band])),(0x1004,authentication.to_bytes(2,'big')),(0x1010,b'\x00\x08')])
        config={'ssid':'EasyMesh-Test','password':'TestSecret123','enable_6ghz':enabled}
        if band==8:
            with self.assertRaises(ValueError):wsc.build_m2(m1,{**config,'enable_6ghz':False},b'R'*16)
            bad=m1.replace(wsc.attr(0x1004,b'\x00\x40'),wsc.attr(0x1004,b'\x00\x20'))
            with self.assertRaises(ValueError):wsc.build_m2(bad,config,b'R'*16)
        m2=wsc.build_m2(m1,config,b'R'*16); a=wsc.attrs(m2)
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
        self.assertEqual(c[0x1045],b'EasyMesh-Test'); self.assertEqual(c[0x1027],b'TestSecret123')
        self.assertEqual(c[0x1003],authentication.to_bytes(2,'big')); self.assertEqual(a[0x101a],b'E'*16)
        altered=bytearray(m2); altered[10]^=1
        self.assertNotEqual(a[0x1005],digest(key[:32],m1+altered[:-12])[:8])
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
