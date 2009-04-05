# -*- coding: utf-8 -*-
import libvkontakte
#from twisted.python.threadpool import ThreadPool
from pyvkt_spikes import reqQueue
from twisted.enterprise.adbapi import safe 
import pyvkt_global as pyvkt
from twisted.internet import defer,reactor
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
        self.feed = None    #feed

        #roster. {jid:{subscripbed:1/0, subscribe: 1/0...}}
        #subscribed means transported contact recieves status
        #subscribe meanes transported contact send status
        self.roster={}      

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
            self.trans.sendPresence(self.trans.jid,jid,status=self.status)
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

    def getName(self,bjid):
        """ returns name of roster item if set """
        if bjid in self.roster and "name" in self.roster[bjid]:
            return self.roster[bjid]["name"]
        return u""

    def setName(self,bjid,name):
        """ sets name of roster item """
        if bjid in self.roster:
            self.roster[bjid]["name"]=name
        else:
            self.roster[bjid]={"subscribe":0,"subscribed":0,"name":name}

    def askSubscibtion(self, bjid,nick=None):
        """just ask for subscribtion if needed"""
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        if not nick:
            nick = self.getName(bjid)
        else:
            self.roster[bjid]["name"]=nick
        if not self.subscribed(bjid):
            self.trans.sendPresence(bjid,self.bjid,"subscribe",nick=nick)

    def subscribe(self,bjid):
        """ answer on subscription request """
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        self.trans.sendPresence(bjid, self.bjid, "subscribed",nick=self.getName(bjid))
        if not self.roster[bjid]["subscribe"] and pyvkt.jidToId(bjid) in self.thread.onlineList:
            self.trans.sendPresence(bjid,self.bjid,nick=self.getName(bjid))
        self.roster[bjid]["subscribe"] = 1
        self.askSubscibtion(bjid)

    def onSubscribed(self,bjid):
        """ when subscribtion recieved """
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        self.roster[bjid]["subscribed"] = 1

    def subscribed(self,bjid):
        """ check for "subscribed" field """
        try:
            if self.roster[bjid]["subscribed"]:
                return 1
        except KeyError:
            pass
        return 0

    def unsubscribe(self,bjid):
        """ delete subscribtion """
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        self.roster[bjid]["subscribe"] = 0
        self.trans.sendPresence(bjid,self.bjid,"unsubscribed")
        self.askUnsubscibtion(bjid)

    def askUnsubscibtion(self, bjid):
        """just ask for unsubscribtion if needed"""
        if self.subscribed(bjid):
            self.trans.sendPresence(bjid,self.bjid,"unsubscribe")

    def onUnsubscribed(self,bjid):
        """ when unsubscribtion recieved """
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        self.roster[bjid]["subscribed"] = 0

    def prsToVkStatus(self,prs):
        """
        converts stores presence int  a string which can be send to a site
        """
        st=u""
        if prs["show"]=="away":
            st = u"отошел"
        elif prs["show"]=="xa":
            st = u"давно отошел"
        elif prs["show"]=="dnd":
            st = u"занят"
        elif prs["show"]=="chat":
            st = u"хочет поговорить"
        if st and prs["status"]:
            st = st + " (" + prs["status"] + ")"
        elif prs["status"]:
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

        for j in self.resources:
            if self.resources[j] and self.resources[j]['priority'] > p['priority']:
                p=self.resources[j]
        return p

    def getHighestPresence(self):
        """ returns prs with maximal priority or latest if several"""
        p=None
        for j in self.resources:
            q=self.resources[j]
            if q and (not p or p["priority"]<q["priority"] or (p["priority"]==q["priority"] and p["time"]<q["time"])):
                p = q
        return p

    def delResource(self,jid):
        """
        deletes resource and does some other work if needed
        """
        if jid in self.resources:
            del self.resources[jid]
        p = self.getHighestPresence()
        if p:
            status=self.prsToVkStatus(p)
            if status!=self.VkStatus and not self.lock:
                self.trans.updateStatus(self.bjid,status)
                self.VkStatus = status


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

        self.thread=libvkontakte.vkonThread(cli=self.trans,jid=jid,email=email,passw=pw,user=self)
        self.lock=0
        #self.pool=ThreadPool(1,1)
        self.pool=reqQueue()
        self.pool.start()
        self.thread.start()
        self.thread.feedOnly=0
        self.trans.sendPresence(self.trans.jid,jid,status=self.status)
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
        #getting config
        self.config={}
        try:
            if data[0][3]:
                self.config=cPickle.loads(b64decode(data[0][3]))
        except EOFError:
            print "error while parsing config"
        except IndexError:
            print ("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
        #getting roster
        self.roster={}
        try:
            if data[0][4]:
                self.roster=cPickle.loads(b64decode(data[0][4]))
        except EOFError:
            print "error while parsing roster"
        except IndexError:
            print ("roster field not found! please add it to your database (see pyvk-t_new.sql for details)")

        defer.execute(self.createThread,jid=bjid,email=data[0][1],pw=data[0][2])
        return

    def loginFailed(self,data,jid):
        print ("login failed for %s"%self.bjid)
        #del self.thread

    def logout(self):
        print "logout %s"%self.bjid
        self.lock=1
        #saving data
        try:
            mq="UPDATE users SET roster='%s', config='%s' WHERE jid='%s';"%(b64encode(cPickle.dumps(self.roster)),b64encode(cPickle.dumps(self.config)),safe(self.bjid))
        except UnicodeEncodeError:
            print "unicode error, possible bad JID: %s"%self.bjid
            self.lock=0
            self.active=0
            return
        q=self.trans.dbpool.runQuery(mq)
        defer.waitForDeferred(q)
        #now it's blocking ;)
        try:
            self.thread.logout()
            self.delThread()
        except AttributeError:
            print "thread doesn't exists (%s)"%self.bjid
        #try:
            #self.pool.stop()
        #except AttributeError:
            #print "%s: user without pool??"%self.bjid
        # now pool is necessary
        self.isActive=0
        self.lock=0
        self.trans.hasUser(self.bjid)
        return 0

        try:
            defer.execute(self.thread.logout).addCallback(self.delThread)
        except AttributeError:
            print "thread doesn't exists (%s)"%self.bjid
        try:
            self.pool.stop()
        except AttributeError:
            print "%s: user without pool??"%self.bjid
        self.lock=0

    def delThread(self,void=0):
        print "delThread %s"%self.bjid
        self.active=0
        try:
            self.thread.stop()
            del self.thread
        except:
            pass
        try:
            self.pool.stop()
            del self.pool
        except:
            pass

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
        self.delThread()


    def getConfig(self,fieldName):
        if (not fieldName in pyvkt.userConfigFields):
            raise KeyError("user config: no such field (%s)"%fieldName)
        try:
            return self.config[fieldName]
        except KeyError:
            #FIXME!!
            #print "%s: '%s' isn't set. using default"%(self.bjid,fieldName)
            return pyvkt.userConfigFields[fieldName]["default"]
        

    #TODO destructor

