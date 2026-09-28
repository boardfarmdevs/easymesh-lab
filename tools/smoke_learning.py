"""Browser interaction checks with synthetic packets; blocks all mutations."""
import json,socket,subprocess,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
proc=subprocess.Popen([sys.executable,str(root/'panel_server.py'),'--port',str(port)],cwd=root)
url=f'http://127.0.0.1:{port}'
try:
 for _ in range(50):
  try:
   boot=json.load(urllib.request.urlopen(url+'/api/bootstrap'));break
  except OSError:time.sleep(.1)
 now=time.time();mac='02:00:00:00:00:10';bssid='02:00:00:00:00:20'
 state={'controller_online':True,'client_telemetry':{mac:{'station':mac,'bssid':bssid,'dbm':-60,'stale':False,'identity':{'label':'iPhone'}}},'operational_bss':[{'radio':'02:00:00:00:00:30','bssid':bssid,'ssid':'Synthetic'}],'observations':{},'optimizer':{'clients':[]}}
 packet={'name':'Synthetic topology','kind':2,'mid':1,'src':'02:00:00:00:00:01','dst':'02:00:00:00:00:02','ethertype':'0x893a','length':25,'flags':128,'fragment':0,'last_fragment':True,'hex':'00'*25,'padding_bytes':0,'tlvs':[{'type':0,'name':'End of message','offset':22,'length':0,'fields':{}}]}
 packets=[{'id':str(i),'event':'packet','direction':'TX' if i%2==0 else 'RX','time':now-10+i*2,'packet':dict(packet,kind=[2,3,7,0x8002][i])} for i in range(4)]
 history=[{'event':'client_sample','time':now-60+i*15,'clients':{mac:{'bssid':bssid,'dbm':-50-i*5,'stale':False,'uplink_mbps':100,'downlink_mbps':200}}} for i in range(4)]
 boot['state']=state
 with sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page();errors=[];posts=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def route(r):
   path=r.request.url.split('/api/')[-1]
   if r.request.method!='GET':posts.append(path);return r.abort()
   value=boot if path=='bootstrap' else state if path=='state' else {'events':packets,'cursor':123} if path.startswith('events') else {'events':history} if path=='history' else [] if path=='commands' else {'sessions':[],'results':[],'service':{}}
   r.fulfill(json=value)
  page.route('**/api/**',route);page.goto(url,wait_until='networkidle')
  assert page.locator('[data-pulse]').count()==4
  assert page.locator('#scopeLegend .scope-key').count()==8
  assert page.locator('#scopeScale').inner_text()=='12 s / div'
  page.locator('[data-pulse="0"]').click()
  assert 'Synthetic topology' in page.locator('#inspector').inner_text()
  page.locator('[data-pulse="0"]').click(modifiers=['Shift']);page.locator('[data-pulse="1"]').click(modifiers=['Shift'])
  assert '2000.000 ms' in page.locator('#scopeStatus').inner_text()
  assert '2 s' in page.locator('#scopeDelta').inner_text()
  span=page.evaluate('scope.span');page.locator('#scopeIn').click();assert page.evaluate('scope.span')==span/2
  page.locator('#scopeTimebase').select_option('0.01')
  assert page.locator('#scopeScale').inner_text()=='10 ms / div'
  assert abs(page.evaluate('scope.span')-.05)<1e-9
  page.locator('#scopeFit').click();assert page.locator('[data-pulse]').count()==4
  box=page.locator('#scopeGraph').bounding_box();before=page.evaluate('scope.start')
  page.mouse.move(box['x']+box['width']*.5,box['y']+20);page.mouse.down();page.mouse.move(box['x']+box['width']*.6,box['y']+20,steps=4);page.mouse.up()
  assert page.evaluate('scope.start')<before
  page.locator('.nav[data-tab="experiments"]').click();page.locator('#clientHistory tbody tr').first.wait_for()
  assert page.locator('#clientHistory tbody tr').count()==4
  assert page.locator('[data-guide="beacon_metrics"]').count()==1
  page.locator('[data-guide="sta_metrics"]').click();assert page.locator('#f-station').input_value()==mac
  page.locator('.nav[data-tab="wire"]').click()
  page.screenshot(path=str(root/'run/learning-scope.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.locator('.nav[data-tab="wire"]').click()
  assert not errors,errors
  assert not posts,posts
  (root/'run').mkdir(exist_ok=True);page.screenshot(path=str(root/'run/learning-mobile.png'),full_page=True)
  browser.close()
 print('Learning UI passed: pulse selection, delta cursors, zoom, drag, history, guided forms, mobile; zero mutations')
finally:proc.terminate();proc.wait(timeout=5)
