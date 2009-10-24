#! /usr/bin/python
# -*- coding: utf-8 -*-
import logging,os,sys
import pyvkt
import pyvkt_config as conf

confName="pyvkt.cfg"
if(os.environ.has_key("PYVKT_CONFIG")):
    confName=os.environ["PYVKT_CONFIG"]
conf.read(confName)
lvl=logging.WARNING
if ("--debug" in sys.argv):
    lvl=logging.DEBUG
if ("--info" in sys.argv):
    lvl=logging.INFO
logging.basicConfig(level=lvl,format='  *  %(asctime)s [%(levelname)s] %(message)s')
s=pyvkt.pyvk_t(conf.get("general","jid"))
s.connect(conf.get("general","server"),conf.get("general","port"),conf.get("general","secret"))
logging.warn("connected")
if ("--autologin" in sys.argv):
    s.addResource(conf.get("general","admin"))
if ('--admin-only' in sys.argv):
    print "isActive=0"
    s.isActive=0
s.startPoll()
try:
    s.main()
except KeyboardInterrupt:
    s.term()
