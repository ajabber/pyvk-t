# -*- coding: utf-8 -*-
import libvkontakte
#from twisted.python.threadpool import ThreadPool
from pyvkt_spikes import reqQueue
from twisted.enterprise.adbapi import safe 
import pyvkt_global as pyvkt
from twisted.internet import defer
import sys,os,cPickle
from base64 import b64encode,b64decode
import time
from traceback import print_stack

class user:
    def __init__(self,trans,jid):
        bjid=pyvkt.bareJid(jid)
        #print "user constructor: %s"%bjid
        
        self.trans=trans
        self.bjid=bjid      #bare jid of a contact
        self.resources={}   #available resources with their status
        self.lock=0 
        self.status_lock = 0
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
        firstTime = 0
        #if had no resources before and not trying to login now
        if not (self.resources or self.lock):
            self.lock=1
            firstTime = 1
            self.login()
        #new status of a resource
        if jid in self.resources:
            pass
        #new resource should be added
        #else:
            #print "addResource(%s)"%jid
            #print_stack()
            #try:
                #for i in self.thread.onlineList:
                    #self.trans.sendPresence("%s@%s"%(i,self.trans.jid),jid)
            #except AttributeError:
                #pass
                #self.storePresence(prs)
        elif self.resources and not self.lock:
            self.trans.sendPresence(self.trans.jid,jid)
            self.trans.usersOnline(self.bjid,self.thread.onlineList)
            #TODO resend presence
            pass
        #if VkStatus has to be changed and should be done now
        if (prs!=None):
            status=self.prsToVkStatus(self.storePresence(prs))
            if status!=self.VkStatus and not self.lock:
                self.trans.updateStatus(self.bjid,status)
                self.VkStatus = status
                #TODO send status to a site
                pass
            if firstTime:
                self.VkStatus = status
        else:
            self.resources[jid]=None
    def prsToVkStatus(self,prs):
        """
        converts stores presence int  a string which can be send to a site
        """
        st=u""
        if prs["show"]=="away":
            st = u"отошел ("+prs["status"]+")"
        elif prs["show"]=="xa":
            st = u"давно отошел ("+prs["status"]+")"
        elif prs["show"]=="dnd":
            st = u"занят ("+prs["status"]+")"
        elif prs["show"]=="chat":
            st = u"хочет поговорить ("+prs["status"]+")"
        else:
            st = prs["status"]
        return st

    def storePresence(self, prs):
        """
        stores presence of a resource and returns it
        """
        if (prs==None):return
        jid=prs["from"]
        p={"jid":jid,"priority":'0',"status":u"","show":u"","time":time.time()}
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

    def createThread(self,jid,email,pw):
        print "createThread %s"%self.bjid
        jid=pyvkt.bareJid(jid)
        # TODO self.jid
        try:
            self.pool.stop()
            del self.pool
        except:
            pass
        try:
            del self.thread
        except:
            pass

        self.thread=libvkontakte.vkonThread(cli=self.trans,jid=jid,email=email,passw=pw)
        self.lock=0
        #self.pool=ThreadPool(1,1)
        self.pool=reqQueue()
        self.pool.start()
        self.thread.start()
        self.thread.feedOnly=0
        self.trans.sendPresence(self.trans.jid,jid)
        self.trans.updateStatus(self.bjid,self.VkStatus)

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
        try:
            mq="SELECT * FROM users WHERE jid='%s'"%safe(self.bjid)
        except UnicodeEncodeError:
            print "unicode error, possible bad JID: %s"%self.bjid
            self.lock=0
            self.active=0
            return
        print mq
        #print_stack()
        q=self.trans.dbpool.runQuery(mq)
        q.addCallback(self.login1)

    def login1(self,data):
        try:
            t=data[0]
        except IndexError:
            print "FIXME unregistered user: %s ?"%self.bjid
            self.lock=0
            self.active=0
            return
        bjid=data[0][0].lower()
        if (bjid!=self.bjid):
            return
        defer.execute(self.createThread,jid=bjid,email=data[0][1],pw=data[0][2])
        try:
            self.config=cPickle.loads(b64decode(data[0][3]))
        except EOFError:
            print "error while parsing config"
            self.config={}
        except IndexError:
            self.config={}
            print ("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
        return

    def loginFailed(self,data,jid):
        print ("login failed for %s"%self.bjid)
        #del self.thread

    def logout(self):
        print "logout %s"%self.bjid
        self.lock=1
        try:
            defer.execute(self.thread.logout).addCallback(self.delThread)
        except AttributeError:
            print "thread doesn't exists (%s)"%self.bjid
        try:
            self.pool.stop()
        except AttributeError:
            print "%s: user without pool??"%self.bjid
        self.lock=0

    def delThread(self,void):
        print "delThread %s"%self.bjid
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
        try:
            self.thread.logout()
        except:
            pass
        try:
            self.thread.stop()
        except:
            pass
        try:
            self.pool.stop()
        except:
            pass

    #TODO destructor

