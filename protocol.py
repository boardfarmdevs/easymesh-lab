"""Inspectable 1905/Multi-AP packet recipes and lossless teaching decoder."""
import json
import re
import struct
from pathlib import Path
from responder import tlv, macbytes, macstr

NAMES=json.loads(Path(__file__).with_name('protocol_names.json').read_text())
MESSAGE_NAMES={int(k):v for k,v in NAMES['messages'].items()}
TLV_NAMES={int(k):v for k,v in NAMES['tlvs'].items()}
MESSAGE_NAMES[0x8012]='Beacon metrics response'
EXPECT={2:[3],5:[6],0x0d:[0x0e],0x11:[0x12],0x8001:[0x8002],0x8004:[0x8005],0x8006:[0x8007],0x8009:[0x800a],0x800b:[0x800c],0x800d:[0x800e],0x800f:[0x8010],0x8011:[0x8012],0x8014:[0x8000,0x8015],0x8016:[0x8000],0x8019:[0x801a],0x8003:[0x8000],0x801b:[0x801c],0x8027:[0x8028]}
WSC_NAMES={0x104a:'Version',0x1022:'Message type',0x1047:'Enrollee UUID',0x1048:'Registrar UUID',0x1020:'MAC address',0x101a:'Enrollee nonce',0x1039:'Registrar nonce',0x1032:'DH public key',0x1004:'Authentication flags',0x1010:'Encryption flags',0x100d:'Connection flags',0x1008:'Configuration methods',0x1044:'WSC state',0x1021:'Manufacturer',0x1023:'Model name',0x1024:'Model number',0x1042:'Serial',0x1054:'Primary device type',0x1011:'Device name',0x103c:'RF bands',0x1002:'Association state',0x1012:'Device password ID',0x1009:'Configuration error',0x102d:'OS version',0x1049:'Vendor extension',0x1018:'Encrypted settings',0x1005:'Authenticator',0x1045:'SSID',0x1027:'Network key',0x101e:'Key wrap authenticator'}
TEXT_ATTRS={0x1021,0x1023,0x1024,0x1042,0x1011,0x1045}

class Reader:
    def __init__(self,b):self.b=b;self.i=0
    def take(self,n):
        if n<0 or self.i+n>len(self.b):raise ValueError('Truncated field')
        v=self.b[self.i:self.i+n];self.i+=n;return v
    def u8(self):return self.take(1)[0]
    def u16(self):return int.from_bytes(self.take(2),'big')
    def u32(self):return int.from_bytes(self.take(4),'big')
    def mac(self):return macstr(self.take(6))
    def left(self):return len(self.b)-self.i

def decode_value(t,b):
    r=Reader(b)
    if t==0:return {'end':'No more TLVs; remaining Ethernet bytes may be padding.'}
    if t in (1,2,0x82,0x95):return {'mac':r.mac()}
    if t in (13,15):return {'role':'Registrar' if r.u8()==0 else b.hex()}
    if t in (14,16):return {'band':{0:'2.4 GHz',1:'5 GHz',2:'60 GHz',3:'6 GHz'}.get(r.u8(),'Unknown / extension')}
    if t==0xb3:return {'profile':r.u8()}
    if t in (0x80,0x81):return {'services':[{0:'Multi-AP Controller',1:'Multi-AP Agent'}.get(r.u8(),'Unknown') for _ in range(r.u8())]}
    if t==3:
        out={'al_mac':r.mac(),'interfaces':[]}
        for _ in range(r.u8()):out['interfaces'].append({'mac':r.mac(),'media_type':f'0x{r.u16():04x}','media_info':r.take(r.u8()).hex()})
        return out
    if t==7:
        out={'local_interface':r.mac(),'neighbors':[]}
        while r.left()>=7:out['neighbors'].append({'al_mac':r.mac(),'bridge_flags':r.u8()})
        return out
    if t==8:
        scope=r.u8(); out={'scope':'All neighbors' if scope==0 else 'Specific neighbor'}
        if scope:out['neighbor']=r.mac()
        out['direction']={0:'TX',1:'RX',2:'TX + RX'}.get(r.u8());return out
    if t in (9,10):
        out={'local_al':r.mac(),'neighbor_al':r.mac(),'links':[]}
        while r.left():
            x={'local_interface':r.mac(),'neighbor_interface':r.mac(),'media_type':r.u16()}
            if t==9:x.update(bridged=r.u8(),errors=r.u32(),packets=r.u32(),capacity_mbps=r.u16(),availability_percent=r.u16(),phy_mbps=r.u16())
            else:x.update(errors=r.u32(),packets=r.u32(),rssi_raw=r.u8())
            out['links'].append(x)
        return out
    if t==0x0b:return {'oui':r.take(3).hex(':'),'vendor_payload':r.take(r.left()).hex(),'interpretation':'Vendor-specific; not inferred from bytes.'}
    if t==0x11:
        out=[]
        while r.left():
            typ=r.u16();n=r.u16();v=r.take(n);value=v.hex()
            if typ in TEXT_ATTRS:value=v.decode('utf8','replace')
            elif typ==0x1022:value={4:'M1 — enrollee capabilities + DH public key',5:'M2 — registrar public key + encrypted configuration'}.get(v[0],v.hex())
            elif typ==0x1020:value=macstr(v)
            elif typ==0x103c and len(v)==1:value={'raw':v.hex(),'bands':[label for bit,label in ((1,'2.4 GHz'),(2,'5 GHz'),(4,'60 GHz'),(8,'6 GHz')) if v[0]&bit]}
            elif typ in (0x1003,0x1004) and len(v)==2:value={'raw':v.hex(),'authentication':[label for bit,label in ((1,'Open'),(2,'WPA-PSK'),(4,'Shared'),(8,'WPA-Enterprise'),(16,'WPA2-Enterprise'),(32,'WPA2-PSK'),(64,'WPA3-SAE (AKM 8)'),(128,'DPP'),(256,'SAE (AKM 24)')) if int.from_bytes(v,'big')&bit]}
            elif typ==0x1027:value='[network key redacted]'
            out.append({'type':f'0x{typ:04x}','name':WSC_NAMES.get(typ,'Unknown attribute'),'length':n,'value':value})
        return {'attributes':out,'note':'Encrypted settings are ciphertext. A capture alone does not reveal the password.'}
    if t==0x83:
        out=[]
        for _ in range(r.u8()):
            x={'radio':r.mac(),'bss':[]}
            for _ in range(r.u8()):x['bss'].append({'bssid':r.mac(),'ssid':r.take(r.u8()).decode('utf8','replace')})
            out.append(x)
        return {'radios':out}
    if t==0x84:
        out=[]
        for _ in range(r.u8()):
            x={'bssid':r.mac(),'clients':[]}
            for _ in range(r.u16()):x['clients'].append({'station':r.mac(),'associated_seconds':r.u16()})
            out.append(x)
        return {'bss':out}
    if t==0x85:
        out={'radio':r.mac(),'max_bss':r.u8(),'operating_classes':[]}
        for _ in range(r.u8()):
            op=r.u8();power=int.from_bytes(r.take(1),'big',signed=True)
            out['operating_classes'].append({'class':op,'max_eirp_dbm':power,'non_operable_channels':list(r.take(r.u8()))})
        return out
    if t in (0x86,0x87,0x88,0xbe):return {'radio':r.mac(),'capability_bytes':r.take(r.left()).hex(),'note':'Preserved capability bitfield; consult the TLV reference for individual bits.'}
    if t==0x8b:
        out={'radio':r.mac(),'preferences':[]}
        for _ in range(r.u8()):
            op=r.u8();channels=list(r.take(r.u8()));flags=r.u8()
            out['preferences'].append({'operating_class':op,'channels':channels or 'All channels in class','preference':flags>>4,'reason_code':flags&15})
        return out
    if t==0x8d:return {'radio':r.mac(),'limit_dbm':r.u8()}
    if t==0x8e:
        radio=r.mac();code=r.u8();return {'radio':radio,'response_code':code,'result':{0:'Accepted',1:'Declined: current preferences',2:'Declined: most recent preferences',3:'Declined: backhaul would break'}.get(code,'Reserved')}
    if t==0x8f:
        out={'radio':r.mac(),'channels':[{'operating_class':r.u8(),'channel':r.u8()} for _ in range(r.u8())]};out['tx_power_dbm']=r.u8();return out
    if t==0x90:return {'bssid':r.mac(),'station':r.mac()}
    if t==0x91:return {'result_code':r.u8(),'association_frame':r.take(r.left()).hex()}
    if t==0x93:return {'bssids':[r.mac() for _ in range(r.u8())]}
    if t==0x94:
        out={'bssid':r.mac(),'channel_utilization_raw':r.u8(),'associated_stations':r.u16(),'esp_flags':r.u8()}
        out['channel_utilization_percent']=round(out['channel_utilization_raw']*100/255,1)
        out['estimated_service_parameters']=r.take(r.left()).hex();return out
    if t==0x96:
        out={'station':r.mac(),'bss':[]}
        for _ in range(r.u8()):
            x={'bssid':r.mac(),'measurement_age_ms':r.u32(),'downlink_mbps':r.u32(),'uplink_mbps':r.u32(),'uplink_rcpi':r.u8()}
            x['estimated_uplink_dbm']=x['uplink_rcpi']/2-110 if x['uplink_rcpi']<=220 else None
            x['power_bound']='at_most' if x['uplink_rcpi']==0 else 'at_least' if x['uplink_rcpi']==220 else None
            x['measurement_note']='AP receive power, RCPI-derived; 221–254 reserved, 255 unavailable. Not client-side RSSI or SNR.'
            out['bss'].append(x)
        return out
    if t==0x97:
        out={'operating_class':r.u8(),'channels':[]}
        for _ in range(r.u8()):out['channels'].append({'channel':r.u8(),'stations':[r.mac() for _ in range(r.u8())]})
        return out
    if t==0x98:
        out={'operating_class':r.u8(),'stations':[]}
        for _ in range(r.u8()):out['stations'].append({'station':r.mac(),'channel':r.u8(),'age_ms':r.u32(),'rcpi':r.u8()})
        return out
    if t==0x9b:
        out={'source_bssid':r.mac(),'flags':r.u8(),'opportunity_window_seconds':r.u16(),'disassociation_timer_beacons':r.u16(),'stations':[r.mac() for _ in range(r.u8())]}
        if out['flags']&0x80:out['targets']=[{'bssid':r.mac(),'operating_class':r.u8(),'channel':r.u8()} for _ in range(r.u8())]
        out['mode']='Mandate' if out['flags']&0x80 else 'Opportunity';return out
    if t==0x9c:
        out={'source_bssid':r.mac(),'station':r.mac(),'btm_status_code':r.u8()}
        if r.left()>=6:out['target_bssid']=r.mac()
        return out
    if t==0x9d:return {'bssid':r.mac(),'control':{0:'Block',1:'Unblock'}.get(r.u8(),'Extended'),'validity_seconds':r.u16(),'stations':[r.mac() for _ in range(r.u8())]}
    if t==0x9e:return {'backhaul_station':r.mac(),'target_bssid':r.mac(),'operating_class':r.u8(),'channel':r.u8()}
    if t==0xa1:return {'capability_flags':f'0x{r.u8():02x}'}
    if t==0xa2:
        return {'station':r.mac(),**{k:r.u32() for k in ['bytes_sent','bytes_received','packets_sent','packets_received','tx_errors','rx_errors','retransmissions']}}
    if t==0xa3:return {'reason_code':r.u8(),'station':r.mac()}
    if t==0x8a:
        return {'interval_seconds':r.u8(),'radios':[{'radio':r.mac(),'rcpi_threshold':r.u8(),'rcpi_hysteresis':r.u8(),'utilization_threshold':r.u8(),'flags':r.u8()} for _ in range(r.u8())]}
    return {'raw':b.hex(),'note':'Raw TLV retained. Detailed field decoder is not yet implemented.'}

def decode_packet(raw):
    if len(raw)<22 or raw[12:14]!=b'\x89\x3a':raise ValueError('Not an untagged IEEE 1905 Ethernet frame')
    version,reserved,kind,mid,frag,flags=struct.unpack('!BBHHBB',raw[14:22]);pos=22;items=[]
    while pos+3<=len(raw):
        start=pos;t,n=struct.unpack_from('!BH',raw,pos);pos+=3
        if pos+n>len(raw):
            items.append({'type':t,'name':'Truncated TLV','length':n,'offset':start,'hex':raw[pos:].hex(),'fields':{'error':'Declared length exceeds remaining frame'}});break
        value=raw[pos:pos+n];pos+=n
        try:fields=decode_value(t,value)
        except (ValueError,IndexError,struct.error) as e:fields={'decode_error':str(e),'raw':value.hex()}
        items.append({'type':t,'name':TLV_NAMES.get(t,'Unknown TLV'),'length':n,'offset':start,'hex':value.hex(),'fields':fields})
        if t==0:break
    return {'src':macstr(raw[6:12]),'dst':macstr(raw[:6]),'ethertype':'0x893a','version':version,'kind':kind,'name':MESSAGE_NAMES.get(kind,'Unknown message'), 'mid':mid,'fragment':frag,'flags':flags,'last_fragment':bool(flags&128),'relay':bool(flags&64),'length':len(raw),'hex':raw.hex(),'tlvs':items,'padding_bytes':max(0,len(raw)-pos),'fragment_warning':frag!=0 or not flags&128}

# Form schema doubles as a teachable, server-side validated command catalogue.
def field(name,label,kind='text',default='',help=''):
    return dict(name=name,label=label,type=kind,default=default,help=help)
MAC=field('station','Client MAC','mac',help='Use a client you connected to the lab SSID.')
BSS=field('bssid','Source BSSID','bssid')
RADIO=field('radio','Radio ID','radio')
OP=field('opclass','Operating class','number',81)
CH=field('channel','Channel','number',6)
CATALOG=[]
def recipe(id,title,group,kind,description,fields=[],effect='Query',expected=''):
    CATALOG.append(dict(id=id,title=title,group=group,kind=kind,description=description,fields=fields,effect=effect,expected=expected or ', '.join(MESSAGE_NAMES.get(x,hex(x)) for x in EXPECT.get(kind,[])) or 'No direct response defined'))
recipe('topology','Discover topology','Discover',2,'Ask for interfaces, neighbors, operational BSSs and associated clients.')
recipe('capabilities','Read AP capabilities','Discover',0x8001,'Learn radio operating classes and HT/VHT/HE capabilities.')
recipe('link_metrics','Read Ethernet link metrics','Telemetry',5,'Request transmit and receive statistics between 1905 neighbors.')
recipe('higher_layer','Read device identity','Discover',0x0d,'Request higher-layer identity and addressing information. Response depends on firmware.')
recipe('generic_phy','Read generic PHY','Discover',0x11,'Ask for generic media descriptions beyond standard interface types.')
recipe('backhaul_capabilities','Read backhaul STA capabilities','Discover',0x8027,'Ask a Profile 2 agent about its backhaul station interfaces.')
recipe('channel_preferences','Read channel preferences','Radio',0x8004,'See which channels each radio prefers and why.')
recipe('ap_metrics','Read BSS telemetry','Telemetry',0x800b,'Read channel utilization, station count and estimated service parameters. Blank BSSID uses all observed BSSs.',[field('bssid','BSSID (blank = all observed)','optional_bssid')])
recipe('client_capabilities','Read client capabilities','Telemetry',0x8009,'Request the client association frame from the AP.',[BSS,MAC])
recipe('sta_metrics','Read associated client metrics','Telemetry',0x800d,'Read client link rates and uplink RCPI measured by the AP.',[MAC])
recipe('unassociated_metrics','Measure unassociated client','Telemetry',0x800f,'Ask the radio to measure one station on a channel. Requires advertised measurement support.',[MAC,OP,CH])
recipe('beacon_metrics','Ask client for beacon measurements','Telemetry',0x8011,'Request a client-side beacon report. Requires a connected client with compatible measurement support.',[MAC,OP,CH,field('target_bssid','Measured BSSID','mac','ff:ff:ff:ff:ff:ff')],expected='Beacon metrics response; a client may decline or return no measurements')
recipe('metric_policy','Set telemetry reporting interval','Telemetry',0x8003,'Request periodic AP metrics and client traffic/link statistics for one radio. Interval 0 stops periodic reporting.',[RADIO,field('interval','Interval (seconds)','number',30)],'Changes reporting')
recipe('channel_selection','Request a channel','Radio',0x8006,'Send a preferred channel. The agent may decline; inspect its response code.',[RADIO,OP,CH],'May interrupt Wi-Fi')
recipe('tx_power','Set transmit power limit','Radio',0x8006,'Request a maximum transmit power for one radio. The agent enforces regulatory/device limits.',[RADIO,field('power','Power limit (dBm)','number',17)],'Changes radio power')
recipe('channel_scan','Request channel scan','Radio',0x801b,'Request a fresh scan of one operating class/channel. Scan support and reporting depend on agent profile.',[RADIO,OP,CH],'May affect airtime')
recipe('steer','Steer a client (BTM)','Steering',0x8014,'Ask the agent to steer one client to a target BSS. An ACK is not proof of a roam; inspect BTM status and subsequent association.',[BSS,MAC,field('target_bssid','Target BSSID','mac'),OP,CH],'May move the selected client', '1905 ACK and/or steering BTM report; verify subsequent client association')
recipe('block','Temporarily block association','Steering',0x8016,'Prevent one client associating to a source BSS for a bounded time. This does not itself disconnect a currently associated client.',[BSS,MAC,field('seconds','Validity (seconds)','number',30)],'Temporarily restricts one client')
recipe('unblock','Allow association','Steering',0x8016,'Remove an association block for one client on a BSS.',[BSS,MAC],'Changes association policy')
recipe('backhaul_steer','Steer wireless backhaul','Steering',0x8019,'Request a wireless backhaul station move. Our current uplink is Ethernet; this may be inapplicable.',[field('station','Backhaul STA MAC','mac'),field('target_bssid','Target BSSID','mac'),OP,CH],'May interrupt backhaul')
recipe('enable_6ghz','Enable 6 GHz / WPA3','Onboarding',0x0a,'Enable the experimental 6 GHz WSC path and Profile 2 lab persona. Send renew for 2.4/5/6 GHz; use WPA3-SAE on 6 GHz and retain WPA2 on existing bands. Requires agent support and a Wi-Fi 6E/7 client.',[],'May interrupt Wi-Fi','Fresh 6 GHz M1 → SAE M2 → 6 GHz operational BSS; client association separately verifies RF/security')
recipe('reonboard','Re-onboard current SSID','Onboarding',0x0a,'Send renew for configured bands, then watch fresh M1 and encrypted M2 exchanges. Does not factory-reset the extender.',[],'May interrupt Wi-Fi','Fresh M1 → M2 → topology containing the configured SSID')
recipe('set_ssid','Set SSID & re-onboard','Onboarding',0x0a,'Apply a new SSID through WSC: WPA2 on 2.4/5 GHz, SAE on 6 GHz when enabled. Blank password preserves the current key.',[field('ssid','SSID','text','EasyMesh-Lab'),field('password','New password (optional)','password')],'Changes Wi-Fi credentials','New SSID in AP Operational BSS reports')
recipe('polling','Automatic query mode','Learning',None,'Pause or resume the controller’s periodic topology/capability queries. Automatic responses and topology announcements continue.',[field('enabled','Enable automatic queries','select','true')],'Local controller setting','Controller state updated')
recipe('raw','Compose a CMDU','Advanced',None,'Build an untagged, single-fragment CMDU addressed only to this lab agent. Add TLVs as JSON: [{"type":"0x95","hex":"..."}]. EOM is appended. This is encoding access, not an implementation of every protocol state machine.',[field('message_type','Message type (hex)','text','0x0002'),field('tlvs','TLV list (JSON)','textarea','[]')],'Depends on message type')

LOOKUP={x['id']:x for x in CATALOG}
def number(p,k,lo=0,hi=255):
    try:v=int(str(p[k]),0) if isinstance(p[k],str) else int(p[k])
    except (KeyError,ValueError,TypeError):raise ValueError(f'{k}: enter an integer')
    if not lo<=v<=hi:raise ValueError(f'{k}: must be {lo}..{hi}')
    return v

def mac(p,k,optional=False):
    s=str(p.get(k,'')).strip().lower()
    if optional and not s:return None
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',s):raise ValueError(f'{k}: enter a six-byte MAC address')
    return macbytes(s)

def build_command(name,p,state):
    if name not in LOOKUP:raise ValueError('Unknown command')
    if not isinstance(p,dict):raise ValueError('Parameters must be an object')
    kind=LOOKUP[name]['kind'];body=b''
    if name in ('reonboard','set_ssid','enable_6ghz','polling'):return []
    if name=='link_metrics':body=tlv(8,b'\x00\x02')
    elif name=='ap_metrics':
        target=mac(p,'bssid',True)
        bss=[target] if target else list(dict.fromkeys(macbytes(x['bssid']) for x in state.get('operational_bss',[])))
        if not bss:raise ValueError('No observed BSS yet. Read topology or enter a BSSID.')
        if len(bss)>32:raise ValueError('Too many BSSs')
        body=tlv(0x93,bytes([len(bss)])+b''.join(bss))
    elif name=='client_capabilities':body=tlv(0x90,mac(p,'bssid')+mac(p,'station'))
    elif name=='sta_metrics':body=tlv(0x95,mac(p,'station'))
    elif name=='unassociated_metrics':body=tlv(0x97,bytes([number(p,'opclass',1),1,number(p,'channel',1,233),1])+mac(p,'station'))
    elif name=='beacon_metrics':body=tlv(0x99,mac(p,'station')+bytes([number(p,'opclass',1),number(p,'channel',1,233)])+mac(p,'target_bssid')+b'\x00\x00\x00\x00')
    elif name=='metric_policy':body=tlv(0x8a,bytes([number(p,'interval'),1])+mac(p,'radio')+bytes([0,0,0,0xc0]))
    elif name=='channel_selection':body=tlv(0x8b,mac(p,'radio')+bytes([1,number(p,'opclass',1),1,number(p,'channel',1,233),0xf0]))
    elif name=='tx_power':body=tlv(0x8d,mac(p,'radio')+bytes([number(p,'power',0,30)]))
    elif name=='channel_scan':body=tlv(0xa6,b'\x80\x01'+mac(p,'radio')+bytes([1,number(p,'opclass',1),1,number(p,'channel',1,233)]))
    elif name=='steer':body=tlv(0x9b,mac(p,'bssid')+b'\x80\x00\x00\x00\x00\x01'+mac(p,'station')+b'\x01'+mac(p,'target_bssid')+bytes([number(p,'opclass',1),number(p,'channel',1,233)]))
    elif name in ('block','unblock'):body=tlv(0x9d,mac(p,'bssid')+bytes([0 if name=='block' else 1])+struct.pack('!H',number(p,'seconds',1,300) if name=='block' else 0)+b'\x01'+mac(p,'station'))
    elif name=='backhaul_steer':body=tlv(0x9e,mac(p,'station')+mac(p,'target_bssid')+bytes([number(p,'opclass',1),number(p,'channel',1,233)]))
    elif name=='raw':
        kind=number(p,'message_type',0,65535)
        try:values=json.loads(p.get('tlvs','[]'))
        except (ValueError,TypeError):raise ValueError('TLV list must be valid JSON')
        if not isinstance(values,list) or len(values)>32:raise ValueError('Use a list of at most 32 TLVs')
        for x in values:
            if not isinstance(x,dict):raise ValueError('Each TLV must be an object')
            t=number(x,'type',1,255)
            try:v=bytes.fromhex(x.get('hex',''))
            except (ValueError,TypeError):raise ValueError('Invalid TLV hex bytes')
            body+=tlv(t,v)
    if len(body)>1400:raise ValueError('This builder supports at most 1400 bytes of TLVs')
    return [(kind,body)]
