"""UI assertions against synthetic telemetry; all network mutations are blocked."""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

url=os.environ.get('LAB_PANEL_URL','http://127.0.0.1:8765')
mac='02:00:00:00:00:11';bssid='02:00:00:00:00:22';radio='02:00:00:00:00:33'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page(reduced_motion="reduce");errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    boot=page.request.get(url+'/api/bootstrap').json()
    fixture={'controller':'02:00:00:00:00:01','target':'02:00:00:00:00:02','controller_online':True,'agent_recent':True,
             'last_agent_at':time.time(),'operational_bss':[{'radio':radio,'bssid':bssid,'ssid':'Synthetic'}],
             'radios':{radio:{'rf_bands':2}},'observations':{'clients':{'type':0x84,'time':time.time(),'fields':{'bss':[{'bssid':bssid,'clients':[{'station':mac}]}]}}},
             'client_telemetry':{mac:{'dbm':-60,'color':'green','stale':False,'rcpi':100,'age_seconds':1,'snr_db':None,'identity':{'label':'Mac laptop','inferred':True,'confidence':'medium'}}}}
    boot['state']=fixture
    def route(r):
        path=r.request.url.split('/api/')[-1]
        if r.request.method!='GET':return r.abort()
        value=boot if path=='bootstrap' else fixture if path=='state' else {'events':[],'cursor':0} if path.startswith('events') else [] if path=='commands' else {'sessions':[],'results':[]}
        r.fulfill(json=value)
    page.route('**/api/**',route);page.goto(url,wait_until='networkidle')
    page.locator('.nav[data-tab="topology"]').click()
    assert page.locator('.signal-bars').count()==1
    page.locator(f'[data-node="client-{mac}"]').click()
    assert page.locator('#topologyDetail .signal-card.green').count()==1
    assert 'not reported' in page.locator('#topologyDetail').inner_text()
    assert 'Mac laptop' in page.locator('#topologyDetail').inner_text()
    for color,power,stale in [('yellow',-70,False),('red',-85,False),('gray',-60,True),('gray',None,True)]:
        fixture['client_telemetry'][mac].update(color=color,dbm=power,stale=stale)
        page.evaluate('(s)=>{state=s;renderTopology();}',fixture)
        assert page.locator(f'#topologyDetail .signal-card.{color}').count()==1
    page.locator('.nav[data-tab="telemetry"]').click()
    assert page.locator('#clientList .signal-card').count()==1
    page.set_viewport_size({'width':390,'height':844});page.locator('.nav[data-tab="topology"]').click()
    assert not errors,errors
    out=Path('run/telemetry-ui.png');out.parent.mkdir(exist_ok=True);page.screenshot(path=str(out),full_page=True)
    browser.close()
print('Synthetic telemetry UI: signal colors, stale/missing data, identity, SNR unknown, mobile passed')
