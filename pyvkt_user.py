# -*- coding: utf-8 -*-
"""
/***************************************************************************
 *   Copyright (C) 2009 by pyvk-t dev team                                 *
 *   pyvk-t.googlecode.com                                                 *
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 *   This program is distributed in the hope that it will be useful,       *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU General Public License for more details.                          *
 *                                                                         *
 *   You should have received a copy of the GNU General Public License     *
 *   along with this program; if not, write to the                         *
 *   Free Software Foundation, Inc.,                                       *
 *   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             *
 ***************************************************************************/
 """
import libvkontakte
#from twisted.python.threadpool import ThreadPool
from pyvkt_spikes import reqQueue
from twisted.enterprise.adbapi import safe 
import pyvkt_global as pyvkt
from twisted.internet import defer,reactor
import sys,os,cPickle
from base64 import b64encode,b64decode
import time
from traceback import print_stack, print_exc

class user:
    #lock=1
    #active=0
    def __init__(self,trans,jid):
        bjid=pyvkt.bareJid(jid)
        #print "user constructor: %s"%bjid
        
        self.trans=trans
        self.bjid=bjid      #bare jid of a contact
        self.resources={}   #available resources with their status
        self._lock=0
        self.status_lock = 0
        self._active=1
        self.state=0
        # login - 1
        # active - 2
        # logout - 3
        # new - 0
        # inactive - 4

        self.FUsent=0
        self.VkStatus=u""   #status which is set on web
        self.status=u"Подождите..."     #status which is show in jabber
        self.feed = None    #feed

        self.refreshDone=True
        self.rosterStatusTimer=0
        #deprecated?
        self.iterationsNumber=0
        self.tonline={}
        self.onlineList={}
        
        #roster. {jid:{subscripbed:1/0, subscribe: 1/0, status: sometext, name: sometext}}
        #subscribed means transported contact recieves status
        #subscribe meanes transported contact send status
        self.roster={}
        self.pool=reqQueue(user=self,name="pool(%s)"%self.bjid)
        self.pool.start()
        

    def addResource(self,jid,prs=None):
        """
        adds resource to jid's reources list
        stores it's presence and does some work of resending presences
        """
        #if had no resources before and not trying to login now
        if (not self.resources) and self.state==0:
            #self.state=1
            #self.lock=1
            self.state=1
            self.trans.sendPresence(self.trans.jid,self.bjid,t="probe")
            #self.pool.call(self.login)
            self.login()
        #new status of a resource
        if jid in self.resources:
            pass
        elif self.resources and self.state==2:
            self.trans.sendPresence(self.trans.jid,jid,status=self.status)
            self.contactsOnline(self.onlineList)
        #if VkStatus has to be changed and should be done now
        if (prs!=None):
            status=self.prsToVkStatus(self.storePresence(prs))
            #if not locked we update status now
            if status!=self.VkStatus and self.state==2:
                self.trans.updateStatus(self.bjid,status)
            #save status. If locked we'll update it automatically when possible
            self.VkStatus = status
        else:
            self.resources[jid]=None

    def getStatus(self,bjid):
        """ returns status of roster item if set """
        if bjid in self.roster and "status" in self.roster[bjid]:
            return self.roster[bjid]["status"]
        return ""

    def setStatus(self,bjid,name):
        """ sets status of roster item """
        if bjid in self.roster:
            self.roster[bjid]["status"]=name
        else:
            self.roster[bjid]={"subscribe":0,"subscribed":0,"name":name,'status':''}

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
            self.roster[bjid]={"subscribe":0,"subscribed":0,"name":name,'status':''}

    def askSubscibtion(self, bjid,nick=None):
        """just ask for subscribtion if needed"""
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        if not nick:
            nick = self.getName(bjid)
        else:
            self.roster[bjid]["name"]=nick
        if 1 or not self.subscribed(bjid):
            self.trans.sendPresence(bjid,self.bjid,"subscribe",nick=nick)

    def subscribe(self,bjid):
        """ answer on subscription request """
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        self.trans.sendPresence(bjid, self.bjid, "subscribed",nick=self.getName(bjid))
        if not self.roster[bjid]["subscribe"] and pyvkt.jidToId(bjid) in self.onlineList:
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
        #print "delres", self.resources
        if jid in self.resources:
            del self.resources[jid]
        p = self.getHighestPresence()
        if p:
            status=self.prsToVkStatus(p)
            if status!=self.VkStatus and self.state==2:
                self.trans.updateStatus(self.bjid,status)
                self.VkStatus = status
        #print "delres", self.resources

    def createThread(self,jid,email,pw):
        #print "createThread %s"%self.bjid
        jid=pyvkt.bareJid(jid)
        # TODO self.jid
        try:
            del self.vclient
        except:
            pass

        self.trans.sendPresence(self.trans.jid,jid,status=self.status,show="away")
        try:
            #self.vclient=libvkontakte.vkonThread(cli=self.trans,jid=jid,email=email,passw=pw,user=self)
            self.vclient=libvkontakte.client(jid=jid,email=email,passw=pw,user=self)
        except libvkontakte.captchaError:
            print "ERR: got captcha request"
            self.trans.sendPresence(self.trans.jid,jid,status="ERROR: captcha request.",show="unavailable")
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,body="ERROR: captcha request.\nPlease, contact transport administrator")
            self.state=4
            return
        except libvkontakte.authError:
            print "ERR: wrong login/pass"
            self.trans.sendPresence(self.trans.jid,jid,status="ERROR: login/password mismatch.",show="unavailable")
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,body="ERROR: auth error.\nCheck your auth data")
            self.state=4
            return
        #self.lock=0
        #self.active=1
        self.state=2
        #self.vclient.start()
        self.vclient.feedOnly=0
        self.trans.updateStatus(self.bjid,self.VkStatus)
        
    def login(self):
        # TODO bare jid?
        #self.active=1
        #self.lock=1
        self.state=1
        #print "self.bjid:%s"%self.bjid
        if (self.trans.isActive==0 and self.bjid!=self.trans.admin):
            #print ("isActive==0, login attempt aborted")
            #self.lock=0
            #self.active=0
            self.state=4
            #WARN bjid?
            return
        try:
            mq="SELECT * FROM users WHERE jid='%s'"%safe(self.bjid)
        except UnicodeEncodeError:
            try:
                print "unicode error, possible bad JID: %s"%self.bjid
            except:
                print "unicode error. can't print jid"
            #self.lock=0
            #self.active=0
            self.state=4
            return
        #print mq
        #print_stack()
        q=self.trans.dbpool.runQuery(mq)
        q.addCallback(self.login1)
        q.addErrback(self.loginFailed)

    def login1(self,data):
        try:
            t=data[0]
        except IndexError:
            #print "FIXME unregistered user: %s ?"%self.bjid
            if not self.bjid in self.trans.unregisteredList:
                reactor.callFromThread(self.trans.sendMessage,src=self.trans.jid,dest=self.bjid,body=u'Вы не зарегстрированы на транспорте')
                self.trans.unregisteredList.append(self.bjid)
                print "unregistered warning sent"
            #self.lock=0
            #self.active=0
            self.state=4
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
        except TypeError:
            print "Error decoding config"
        except IndexError:
            print ("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
        #getting roster
        self.roster={}
        try:
            if data[0][4]:
                self.roster=cPickle.loads(b64decode(data[0][4]))
        except EOFError:
            print "error while parsing roster"
        except TypeError:
            print "Error decoding roster"
        except IndexError:
            print ("roster field not found! please add it to your database (see pyvk-t_new.sql for details)")

        defer.execute(self.createThread,jid=bjid,email=data[0][1],pw=data[0][2])
        return

    def loginFailed(self,data):
        print ("login failed for %s"%self.bjid)
        print "possible database error"
        self.delThread()
        #del self.vclient

    def logout(self):
        #print "logout %s"%self.bjid
        #self.lock=1
        #self.active=0
        if (self.state==3):
            print "logout(): state=3, logout canceled"
            return
        self.state=3
        #saving data
        try:
            mq="UPDATE users SET roster='%s', config='%s' WHERE jid='%s';"%(b64encode(cPickle.dumps(self.roster)),b64encode(cPickle.dumps(self.config)),safe(self.bjid))
        except UnicodeEncodeError:
            try:
                print "unicode error, possible bad JID: %s"%self.bjid
            except:
                pass
        except AttributeError:
            print_exc()
        else:
            q=self.trans.dbpool.runQuery(mq)
            defer.waitForDeferred(q)
        #now it's blocking ;)
        self.trans.sendPresence(src=self.trans.jid,dest=self.bjid,t="unavailable")
        self.contactsOffline(self.onlineList)
        try:
            self.vclient.logout()
        except:
            print_exc()
        try:
            self.pool.stop()
        except:
            print_exc()
        try:
            self.delThread()
        except:
            print_exc()
        self.trans.hasUser(self.bjid)
        return 0
    def delThread(self,void=0):
        #print "delThread %s"%self.bjid
        #self.active=0
        #self.lock=0
        self.state=4
        try:
            #self.vclient.stop()
            del self.vclient
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
    def refreshData(self):
        """
        refresh online list and statuses
        """
        #self.loopDone=0
        #print self.roster
        #print "r"
        if (1 and self.rosterStatusTimer):
            self.rosterStatusTimer=self.rosterStatusTimer-1
        else:
            slist=self.vclient.getStatusList()
            self.rosterStatusTimer=5
            # it's about 5 munutes
            for i in slist:
                self.setStatus("%s@%s"%(i,self.trans.jid),slist[i])
                #self.roster["%s@%s"%(i,self.trans.jid)]["status"]=slist[i]
        #self.vclient.loopIntern()
        self.vclient
        tfeed=self.vclient.getFeed()
        #tfeed is epty only on some error. Just ignore it
        if tfeed:
            self.trans.updateFeed(self.bjid,tfeed)
        self.onlineList=self.vclient.getOnlineList()
        if (self.tonline.keys()!=self.onlineList.keys()):
            self.contactsOffline(filter(lambda x:self.onlineList.keys().count(x)-1,self.tonline.keys()))
            self.contactsOnline(filter(lambda x:self.tonline.keys().count(x)-1,self.onlineList.keys()))
            self.tonline=self.onlineList
        #FIXME online status
        self.iterationsNumber = self.iterationsNumber + 15 #we sleep 15 in  pollManager
        if self.iterationsNumber>13*60 and self.getConfig("keep_online"):
            self.vclient.getHttpPage("http://pda.vkontakte.ru/id1")
            self.iterationsNumber = 0
        #self.loopDone=True        
        self.refreshDone=True
    def contactsOnline(self,contacts):
        """ send 'online' presence"""
        for i in contacts:
            try:
                nick=u'%s %s'%(self.onlineList[i]["first"],self.onlineList[i]["last"])
            except:
                print_exc()
                nick=None
            status = self.getStatus("%s@%s"%(i,self.trans.jid))
            self.setName("%s@%s"%(i,self.trans.jid),nick)
            if self.getConfig("show_onlines") and (not self.trans.roster_management or self.subscribed("%s@%s"%(i,self.trans.jid))):
                self.trans.sendPresence("%s@%s"%(i,self.trans.jid),self.bjid,nick=nick,status=status)       
    def contactsOffline(self,contacts,force=0):
        """ 
        send 'offline' presence
        set 'force' paramenter to send presence even if disabled in user config
        """
        for i in contacts:
            if (force or self.getConfig("show_onlines")) and (not self.trans.roster_management or self.subscribed("%s@%s"%(i,self.trans.jid))):
                self.trans.sendPresence("%s@%s"%(i,self.trans.jid),self.bjid,t="unavailable")        
    def __del__(self):
        self.delThread()


    def getConfig(self,fieldName):
        if (not fieldName in pyvkt.userConfigFields):
            raise KeyError("user config: no such field (%s)"%fieldName)
        try:
            return self.config[fieldName]
        except KeyError:
            return pyvkt.userConfigFields[fieldName]["default"]
        except AttributeError:
            print "user without config\nstate=%s"%(self.state)
            return pyvkt.userConfigFields[fieldName]["default"]
    def __getattr__(self,name):
        #print "getattr",name
        #print "state = ",self.state
        if (name=="lock"):
            print "deprecated user.lock!"
            print_stack(limit=2)
            if (self.state in (1,3)):
                return 1
            return 0
            #return self._lock
        if (name=="active"):
            print "deprecated user.active!"
            print_stack(limit=2)
            if (self.state in (1,2)):
                return 1
            return 0

            #return self._active
        if (name=='thread'):
            print "deprecated user.thread!"
            print_stack(limit=2)
            return self.vclient
        if (name=='vclient'):
            raise pyvkt.noVclientError(self.bjid)
        raise AttributeError("user instance without '%s'"%name)
        #raise AttributeError("user %s don't  have '%s'"%(self.bjid.encode("utf-8"),name))
    def __setattr__(self,name,val):
        if (name=="lock"):
            print "deprecated user.lock!"
            print_stack(limit=2)
            if (val):
                if self._active: self.state==1
                else: self.state==3
            else:
                if self._active: self.state==2
                else: self.state==0
            #self._lock=val
        if (name=="active"):
            print "deprecated user.active!"
            print_stack(limit=2)
            if (val):
                if self._lock: self.state==1
                else: self.state==2
            else:
                if self._lock: self.state==3
                else: self.state==0
            #self._active=val
        self.__dict__[name]=val

#TODO destructor

