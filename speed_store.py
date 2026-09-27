"""Shared, private speed-test session/job files; no shell or client execution."""
import json,math,os,time,uuid
from pathlib import Path
BASE=Path(__file__).resolve().parent/'speed'
def read(path,default=None):
 try:return json.loads(path.read_text())
 except (OSError,ValueError):return default

def atomic(path,value):
 path.parent.mkdir(exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(value,f)
 os.replace(tmp,path)

def valid_id(id):
 if not isinstance(id,str) or len(id)!=32 or any(c not in '0123456789abcdef' for c in id):raise ValueError('Invalid session ID')
 return id

def sessions():
 now=time.time();out=[]
 for p in (BASE/'sessions').glob('*.json'):
  s=read(p,{})
  if s and now-s.get('seen',0)<86400:
   s.pop('token',None);s['online']=now-s['seen']<15;out.append(s)
 return sorted(out,key=lambda s:s['seen'],reverse=True)

def enqueue(id):
 valid_id(id);s=read(BASE/'sessions'/f'{id}.json',{})
 if time.time()-s.get('seen',0)>15:raise ValueError('Open the speed-test page on that client first')
 old=read(BASE/'jobs'/f'{id}.json',{})
 if old.get('status') in ('queued','running') and time.time()-old.get('created_at',0)<60:raise ValueError('This client already has a pending test')
 job={'id':uuid.uuid4().hex,'session':id,'status':'queued','seconds_per_direction':6,'created_at':time.time()}
 atomic(BASE/'jobs'/f'{id}.json',job);return job

def snapshot():
 return {'url':'http://10.203.88.1:8080','sessions':sessions(),'results':sorted([read(p,{}) for p in (BASE/'results').glob('*.json')],key=lambda r:r.get('finished_at',0),reverse=True)[:30],'leases':read(BASE/'leases.json',{}),'service':read(BASE/'service.json',{})}
