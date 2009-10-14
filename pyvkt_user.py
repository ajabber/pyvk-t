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
from traceback import print_stack, print_exc,format_exc
import xml.dom.minidom
import lxml.etree as xml
import time,logging
class UnregisteredError (Exception):
    pass
class user:
    #lock=1
    #active=0
    def __init__(self,trans,jid,noLoop=False,captcha_key=None):
        bjid=pyvkt.bareJid(jid)
        self.captcha_key=captcha_key
        #print "user constructor: %s"%bjid
        self.loginTime=int(time.time())
        self.trans=trans
        self.captcha_sid=None
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
        
        #roster. {jid:{subscripbed:1/0, subscribe: 1/0, status: sometext, name: sometext,avatar_url: http://urlofavatar,avatar_hash}}
        #subscribed means transported contact recieves status
        #subscribe meanes transported contact send status
        self.roster={}
        if (not noLoop):
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
        """just ask for subscribtion if needed and returns if requested"""
        if not bjid in self.roster:
            self.roster[bjid]={"subscribe":0,"subscribed":0}
        if not nick:
            nick = self.getName(bjid)
        else:
            self.roster[bjid]["name"]=nick
        if 1 or not self.subscribed(bjid):
            self.trans.sendPresence(bjid,self.bjid,"subscribe",nick=nick)
            #print 'askSubscribtion: to=%s, from=%s'%(bjid,self.bjid)
            return 1
        return 0

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
        jid=prs.get("from")
        p={"jid":jid,"priority":'0',"status":u"","show":u"","time":time.time()}
        for i in prs:
            if len(i) and i.tag in p:
                p[i.name]=i.text
        logging.info("presence params: %s"%str(p))
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
            if (self.captcha_key and self.captcha_sid):
                #print "captcha fighting!"
                self.vclient=libvkontakte.client(jid=jid,email=email,passw=pw,user=self,
                    captcha_key=self.captcha_key,captcha_sid=self.captcha_sid)
                self.captcha_sid=None
            else:
                self.vclient=libvkontakte.client(jid=jid,email=email,passw=pw,user=self)
        except libvkontakte.captchaError,exc:
            #print "ERR: got captcha request"
            logging.warning(str(exc))
            
            if (exc.sid):
                self.captcha_sid=exc.sid
                self.saveData()
            self.trans.sendPresence(self.trans.jid,jid,status="ERROR: captcha request.",show="unavailable")
            url='http://vkontakte.ru/captcha.php?s=1&sid=%s'%exc.sid
            #print url
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,
                body=u"Ошибка подключения, стребуется ввести код подтверждения.\nДля подключения отправьте транспорту сообщение вида '/login captcha' (без кавычек), вместо слова captcha введите код с картинки по ссылке %s"%url)
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
        self.pool.call(self.refreshData)

        
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
            self.readData()
        except UnregisteredError:
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,body=u'Вы не зарегистрированы на транспорте.')
        defer.execute(self.createThread,jid=self.bjid,email=self.email,pw=self.password)
    def loginCallback(self,stage):
        self.trans.sendPresence(self.trans.jid,self.bjid,status=u'Подключаюсь [%s]... '%stage,show="away")
    def login1(self,data=None):
        #if (data):
            #try:
                #t=data[0]
            #except IndexError:
                ##print "FIXME unregistered user: %s ?"%self.bjid
                #if not self.bjid in self.trans.unregisteredList:
                    #reactor.callFromThread(self.trans.sendMessage,src=self.trans.jid,dest=self.bjid,body=u'Вы не зарегстрированы на транспорте')
                    #self.trans.unregisteredList.append(self.bjid)
                    ##logging.info("unregistered warning sent")
                ##self.lock=0
                ##self.active=0
                #self.state=4
                #return
            #self.parseDbData(data)
        
        return

    def loginFailed(self,data):
        #print data
        logging.warning ("login failed for %s"%self.bjid)
        #print "possible database error"
        self.delThread()

    def logout(self):
        #print "logout %s"%self.bjid
        #self.lock=1
        #self.active=0
        if (self.state==3):
            print "logout(): state=3, logout canceled"
            return
        self.state=3
        #saving data
        #self.config["last_activity"]=int(time.time())
        try:
            self.saveData()
        except:
            print "GREPME savedata failed"
            print_exc()

        self.trans.sendPresence(src=self.trans.jid,dest=self.bjid,t="unavailable")
        self.contactsOffline(self.onlineList)
        try:
            self.vclient.logout()
        except:
            print_exc()
        try:
            self.pool.stop()
            #self.pool.join()
        except:
            print_exc()
        try:
            self.delThread()
        except:
            print_exc()
        #TODO separate thread
        self.trans.hasUser(self.bjid)
        return 0
    def delThread(self,void=0):
        #print "delThread %s"%self.bjid
        #self.active=0
        #self.lock=0
        self.state=4
        try:
            self.trans.httpIn += self.vclient.bytesIn
        except:
            pass
            #print_exc()
        try:
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
            bjid="%s@%s"%(i,self.trans.jid)
            status = self.getStatus(bjid)
            self.setName(bjid,nick)
            if "avatar_url" in self.onlineList[i]:#we know about avatar
                if not ("avatar_url" in self.roster[bjid] and self.onlineList[i]["avatar_url"]==self.roster[bjid]["avatar_url"]):
                    self.roster[bjid]["avatar_url"]=self.onlineList[i]["avatar_url"]
                    if self.roster[bjid]["avatar_url"]:
                        self.roster[bjid]["avatar_hash"]="nohash"
                    else:#no avatar -> no hash needed
                        self.roster[bjid]["avatar_hash"]=u""
            if not "avatar_url" in self.onlineList[i] or not "avatar_hash" in self.roster[bjid]:
                self.roster[bjid]["avatar_hash"]="nohash"
            #if no hash yet update it
            if self.getConfig("vcard_avatar") and self.trans.show_avatars and self.roster[bjid]["avatar_hash"]=="nohash":
                #print "contactsOnline: getAvatar"
                d=self.pool.defer(f=self.vclient.getAvatar,photourl=self.roster[bjid]["avatar_url"],v_id=i,gen_hash=1)
                d.addCallback(self.avatarHashCalculated,v_id=i)

            if self.getConfig("show_onlines") and (not self.trans.roster_management or self.subscribed(bjid)):
                if self.getConfig("vcard_avatar") and self.trans.show_avatars and ("avatar_hash" in self.roster[bjid]):
                    self.trans.sendPresence(bjid,self.bjid,nick=nick,status=status,avatar=self.roster[bjid]["avatar_hash"])       
                else:
                    self.trans.sendPresence(bjid,self.bjid,nick=nick,status=status)       

    def avatarHashCalculated(self,data,v_id):
        """saves hash of avatar previously calculated in getAvatar funcrion"""
        if not data: return
        bjid="%s@%s"%(v_id,self.trans.jid)
        self.roster[bjid]["avatar_hash"]=data[1]
        if self.getConfig("show_onlines") and (not self.trans.roster_management or self.subscribed(bjid)):
            if v_id in self.onlineList:
                status = self.getStatus(bjid)
                nick = self.getName(bjid)
                self.trans.sendPresence(bjid,self.bjid,nick=nick,status=status,avatar=data[1])       

    def contactsOffline(self,contacts,force=0):
        """ 
        send 'offline' presence
        set 'force' paramenter to send presence even if disabled in user config
        """
        for i in contacts:
            if (force or self.getConfig("show_onlines")) and (not self.trans.roster_management or self.subscribed("%s@%s"%(i,self.trans.jid))):
                self.trans.sendPresence("%s@%s"%(i,self.trans.jid),self.bjid,t="unavailable")        
    def saveData(self):
        dirname=self.trans.datadir+"/"+self.bjid[:1]
        fname=dirname+"/"+self.bjid
        #print dirname
        if (not os.path.exists(dirname)):
            print "creating dir %s"%dirname
            os.mkdir(dirname)
        root=xml.Element("userdata",{'version':'0.1'})
        # versions:
        # 0.1 - initial
        if (type(self.email)==str):
            self.email=self.email.decode('utf-8')
        if (type(self.password)==str):
            try:
                self.password=self.password.decode('utf-8')
            except UnicodeDecodeError:
                print "Password is not in Utf8. Trying cp1251"
                self.password=self.password.decode('cp1251')

        xml.SubElement(root,"email").text=self.email
        xml.SubElement(root,"password").text=self.password
        #print self.config
        if (self.captcha_sid):
            xml.SubElement(root,"captcha_sid").text=self.captcha_sid
        conf=xml.SubElement(root,"config")
        for i in self.config:
            try:
                xml.SubElement(conf,'option',{'name':i,'value':unicode(self.config[i])})
            except:
                print_exc()
        rost=xml.SubElement(root,"roster")
        for i in self.roster:
            item=xml.SubElement(rost,'item',{'jid':i})
            for j in ('status', 'name', 'subscribed', 'subscribe', 'avatar_url', 'avatar_hash'):
                try:
                    try:
                        t=unicode(self.roster[i][j])
                    except:
                        t=self.roster[i][j].decode("utf-8")
                    xml.SubElement(item,j).text=t
                except KeyError:
                    pass
                except:
                    print_exc()
        dat=xml.tostring(root,pretty_print=True)
        if (len(dat)==0):
            print "ERROR: empty file creation prevented!"
            return
        cfile=open(fname,'w')
        cfile.write(dat)
        cfile.close()
        #print "user %s data successfully saved"%self.bjid
    def readData(self):
        dirname=self.trans.datadir+"/"+self.bjid[:1]
        fname=dirname+"/"+self.bjid
        try:
            cfile=open(fname,'r')
        except IOError, err:
            if (err.errno==2):
                logging.warning('readData for unregistered: %s'%self.bjid)
                raise UnregisteredError
        tree=xml.parse(cfile)
        self.email= tree.xpath('//email/text()')[0]
        self.password=tree.xpath('//password/text()')[0]        
        self.config={}
        try:
            self.captcha_sid=tree.xpath('//captcha_sid/text()')[0]
        except IndexError:
            pass
        for i in  tree.xpath('//config/*'):
            n,v=i.get('name'),i.get('value')
            try:
                if (pyvkt.userConfigFields[n]['type']=='boolean'):
                    if (v=='True'):
                        v=True
                    else:
                        v=False
                self.config[n]=v
            
            except:
                print_exc()
            
        #print config
        self.roster={}
        for i in  tree.xpath('//roster/*'):
            t={}
            for j in i:
                if (j.tag in ('subscribed','subscribe')):
                    t[j.tag]=int(j.text)
                else:
                    t[j.tag]=j.text
            self.roster[i.get('jid')]=t
        #print "data file successfully parsed"
        cfile.close()

    def getConfig(self,fieldName):
        if (not fieldName in pyvkt.userConfigFields):
            raise KeyError("user config: no such field (%s)"%fieldName)
        try:
            return self.config[fieldName]
        except KeyError:
            return pyvkt.userConfigFields[fieldName]["default"]
        except AttributeError:
            logging.warn("user without config\nstate=%s"%(self.state))
            return pyvkt.userConfigFields[fieldName]["default"]
    #def __getattr__(self,name):
        ##print "getattr",name
        ##print "state = ",self.state
        #if (name=="lock"):
            #print "deprecated user.lock!"
            #print_stack(limit=2)
            #if (self.state in (1,3)):
                #return 1
            #return 0
            ##return self._lock
        #if (name=="active"):
            #print "deprecated user.active!"
            #print_stack(limit=2)
            #if (self.state in (1,2)):
                #return 1
            #return 0

            ##return self._active
        #if (name=='thread'):
            #print "deprecated user.thread!"
            #print_stack(limit=2)
            #return self.vclient
        #if (name=='vclient'):
            #raise pyvkt.noVclientError(self.bjid)
        #raise AttributeError("user instance without '%s'"%name)
        #raise AttributeError("user %s don't  have '%s'"%(self.bjid.encode("utf-8"),name))
    #def __setattr__(self,name,val):
        #if (name=="lock"):
            #print "deprecated user.lock!"
            #print_stack(limit=2)
            #if (val):
                #if self._active: self.state==1
                #else: self.state==3
            #else:
                #if self._active: self.state==2
                #else: self.state==0
            ##self._lock=val
        #if (name=="active"):
            #print "deprecated user.active!"
            #print_stack(limit=2)
            #if (val):
                #if self._lock: self.state==1
                #else: self.state==2
            #else:
                #if self._lock: self.state==3
                #else: self.state==0
            ##self._active=val
        #self.__dict__[name]=val


#TODO destructor

