"""Synthetic WSC enrollee; no device capture, identity or credential material."""
from wsc import P, attr

def synthetic_m1():
    fields = [(0x104a,b'\x10'),(0x1022,b'\x04'),(0x101a,b'E'*16),
              (0x1020,bytes.fromhex('020000000135')),
              (0x1032,pow(2,123456789,P).to_bytes(192,'big')),
              (0x103c,b'\x02'),(0x1004,b'\x00\x20'),(0x1010,b'\x00\x08'),
              (0x1021,b'Synthetic'),(0x1023,b'Test Agent'),
              (0x1049,bytes.fromhex('00372a000120')),
              (0x1049,bytes.fromhex('00372a060120'))]
    return b''.join(attr(t,v) for t,v in fields)
