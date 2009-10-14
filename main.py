#! /usr/bin/python
# -*- coding: utf-8 -*-
import logging,os,sys
import pyvkt
import pyvkt_config as conf
import guppy.heapy.RM
confName="pyvkt.cfg"
if(os.environ.has_key("PYVKT_CONFIG")):
    confName=os.environ["PYVKT_CONFIG"]
#import sys

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
#if ("--autologin" in sys.argv):
    #s.addResource('eqx@eqx.su')
if ('--admin-only' in sys.argv):
    print "isActive=0"
    s.isActive=0
s.startPoll()
#print 111
import cProfile
try:
    #cProfile.run('s.main()','profile')
    s.main()
except KeyboardInterrupt:
    s.term()