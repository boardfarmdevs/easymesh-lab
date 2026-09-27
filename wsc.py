"""WSC M1/M2 crypto and WPA2 / opt-in 6 GHz WPA3-SAE credential encoding.
Reference: prplMesh-old/src/al_wsc.c; interoperable wire format, Python implementation.
"""
import hashlib
import hmac
import secrets
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# RFC 3526 MODP group 5, used by WSC (1536 bits, generator 2).
P = int('''FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E08
8A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD
3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625
E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A8
99FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163
BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3A
D961C62F356208552BB9ED529077096966D670C354E4ABC9804
F1746C08CA237327FFFFFFFFFFFFFFFF'''.replace('\n',''), 16)

def attr(t, b):
    return struct.pack('!HH', t, len(b)) + b

def attrs(data):
    result = {}; pos = 0
    while pos < len(data):
        if len(data)-pos < 4:
            raise ValueError('truncated WSC attribute header')
        t, n = struct.unpack_from('!HH', data, pos); pos += 4
        if pos+n > len(data) or (t in result and t != 0x1049):
            raise ValueError('truncated or duplicate WSC attribute')
        # Multiple vendor extensions are legal; crypto uses the unchanged raw M1.
        result.setdefault(t, data[pos:pos+n]); pos += n
    return result

def hm(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()

def derive(shared, enonce, mac, rnonce):
    dhkey = hashlib.sha256(shared.to_bytes(192, 'big')).digest()
    kdk = hm(dhkey, enonce + mac + rnonce)
    label = b'Wi-Fi Easy and Secure Key Derivation'
    keys = b''.join(hm(kdk, struct.pack('!I', i) + label + struct.pack('!I', 640)) for i in range(1,4))[:80]
    return keys[:32], keys[32:48]

def validate_config(config):
    if not isinstance(config.get('enable_6ghz',False),bool):
        raise ValueError('enable_6ghz must be a boolean')
    if type(config.get('controller_profile',1)) is not int or config.get('controller_profile',1) not in (1,2):
        raise ValueError('controller_profile must be 1 or 2')
    ssid = config['ssid'].encode('utf-8'); password = config['password'].encode('ascii')
    if not 1 <= len(ssid) <= 32:
        raise ValueError('SSID must be 1..32 UTF-8 bytes')
    if not 8 <= len(password) <= 63 or any(x < 32 or x > 126 for x in password):
        raise ValueError('Password must be 8..63 printable ASCII characters')
    return ssid, password

def inspect_m1(data):
    a = attrs(data)
    for t, n in ((0x1022,1),(0x101a,16),(0x1020,6),(0x1032,192),(0x103c,1),(0x1004,2),(0x1010,2)):
        if len(a.get(t,b'')) != n:
            raise ValueError(f'M1 missing/invalid attribute {t:04x}')
    if a[0x1022] != b'\x04':
        raise ValueError('WSC is not M1')
    public = int.from_bytes(a[0x1032], 'big')
    if not 2 <= public <= P-2 or pow(public, (P-1)//2, P) != 1:
        raise ValueError('invalid DH public key')
    return a

def build_m2(m1, config, registrar_uuid):
    ssid, password = validate_config(config); a = inspect_m1(m1)
    rf=a[0x103c][0]
    if rf==8:
        if not config.get('enable_6ghz',False):raise ValueError('6 GHz provisioning is disabled')
        authentication=0x40  # WSC SAE / WPA3-Personal, AKM suite 8.
    elif rf in (1,2,3):authentication=0x20
    else:raise ValueError('Unsupported or ambiguous WSC RF band')
    if not (int.from_bytes(a[0x1004],'big') & authentication and int.from_bytes(a[0x1010],'big') & 8):
        raise ValueError('radio does not advertise '+('WPA3-SAE/AES' if rf==8 else 'WPA2-PSK/AES'))
    auth_bytes=struct.pack('!H',authentication)
    secret = secrets.randbits(320) | (1 << 319)
    public = pow(2, secret, P).to_bytes(192,'big'); rnonce = secrets.token_bytes(16)
    auth, wrap = derive(pow(int.from_bytes(a[0x1032],'big'),secret,P),a[0x101a],a[0x1020],rnonce)
    fields = [(0x104a,b'\x10'),(0x1022,b'\x05'),(0x101a,a[0x101a]),
              (0x1039,rnonce),(0x1048,registrar_uuid),(0x1032,public),
              (0x1004,auth_bytes),(0x1010,b'\x00\x08'),(0x100d,b'\x01'),
              (0x1008,b'\x06\x80'),(0x1021,b'Python Lab'),(0x1023,b'EasyMesh Controller'),
              (0x1024,b'1'),(0x1042,b'lab-controller'),(0x1054,bytes.fromhex('00060050f2000002')),
              (0x1011,b'Python EasyMesh Lab'),(0x103c,a[0x103c]),(0x1002,b'\x00\x01'),
              (0x1009,b'\x00\x00'),(0x1012,b'\x00\x04'),(0x102d,b'\x80\x00\x00\x01'),
              (0x1049,bytes.fromhex('00372a000120'))]
    # Multi-AP fronthaul bit 0x20; wired backhaul, no wireless backhaul BSS.
    plain = b''.join(attr(t,b) for t,b in [(0x1045,ssid),(0x1003,auth_bytes),
                   (0x100f,b'\x00\x08'),(0x1027,password),(0x1020,a[0x1020]),
                   (0x1049,bytes.fromhex('00372a000120060120'))])
    plain += attr(0x101e,hm(auth,plain)[:8])
    pad = 16-len(plain)%16; plain += bytes([pad])*pad; iv=secrets.token_bytes(16)
    enc=Cipher(algorithms.AES(wrap),modes.CBC(iv)).encryptor()
    fields.append((0x1018,iv+enc.update(plain)+enc.finalize()))
    m2=b''.join(attr(t,b) for t,b in fields)
    return m2+attr(0x1005,hm(auth,m1+m2)[:8])
