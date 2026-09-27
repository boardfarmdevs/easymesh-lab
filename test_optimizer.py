import unittest
from optimizer import Optimizer

class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.policy=Optimizer()
        self.client={'station':'02:00:00:00:00:11','bssid':'02:00:00:00:00:22','ssid':'Lab','dbm':-80,'stale':False,'associated_seconds':200}
        self.target={'station':self.client['station'],'bssid':'02:00:00:00:00:33','ssid':'Lab','security_compatible':True,'dbm':-60,'source':'unassociated_sta_metrics','measured_at':1000,'operating_class':115,'channel':36,'comparable_to_current':True}
    def test_no_guessing_targets_or_stale_signal(self):
        self.assertEqual(self.policy.assess(self.client,[],1000)['status'],'observe')
        for key,value in [('stale',True),('dbm',None),('associated_seconds',2),('dbm',-60),('bound','at_most')]:
            self.assertEqual(self.policy.assess({**self.client,key:value},[self.target],1000)['status'],'observe')
        for key,value in [('measured_at',900),('measured_at',1001),('security_compatible',False),('ssid','Other'),('comparable_to_current',False),('dbm',-75)]:
            self.assertEqual(self.policy.assess(self.client,[{**self.target,key:value}],1000)['status'],'observe')
    def test_execution_requires_approval_and_cooldown(self):
        p=self.policy.assess(self.client,[self.target],1000);sent=[]
        queue=lambda name,params:sent.append((name,params))
        with self.assertRaises(PermissionError):self.policy.queue_approved(p,queue,now=1000)
        self.assertEqual(sent,[])
        self.policy.queue_approved(p,queue,approved=True,now=1000)
        self.assertEqual(sent[0][0],'steer')
        self.assertEqual(self.policy.observe_outcome(self.client['station'],self.target['bssid'],999)['status'],'awaiting_fresh_association')
        self.assertEqual(self.policy.observe_outcome(self.client['station'],self.client['bssid'],1002)['status'],'awaiting_target_association')
        self.assertEqual(self.policy.observe_outcome(self.client['station'],self.target['bssid'],1003)['status'],'target_association_observed')
        with self.assertRaises(ValueError):self.policy.queue_approved(p,queue,approved=True,now=1001)
        self.assertEqual(self.policy.assess(self.client,[self.target],1001)['reason'],'Steering cooldown active')

if __name__=='__main__':unittest.main()
