# -*- coding: utf-8 -*-
import libvkontakte
from twisted.python.threadpool import ThreadPool
from twisted.enterprise.adbapi import safe 
import pyvkt_global as pyvkt
from twisted.internet import defer
import sys,os,cPickle
from base64 import b64encode,b64decode
class user:
    def __init__(self,trans,jid):
        bjid=pyvkt.bareJid(jid)
        #print "user constructor: %s"%bjid
        
        self.trans=trans
        self.bjid=bjid
        self.resources=[]
        self.lock=0
        self.active=1
        self.FUsent=0
        pass
    def addResource(self,jid):
        if(len(self.resources)==0 and self.lock==0):
            self.login()
        if (jid in self.resources):
            pass
        else:
            self.resources.append(jid)
            #TODO resend presence
    def delResource(self,jid):
        if (jid in self.resources):
            self.resources.remove(jid)
        if (len(self.resources)==0):
            self.logout()
        #TODO any resources left?
    def createThread(self,jid,email,pw):
        jid=pyvkt.bareJid(jid)
        # TODO self.jid
        self.thread=libvkontakte.vkonThread(cli=self.trans,jid=jid,email=email,passw=pw)
        #del self.locks[jid]
        self.lock=0
        self.pool=ThreadPool(1,1)
        self.pool.start()
        self.thread.start()
        self.thread.feedOnly=0
    def login(self):
        # TODO bare jid?
        self.active=1
        #print "self.bjid:%s"%self.bjid
        if (self.trans.isActive==0 and self.bjid!=self.trans.admin):
            #print ("isActive==0, login attempt aborted")
            if (self.FUsent!=0):
                #self.trans.sendMessage(self.trans.jid,self.bjid,u"В настоящий момент транспорт неактивен, попробуйте подключиться позже")
                self.FUsent=1
            self.lock=0
            self.active=0
            #WARN bjid?
            return
        if (self.lock):
            
            return
        self.lock=1
        mq="SELECT * FROM users WHERE jid='%s'"%safe(self.bjid)
        print mq
        q=self.trans.dbpool.runQuery(mq)
        q.addCallback(self.login1)
    def login1(self,data):
        t=data[0]
        bjid=data[0][0].lower()
        if (bjid!=self.bjid):
            return
        defer.execute(self.createThread,jid=bjid,email=data[0][1],pw=data[0][2])
        try:
            if (data[0][3]==" "):
                self.config={}
            self.config=cPickle.loads(b64decode(data[0][3]))
            print 'got config',self.config
        except IndexError:
            self.config={}
            print ("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
        
        ## wtf??
        return
        p = self.trans.foregroundPresence(bjid)
        if p:
            self.trans.sendPresence(self.trans.jid,bjid,status=p["status"],show=p["show"])
            #FIXME "too fast"!!
            self.pool.callInThread(self.updateStatus,bjid=bjid,text=p["status"])
        else:
            self.trans.sendPresence(self.trans.jid,bjid)

    def loginFailed(self,data,jid):
        print ("login failed for %s"%self.bjid)
        #del self.thread
    def logout(self):
        try:
            defer.execute(self.thread.logout).addCallback(self.delThread,bjid=bjid)
        except KeyError:
            pass
        try:
            self.pool.stop()
            del self.pool
        except KeyError:
            pass
        try:
            del self.config
        except KeyError:
            pass
    def delThread(self):
        del self.thread
        self.active=0
    def hasResource(self,jid):
        """
        return 1 if
            bare jid set and has any resources available
            full jid set and is available
        otherwise returns 0 
        """
        bjid=pyvkt.bareJid(jid)
        #barejid - just check if any resources available
        if jid==bjid and self.resources.has_key(bjid) and len(self.resources[bjid]):
            return 1
        #full jid - check for certain resource
        if jid!=bjid and self.resources.has_key(bjid) and self.resources[bjid].has_key(jid):
            return 1
        #nothing
        return 0

        
        
        
        
        
        
        
        
        
        
        
