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
import pyvkt.libvkontakte as libvkontakte
from spikes import reqQueue
import general as gen
import sys,os,cPickle
from base64 import b64encode,b64decode
import time
from traceback import print_stack, print_exc,format_exc
import xml.dom.minidom
import lxml.etree as xml
import time,logging
import demjson
class UnregisteredError (Exception):
    pass

class user:
    #lock=1
    #active=0
    feed={}
    cookies=[]
    blocked=False
    refreshCount=0
    def __init__(self,trans,jid,noLoop=False,captcha_key=None):
        bjid=gen.bareJid(jid)
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
        self.uapiStates={}      # userapi states (ts)
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
            self.state=1
            self.trans.sendPresence(self.trans.jid,self.bjid,t="probe")
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
        if not self.roster[bjid]["subscribe"] and gen.jidToId(bjid) in self.onlineList:
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
        jid=gen.bareJid(jid)
        # TODO self.jid
        try:
            del self.vclient
        except:
            pass
        if (self.blocked):
            logging.warning('login attempt from blocked user')
            self.trans.sendPresence(self.trans.jid,jid,status=u"ERROR: login/password mismatch.",show="unavailable")
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,body=u"Вы указали неверный email или пароль. Необходимо зарегистрироваться на транспорте повторно.")            
            return
        self.trans.sendPresence(self.trans.jid,jid,status=self.status,show="away")
        try:
            #self.vclient=libvkontakte.vkonThread(cli=self.trans,jid=jid,email=email,passw=pw,user=self)
            ck=None
            cs=None
            if (self.captcha_key and self.captcha_sid):
                #print "captcha fighting!"
                ck=self.captcha_key
                cs=self.captcha_sid
                self.captcha_sid=None
            self.vclient=libvkontakte.client(jid=jid,email=email,passw=pw,user=self,captcha_key=ck,captcha_sid=cs, login=False)
            self.vclient.readCookies()
            #FIXME legacy cookies
            if (self.cookies):
                self.vclient.cjar.clear()
                for d,n,v in self.cookies:
                    self.vclient.setCookie(name=n, val=v, site=d)
                    if (n=='remixsid'):
                        self.vclient.sid=v
            else:
                logging.warning('legacy cookies')
                for d,n,v in self.vclient.getCookies():
                    if (n=='remixsid'):
                        self.vclient.sid=v
            if (self.vclient.getSelfId()==-1):
                self.vclient.login(email,pw,captcha_key=ck,captcha_sid=cs)
                if (self.vclient.getSelfId()==-1):
                    raise libvkontakte.authError
                else:
                    if (ck and cs):
                        logging.warning ('captcha defeated!')
                #TODO block user
                for d,n,v in self.vclient.getCookies():
                    if (n=='remixsid'):
                        self.vclient.sid=v
                self.vclient.saveCookies()
        except libvkontakte.captchaError,exc:
            #print "ERR: got captcha request"
            logging.warning(str(exc))
            
            if (exc.sid):
                self.captcha_sid=exc.sid
                self.saveData()
            self.trans.sendPresence(self.trans.jid,jid,status="ERROR: captcha request.",show="unavailable")
            url='http://vkontakte.ru/captcha.php?s=1&sid=%s'%exc.sid
            #print ur
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,
                body=u"Ошибка подключения, требуется ввести код подтверждения.\nДля подключения отправьте транспорту сообщение вида '.login captcha' (без кавычек), вместо слова captcha введите код с картинки по ссылке %s"%url)
            self.state=4
            return
        except libvkontakte.authError:
            logging.warning('authError')
            self.trans.sendPresence(self.trans.jid,jid,status="ERROR: login/password mismatch.",show="unavailable")
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,body=u"Неверный email и/или пароль.")
            self.blocked=True
            self.state=4
            return
        self.state=2
        self.trans.updateStatus(self.bjid,self.VkStatus)
        self.refreshData()
        
    def login(self):
        # TODO bare jid?
        self.state=1
        if (self.trans.isActive==0 and self.bjid!=self.trans.admin):
            self.state=4
            return
        try:
            self.readData()
        except gen.InternalError,e:
            logging.error('internal error: %s'%e)
            if e.fatal:
                logging.error('fatal error')
                return
            txt=u"Внутренняя ошибка транспорта (%s):\n%s"%(e.t,e.s)
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,
                body=txt)
            return
        except UnregisteredError:
            logging.warning("login attempt from unregistered user %s"%self.bjid)
            self.trans.sendMessage(src=self.trans.jid,dest=self.bjid,body=u'Вы не зарегистрированы на транспорте.')
            return
        self.pool.call(self.createThread,jid=self.bjid,email=self.email,pw=self.password)
        
    def logout(self):
        #print "logout %s"%self.bjid
        #self.lock=1
        #self.active=0
        
        if (self.state==3):
            print "logout(): state=3, logout canceled"
            return
        logging.warning('logout')
        self.state=3
        #saving data
        #self.config["last_activity"]=int(time.time())
        try:
            self.saveJsonData()
        except Exception,e:
            logging.warning('saveData: %s'%e)

        self.trans.sendPresence(src=self.trans.jid,dest=self.bjid,t="unavailable")
        self.contactsOffline(self.onlineList)
        try:
            self.vclient.logout()
        except Exception,e:
            logging.warning('logout: %s'%e)
        try:
            self.pool.stop()
            #self.pool.join()
        except Exception,e:
            logging.warning('stopping pool: %s'%e)
        try:
            self.delThread()
        except Exception,e:
            logging.warning('delThread: %s'%e)
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
        except Exception,e:
            logging.warning('http traffic count: %s'%e)
            #print_exc()
        try:
            del self.vclient
            #TODO check references
        except Exception,e:
            logging.warning('deleting vclient: %s'%e)
        try:
            self.pool.stop()
            del self.pool
            #TODO check references
        except Exception,e:
            logging.warning('stopping pool: %s'%e)

    def hasResource(self,jid):
        """
        return 1 if resource is available
        otherwise returns 0 
        """
        bjid=gen.bareJid(jid)
        #barejid - just check if any resources available
        if jid==bjid and self.resources:
            return 1
        #full jid - check for certain resource
        if jid in self.resources:
            return 1
        #nothing
        return 0
    def checkWallUpdate(self):
        try:
            ts=self.uapiStates['wall']
        except:
            #print_exc()
            #logging.warning("wall status (%s): no wall ts. requesting..."%self.bjid)
            self.uapiStates['wall']=self.vclient.getWallState()
        else:
            msgs=self.vclient.getWallHistory(ts)
            if (msgs==False):
                #logging.warning("wall status (%s): bad reply. re-requesting ts..."%self.bjid)
                #FIXME is it possible to use old ts?
                self.uapiStates['wall']=self.vclient.getWallState()
                return
            #print msgs
            for t,a,m in msgs:
                
                #src='%s@%s'%(m['from'][0],self.trans.jid)
                if (a=='add'):
                    src='%s@%s'%(m['from'][0],self.trans.jid)
                    text=m['text'][0]
                    #print 'sending wall notify from ',src
                    self.trans.sendMessage(src,self.bjid,body=u"Пользователь оставил сообщение на Вашей стене:\n '%s'"% text)
                if (a=='del'):
                    src=self.trans.jid
                    self.trans.sendMessage(src,self.bjid,body=u"Сообщение с вашей стены было удалено")
                #logging.warning("new ts: %s"%t)
                self.uapiStates['wall']=t
                    
    def refreshData(self):
        """
        refresh online list and statuses
        """
        #self.loopDone=0
        #print self.roster
        #print "r"
        self.refreshCount+=1
        if (1 and self.rosterStatusTimer):
            self.rosterStatusTimer=self.rosterStatusTimer-1
        else:
            slist=self.vclient.getStatusList()
            self.rosterStatusTimer=5
            # it's about 5 munutes
            for i in slist:
                self.setStatus("%s@%s"%(i,self.trans.jid),slist[i])
                #self.roster["%s@%s"%(i,self.trans.jid)]["status"]=slist[i]
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
        if (self.getConfig("wall_notify")):
            try:
                self.checkWallUpdate()
            except:
                logging.exception('')
        self.iterationsNumber = self.iterationsNumber + 15 #we sleep 15 in  pollManager
        if self.iterationsNumber>13*60 and self.getConfig("keep_online"):
            self.vclient.getHttpPage("http://pda.vkontakte.ru/id1")
            self.iterationsNumber = 0
        if ((self.refreshCount%1000)==0):
            self.refreshCount=0
            #self.sendProbe()
        #self.loopDone=True        
        self.refreshDone=True
    def contactsOnline(self,contacts):
        """ send 'online' presence"""
        for i in contacts:
            try:
                nick=u'%s %s'%(self.onlineList[i]["first"],self.onlineList[i]["last"])
            except Exception,e:
                logging.warning('bad nick (%s)'%e)
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
        return self.saveJsonData()
        dirname=self.trans.datadir+"/"+self.bjid[:1]
        #FIXME config
        fname=dirname+"/"+self.bjid
        #print dirname
        if (not os.path.exists(dirname)):
            #print "creating dir %s"%dirname
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
        #if (self.blocked):
            #logging.warning('saving block')
            #xml.subElement(root,'blocked')
        xml.SubElement(root,"email").text=self.email
        xml.SubElement(root,"password").text=self.password
        try:
            cook=self.vclient.getCookies()
            c=xml.SubElement(root,'cookies')
            for d,n,v in cook:
                if (d[0]=='.'):
                    d=d[1:]
                xml.SubElement(c,'cookie', {'domain':d,'name':n, 'value':v})
        except Exception,e:
            logging.error('can\'t save cookie, %s'%e)
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
        states=xml.SubElement(root,"states")
        for i in self.uapiStates.keys():
            xml.SubElement(states,i).set('ts',str(self.uapiStates[i]))
        dat=xml.tostring(root,pretty_print=True)
        if (len(dat.strip())==0):
            logging.error("empty file creation prevented!")
            return
        cfile=open(fname,'w')
        cfile.write(dat)
        cfile.close()
        #print "user %s data successfully saved"%self.bjid
    def saveJsonData(self):

        data={}
        try:
            ad={'email':unicode(self.email), 'password': unicode(self.password), 'captcha_sid':self.captcha_sid}
            data['auth']=ad
        except:
            logging.exception('')
        try:
            cook=self.vclient.getCookies()
        except:
            cook=self.cookies
        cd=[]
        for d,n,v in cook:
            if (d[0]=='.'):
                d=d[1:]
            cd.append({'domain':d,'name':n, 'value':v})
        data['cookies']=cd
            #logging.warning('')
        #conf=[]
        #for i in self.config:
            #conf.append({'name':i,'value':unicode(self.config[i])})
        data['config']=self.config
        rost=[]
        for i in self.roster:
            item={'jid':i}
            #item=xml.SubElement(rost,'item',{'jid':i})
            for j in ('status', 'name', 'subscribed', 'subscribe', 'avatar_url', 'avatar_hash'):
                try:
                    try:
                        t=unicode(self.roster[i][j])
                    except:
                        #FIXME unicode anywhere!
                        t=self.roster[i][j].decode("utf-8")
                    item[j]=t
                    #xml.SubElement(item,j).text=t
                except KeyError:
                    pass
                except:
                    logging.exception('')
            rost.append(item)
        data['roster']=rost
        data['uapi_states']=self.uapiStates
        #print data
        j=demjson.JSON(compactly=False)
        dirname=self.trans.datadir+"/"+self.bjid[:1]
        fname=dirname+"/"+self.bjid+'_json'
        #print j.encode(data)
        cfile=open(fname,'w')
        cfile.write(j.encode(data).encode('utf-8'))
        cfile.close()
        #logging.warning('json data saved')
    def readJsonData(self):
        dirname=self.trans.datadir+"/"+self.bjid[:1]
        fname=dirname+"/"+self.bjid+'_json'
        cfile=open(fname,'r')
        f=cfile.read()
        cfile.close()
        j=demjson.JSON(compactly=False)
        data=j.decode(f.decode('utf-8'))
        try:
            self.cookies=[(i['domain'], i['name'], i['value']) for i in data['cookies'] ]
        except TypeError:
            self.cookies=data['cookies']
        #TODO blocked
        self.email=data['auth']['email']
        self.password=data['auth']['password']
        self.captcha_sid=data['auth']['captcha_sid']
        self.config=data['config']
        self.roster={}
        for i in data['roster']:
            j=i['jid']
            del i['jid']
            self.roster[j]=i
            #print i
        self.uapiStates=data['uapi_states']
    def readData(self):
        try:
            return self.readJsonData()
        except IOError, err:
            pass
            #logging.exception('') 
        dirname=self.trans.datadir+"/"+self.bjid[:1]
        #FIXME config
        fname=dirname+"/"+self.bjid
        
        try:
            cfile=open(fname,'r')
        except IOError, err:
            if (err.errno==2):
                #logging.warning('readData for unregistered: %s'%self.bjid)
                raise UnregisteredError
        try:
            tree=xml.parse(cfile)
        except xml.XMLSyntaxError:
            logging.error ("broken xml file: %s"%fname)
            raise gen.InternalError(t='err:brokendata', s=u'База данных была повреждена. Вам необходимо перерегистрироваться.')
        try:
            cook=tree.xpath('//cookies/*')
            if (len(cook)):
                self.cookies=[(i.get('domain'),i.get('name'),i.get('value')) for i in cook]
            else:
                self.cookies=[]
            #print cook
        except Exception, e:
            logging.warning('can\'t read cookies: %s'%e)
        #print tree.xpath('//blocked')
        if (len(tree.xpath('//blocked'))!=0):
            logging.warning('blocked user')
            #self.blocked=True
        try:
            self.email= tree.xpath('//email/text()')[0]
            self.password=tree.xpath('//password/text()')[0]
        except IndexError:
            logging.error('readData(%s): can\'t find email/password'%self.bjid)
            self.email=''
            self.password=''
            #FIXME error message
        self.config={}
        try:
            self.captcha_sid=tree.xpath('//captcha_sid/text()')[0]
        except IndexError:
            pass
        for i in  tree.xpath('//config/*'):
            n,v=i.get('name'),i.get('value')
            try:
                if (gen.userConfigFields[n]['type']=='boolean'):
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
        self.uapiStates={}
        for i in  tree.xpath('//states/*'):
            self.uapiStates[i.tag]=i.get('ts')
        #print '1111111',self.uapiStates
        #print "data file successfully parsed"
        cfile.close()
    def sendProbe(self):
        for i in self.roster:
            if self.roster[i]['subscribed']:
                self.trans.sendPresence(i,self.bjid,t='probe')
                logging.warning('probe sent from %s'%i)
                return
    def getConfig(self,fieldName):
        if (not fieldName in gen.userConfigFields):
            raise KeyError("user config: no such field (%s)"%fieldName)
        try:
            return self.config[fieldName]
        except KeyError:
            return gen.userConfigFields[fieldName]["default"]
        except AttributeError:
            logging.warn("user without config state=%s"%(self.state))
            return gen.userConfigFields[fieldName]["default"]
    def __getattr__(self,name):
        if (name=='vclient'):
            raise gen.NoVclientError(self.bjid)
        raise AttributeError("user [%s] instance has no attribute '%s'"%(self.bjid,name))
    def sendFriendList(self,fl):

        #bjid=gen.bareJid(jid)
        #n=0
        #if self.hasUser(bjid):
        tj=self.trans.jid
        for f in fl:
            src="%s@%s"%(f,tj)
            try:
                nick=u"%s %s"%(fl[f]["first"],fl[f]["last"])
            except KeyError:
                logging.warning('id%s: something wrong with nick'%f)
                try:
                    nick=fl[f]["first"]
                except:
                    try:
                        nick=fl[f]["last"]
                    except:
                        nick=u'<pyvk-t: internal error>'
            x=self.askSubscibtion(src,nick=nick)
            #if x: 
                #n+=1
            #self.sendPresence(src,jid,"subscribed")
            #self.sendPresence(src,jid,"subscribe")
            #return
        #self.sendMessage(self.jid,jid,u"Отправлены запросы авторизации.")



#TODO destructor

