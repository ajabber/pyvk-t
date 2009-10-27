#! /usr/bin/python
# -*- coding: utf-8 -*-
import logging,os,sys
import pyvkt.component
import pyvkt.config as conf
import optparse
confName="pyvkt.cfg"
if(os.environ.has_key("PYVKT_CONFIG")):
    confName=os.environ["PYVKT_CONFIG"]
    
op=optparse.OptionParser()
op.add_option('-c','--config',default=confName,help='configuration file name')
op.add_option('-a','--admin-only',action='store_true', default=False, help='only admin can use transport when this flag is enabled')
op.add_option('-l','--autologin', action='store_true', default=False)

opt,args=op.parse_args()
conf.read(opt.config)
lvl=logging.WARNING
if ("--debug" in sys.argv):
    lvl=logging.DEBUG
if ("--info" in sys.argv):
    lvl=logging.INFO

logging.basicConfig(level=lvl,format='  *  %(asctime)s [%(levelname)s] %(message)s')
s=pyvkt.component.pyvk_t(conf.get("general","jid"))
s.connect(conf.get("general","server"),conf.get("general","port"),conf.get("general","secret"))
logging.warn("connected")
if (opt.autologin):
    s.addResource(conf.get("general","admin"))
if (opt.admin_only):
    print "isActive=0"
    s.isActive=0
s.startPoll()
try:
    s.main()
except KeyboardInterrupt:
    s.term()
