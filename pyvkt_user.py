# -*- coding: utf-8 -*-
import libvkontakte
from twisted.python.threadpool import ThreadPool
from twisted.enterprise.adbapi import safe 
import pyvkt_global as pyvkt
from twisted.internet import defer
import sys,os,cPickle
from base64 import b64encode,b64decode
import time

class user:
    def __init__(self,trans,jid):
        bjid=pyvkt.bareJid(jid)
        #print "user constructor: %s"%bjid
        
        self.trans=trans
        self.bjid=bjid      #bare jid of a contact
        self.resources={}   #available resources with their status
        self.lock=0 
        self.active=1
        self.FUsent=0
        self.VkStatus=u""   #status which is set on web
        self.status=u""     #status which is show in jabber
        pass

    def addResource(self,jid,prs=None):
        """
        adds resource to jid's reources list
        stores it's presence and does some work of resending presences
        """
        #jid=prs["from"]
        firstTime = 0
        #if had no resources before and not trying to login now
        if not (self.resources or self.lock):
            firstTime = 1
            self.login()
        #new status of a resource
        if jid in self.resources:
            pass
        #new resource should be added
        else:
            #TODO resend presence
            pass
        #if VkStatus has to be changed and should be done now
        status=self.prsToVkStatus(prs)
        if status!=self.VkStatus or firstTime and not self.lock:
            #TODO send status to a site
            pass

    def prsToVkStatus(self,prs):
        """
        converts stores presence int  a string which can be sent to a site
        """
        status=""
        try:
            status=prs.status.children[0]
        except (KeyError, IndexError,AttributeError):
            pass
        return status

    def storePresence(self, prs):
        """
        stores presence of a resource and returns it
        """
        jid=prs["from"]
        p={"jid":jid,"priority":'0',"status":u"","time":time.time()}
        for i in prs.elements():
            if i.children and i.name in p:
                p[i.name]=i.children[0]
        p["priority"]=int(p["priority"])
        self.resources[jid]=p
        return p

    def delResource(self,jid):
        """
        deletes resource and does some other work if needed
        """
        if jid in self.resources:
            del self.resources[jid]
        if not self.resources:
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
            try:
                self.config=cPickle.loads(b64decode(data[0][3]))
            except EOFError:
                print "error while parsing config"
                self.config={}
            print 'got config',self.config
        except IndexError:
            self.config={}
            print ("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
        
        return

    def loginFailed(self,data,jid):
        print ("login failed for %s"%self.bjid)
        #del self.thread

    def logout(self):
        print "logout %s"%self.bjid
        defer.execute(self.thread.logout).addCallback(self.delThread)
        self.pool.stop()

    def delThread(self,void):
        del self.thread
        self.active=0

    def hasResource(self,jid):
        """
        return 1 if resource is available
        otherwise returns 0 
        """
        bjid=pyvkt.bareJid(jid)
        #barejid - just check if any resources available
        if jid==bjid and self.resources:
            return 1
        #full jid - check for certain resource
        if jid!=bjid and jid in self.resources:
            return 1
        #nothing
        return 0
    def __del__(self):
        self.thread.logout()
        self.thread.stop()
        self.pool.stop()
    #TODO destructor

