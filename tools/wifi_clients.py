#!/usr/bin/env python3
"""Manage explicitly enrolled USB Wi-Fi clients in independent network namespaces."""
import json, os, signal, subprocess, time, re, grp
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
RUN=BASE/'run/wifi-clients'
CONFIG=Path('/etc/easymesh-wifi-clients.json')

def call(*args,check=True):
 return subprocess.run(args,check=check,capture_output=True,text=True).stdout.strip()
def inside(ns,*args,check=True):
 return call('ip','netns','exec',ns,*args,check=check)

def main():
 os.umask(0o077);RUN.mkdir(parents=True,exist_ok=True)
 cfg=json.loads(CONFIG.read_text());wifi=json.loads((BASE/'config.json').read_text())
 children={};logs={}
 def stop(*_):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,stop)
 try:
  while True:
   status=[];radio_observations=[]
   for c in cfg['clients']:
    ns=c['namespace'];mac=c['mac'];iface='wlan0'
    if ns not in [l.split()[0] for l in call('ip','netns','list').splitlines()]:call('ip','netns','add',ns)
    links=json.loads(inside(ns,'ip','-j','link'))
    present=next((l for l in links if l.get('address')==mac),None)
    if not present:
     for path in Path('/sys/class/net').iterdir():
      if (path/'phy80211').exists() and (path/'address').read_text().strip()==mac:
       call('ip','link','set',path.name,'down')
       call('iw','phy',(path/'phy80211').resolve().name,'set','netns','name',ns)
       links=json.loads(inside(ns,'ip','-j','link'));present=next((l for l in links if l.get('address')==mac),None);break
    if not present:
     if ns in children:
      children.pop(ns).terminate();logs.pop(ns).close()
     status.append({'namespace':ns,'mac':mac,'state':'adapter_absent'});continue
    if present['ifname']!=iface:inside(ns,'ip','link','set',present['ifname'],'name',iface)
    if ns not in children or children[ns].poll() is not None:
     inside(ns,'ip','link','set','lo','up');inside(ns,'iw','reg','set',cfg['country'])
     inside(ns,'ip','link','set',iface,'up');inside(ns,'ip','addr','replace',c['address'],'dev',iface)
     inside(ns,'iw','dev',iface,'set','power_save','off',check=False)
     if ns in logs:logs.pop(ns).close()
     conf=RUN/(ns+'.conf')
     # Hex SSID avoids configuration injection; JSON quoting escapes the passphrase.
     security=c.get('security','wpa2')
     if security not in ('wpa2','wpa3'):raise ValueError('security must be wpa2 or wpa3')
     text='ctrl_interface=/run/wpa_'+ns+'\ncountry='+cfg['country']+'\nsae_pwe=2\nnetwork={\n ssid='+wifi['ssid'].encode().hex()+'\n'
     if security=='wpa3':
      text+=' sae_password='+json.dumps(wifi['password'])+'\n key_mgmt=SAE\n ieee80211w=2\n'
     else:
      text+=' psk='+json.dumps(wifi['password'])+'\n key_mgmt=WPA-PSK\n ieee80211w=1\n'
     if c.get('bssid'):text+=' bssid='+c['bssid']+'\n'
     if c.get('scan_freq'):text+=' scan_freq='+str(int(c['scan_freq']))+'\n'
     conf.write_text(text+'}\n');conf.chmod(0o600)
     logs[ns]=(RUN/(ns+'.log')).open('a')
     children[ns]=subprocess.Popen(['ip','netns','exec',ns,'wpa_supplicant','-i',iface,'-c',str(conf)],stdout=logs[ns],stderr=subprocess.STDOUT)
    link=inside(ns,'iw','dev',iface,'link',check=False)
    info=inside(ns,'iw','dev',iface,'info',check=False)
    channel=re.search(r'channel (\d+) \(([\d.]+) MHz\), width: (\d+) MHz',info)
    bssid=re.search(r'Connected to ([0-9a-f:]+)',link)
    if channel and bssid:radio_observations.append({'client':mac,'bssid':bssid[1],'channel':int(channel[1]),'frequency_mhz':float(channel[2]),'width_mhz':int(channel[3]),'time':time.time()})
    status.append({'namespace':ns,'mac':mac,'address':c['address'],'radio_info':info,'link':link,'station':inside(ns,'iw','dev',iface,'station','dump',check=False)})
   tmp=RUN/'status.tmp';tmp.write_text(json.dumps({'time':time.time(),'clients':status},indent=2));tmp.replace(RUN/'status.json')
   public=BASE/'run/wifi-radio-observations.tmp';public.write_text(json.dumps(radio_observations));os.chown(public,0,grp.getgrnam('easymesh').gr_gid);public.chmod(0o640);public.replace(BASE/'run/wifi-radio-observations.json')
   time.sleep(5)
 except KeyboardInterrupt:pass
 finally:
  for p in children.values():
   p.terminate()
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for f in logs.values():f.close()
  # Return physical radios to the VM default namespace on an intentional stop.
  for c in cfg['clients']:
   ns=c['namespace']
   try:
    data=inside(ns,'iw','dev');phy=next((l.strip()[4:] for l in data.splitlines() if l.strip().startswith('phy#')),None)
    if phy:
     inside(ns,'ip','addr','flush','dev','wlan0');inside(ns,'ip','link','set','wlan0','down')
     inside(ns,'ip','link','set','wlan0','name','wlx'+c['mac'].replace(':',''))
     inside(ns,'iw','phy','phy'+phy,'set','netns','1')
   except subprocess.CalledProcessError:pass
if __name__=='__main__':main()
