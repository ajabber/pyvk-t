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
#TODO clean up this import hell!!
import twisted
from twisted.application import internet, service
from twisted.internet import interfaces, defer, reactor,threads
from twisted.python import log
from twisted.words.xish import domish
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.enterprise import adbapi 
from twisted.enterprise.adbapi import safe 
from twisted.words.protocols.jabber.ijabber import IService
from twisted.words.protocols.jabber import component,xmlstream,jid

from base64 import b64encode,b64decode
from zope.interface import Interface, implements
from base64 import b64encode,b64decode
from traceback import print_stack, print_exc
import sys,os,platform,threading,signal,cPickle,sha,time,ConfigParser

from pyvkt_user import user
import pyvkt_global as pyvkt
import pyvkt_user,pyvkt_commands
from libvkontakte import *
from pyvkt_spikes import pollManager

def create_reply(elem):
    """ switch the 'to' and 'from' attributes to reply to this element """
    # NOTE - see domish.Element class to view more methods 
    frm = elem['from']
    elem['from'] = elem['to']
    elem['to']   = frm

    return elem

class LogService(component.Service):
    """
    A service to log incoming and outgoing xml to and from our XMPP component.

    """
    packetsIn = 0
    packetsOut = 0
    bytesIn = 0
    bytesOut = 0
    
    def transportConnected(self, xmlstream):
        xmlstream.rawDataInFn = self.rawDataIn
        xmlstream.rawDataOutFn = self.rawDataOut

    def rawDataIn(self, buf):
        self.packetsIn += 1
        try:
            self.bytesIn += len(buf)
        except:
            pass
        #log.msg("%s - RECV: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        pass

    def rawDataOut(self, buf):
        self.packetsOut += 1
        try:
            self.bytesOut += len(buf)
        except:
            pass

        #log.msg("%s - SEND: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        pass

class pyvk_t(component.Service):

    implements(IService)
    startTime = time.time()
    logger=None

    def __init__(self):
        config = ConfigParser.ConfigParser()
        confName="pyvk-t_new.cfg"
        if(os.environ.has_key("PYVKT_CONFIG")):
            confName=os.environ["PYVKT_CONFIG"]
        config.read(confName)
        self.httpIn = 0
        dbmodule=config.get("database","module") 
        if dbmodule=="MySQLdb":
            self.dbpool = adbapi.ConnectionPool(
                dbmodule,
                host=config.get("database","host"), 
                user=config.get("database","user"), 
                passwd=config.get("database","passwd"), 
                db=config.get("database","db"),
                cp_reconnect=1)
        elif dbmodule=="sqlite3":
            self.dbpool = adbapi.ConnectionPool(
                dbmodule,
                database=config.get("database","db"),
                cp_reconnect=1)
        else:
            self.dbpool = adbapi.ConnectionPool(
                dbmodule,
                host=config.get("database","host"), 
                user=config.get("database","user"), 
                password=config.get("database","passwd"), 
                database=config.get("database","db"),
                cp_reconnect=1)

            
        if config.has_option("features","sync_status"):
            self.sync_status = config.getboolean("features","sync_status")
        else:
            self.sync_status = 0
        if config.has_option("features","avatars"):
            self.show_avatars = config.getboolean("features","avatars")
        else:
            self.show_avatars = 0
        if config.has_option("features","datadir"):
            self.datadir = config.get("features","datadir")
        else:
            print "you have to set features/datadir in your config file and convert yur DB to new format using #convertdb command"
            raise Exception
        if config.has_option("features","roster_management"):
            self.roster_management = config.getboolean("features","roster_management")
        else:
            self.roster_management= 0
        if config.has_option("features","feed_notify"):
            self.feed_notify = config.getboolean("features","feed_notify")
        else:
            self.feed_notify= 0
        try:
            self.cachePath=config.get("features","cache_path")
        except (ConfigParser.NoOptionError,ConfigParser.NoSectionError):
            print "features/cache_path isn't set. disabling cache"
            self.cachePath=None
        try:
            self.cookPath=config.get("features","cookies_path")
        except (ConfigParser.NoOptionError,ConfigParser.NoSectionError):
            print "features/cookies_path isn't set."
        #try:
        #if config.has_option("features","pubsub_avatars"):
            #self.pubsub=pubsub.pubsubMgr(self)
        #else:
        self.pubsub=None
        self.users={}
        try:
            self.admin=config.get("general","admin")
        except:
            log.message("you didn't set admin JID in config!")
            self.admin=None
        #self.config=config
        #try:
        proc=os.popen("svnversion")
        s=proc.read()
        if(s=="exported" or s==""):
            self.revision="alpha"
        else:
            p=s.find(":")
            ver=s[p+1:-1]
            self.revision="svn-rev.%s"%ver
        self.commands=pyvkt_commands.cmdManager(self)
        self.isActive=1
        self.pollMgr=pollManager(self)
        
        self.unregisteredList=[]
        signal.signal(signal.SIGUSR1,self.signalHandler)

    def componentConnected(self, xmlstream):
        """
        This method is called when the componentConnected event gets called.
        That event gets called when we have connected and authenticated with the XMPP server.
        """
        self.jabberId = xmlstream.authenticator.otherHost
        self.jid= xmlstream.authenticator.otherHost
        self.xmlstream = xmlstream # set the xmlstream so we can reuse it
        
        xmlstream.addObserver('/presence', self.onPresence, 1)
        xmlstream.addObserver('/iq', self.onIq, 1)
        #xmlstream.addOnetimeObserver('/iq/vCard', self.onVcard, 2)
        xmlstream.addObserver('/message', self.onMessage, 1)
        if (self.pollMgr.isAlive()):
            print "reconnect happened"
        else:
            self.pollMgr.start()
            
        print "component ready!"

    def onMessage(self, msg):
        """
        Act on the message stanza that has just been received.
        """
        v_id=pyvkt.jidToId(msg["to"])
        if (msg.hasAttribute("type")) and msg["type"]=="error":
            print "XMPP ERROR:"
            print msg.toXml().encode('ascii', 'replace')
            return None
        if (v_id==-1):
            return None
        if (msg.body):
            req=msg.request
            try:
                msgid=msg["id"]
            except KeyError:
                msgid=""
            try:
                body=msg.body.children[0]
            except:
                print "strange message"
                try:
                    print msg
                except:
                    print msg.encode("utf-8")
                return
            
            bjid=pyvkt.bareJid(msg["from"])
            if (body[0:1]=="/") and body[:4]!="/me ":
                if (req and req.uri=='urn:xmpp:receipts'):
                    self.msgDeliveryNotify(0,msg_id=msgid,jid=msg["from"],v_id=0,receipt=1)
                cmd=body[1:].rstrip()
                #if (self.users.has_key(bjid) and self.users[bjid].vclient and cmd=="get roster"):
                if (cmd=="get roster"):
                    if (self.hasUser(bjid)):
                        d=self.users[bjid].pool.defer(self.users[bjid].vclient.getFriendList)
                        d.addCallback(self.sendFriendlist,jid=bjid)
                    else:
                        self.sendMessage(self.jid,msg["from"],u"Сначала необходимо подключиться")
                elif (cmd=="help"):
                    self.sendMessage(self.jid,msg["from"],u"""/get roster для получения списка
/login для подключения
/logout для отключения
/config для изменения настроек
/setstatus для изменения статуса на сайте""")
                else:
                    if (self.hasUser(bjid)):
                        d=self.users[bjid].pool.defer(f=self.commands.onMsg,jid=msg["from"],text=cmd,v_id=v_id)
                    else:
                        d=threads.deferToThread(f=self.commands.onMsg,jid=msg["from"],text=cmd,v_id=v_id)
                    cb=lambda (x):self.sendMessage(msg['to'],msg["from"],x)
                    d.addCallback(cb)
                    d.addErrback(self.errorback)
                return

            if (body[0:1]=="#" and bjid==self.admin and msg["to"]==self.jid):
                if (req and req.uri=='urn:xmpp:receipts'):
                    self.msgDeliveryNotify(0,msg_id=msgid,jid=msg["from"],v_id=0,receipt=1)                
                # admin commands
                cmd=body[1:]
                
                log.msg("admin command: '%s'"%cmd)
                if (cmd[:4]=="stop"):
                    self.isActive=0
                    if (cmd=="stop"):
                        self.stopService(suspend=True)
                    else:
                        self.stopService(suspend=True,msg=cmd[5:])
                    self.sendMessage(self.jid,msg["from"],"'%s' done"%cmd)
                elif (cmd=="start"):
                    self.isActive=1
                elif (cmd=="sendprobes"):
                    threads.deferToThread(self.sendProbes,msg["from"])

                elif (cmd=="users"):
                    count = 0
                    ret = u''
                    for i in self.users.keys():
                        if (self.hasUser(i)):
                            ret=ret+u"\nxmpp:%s"%(i)
                            count+=1
                    ret=u"%s user(s) online"%count + ret
                    self.sendMessage(self.jid,msg["from"],ret)
                elif (cmd=="stats"):
                    #TODO async request
                    self.sendStatsMessage(msg['from'])

                elif (cmd=="resources"):
                    count = 0
                    rcount = 0
                    ret = u''
                    for i in self.users.keys():
                        if (self.hasUser(i)):
                            for j in self.users[i].resources.keys():
                                ret=ret+u"\nxmpp:%s %s(%s)[%s]"%(j,self.users[i].resources[j]["show"],self.users[i].resources[j]["status"],self.users[i].resources[j]["priority"])
                                rcount +=1
                            ret=ret+u"\n"
                            count+=1
                    ret=u"%s(%s) user(s) online"%(count,rcount) + ret
                    self.sendMessage(self.jid,msg["from"],ret)
                elif (cmd[:6]=="roster"):#Получение информации о ростере человека
                    j=cmd[7:]
                    if not j:
                            j=msg['from']
                    j=pyvkt.bareJid(j)
                    ret=u'Ростер %s:\n'%j
                    if self.hasUser(j):
                        ret = ret + u'\tКоличество контактов: %s\n'%len(self.users[j].roster)
                        ret = ret + u'\tРазмер данных в БД: %s'%len(b64encode(cPickle.dumps(self.users[j].roster,2)))
                    else:
                        ret = u'Пользователь %s не в сети, можете посмотреть его ростер в базе'%j
                    self.sendMessage(self.jid,msg["from"],ret)
                elif(cmd=="stats2"):
                    for i in self.users.keys():
                        try:
                            print i
                            #print "a=%s l=%s"%(self.users[i].active,self.users[i].lock)
                        except:
                            pass
                elif (cmd[:4]=="wall"):
                    for i in self.users:
                        self.sendMessage(self.jid,i,"[broadcast message]\n%s"%cmd[5:])
                    self.sendMessage(self.jid,msg["from"],"'%s' done"%cmd)
                elif (cmd=='convertdb'):
                    print "convertdb request\nstopping transport..."
                    self.stopService(suspend=True)
                    qq=self.dbpool.runQuery("SELECT * FROM users;")
                    qq.addCallback(self.convertDb)
                    #print repr(ulist)
                    
                else:
                    self.sendMessage(self.jid,msg["from"],"unknown command: '%s'"%cmd)
                return
            if(msg["to"]!=self.jid and self.hasUser(bjid)):
                dogpos=msg["to"].find("@")
                try:
                    v_id=int(msg["to"][:dogpos])
                except:
                    log.msg("bad JID: %s"%msg["to"])
                    return
                if self.users[bjid].getConfig("jid_in_subject"):
                    title = "xmpp:%s"%bjid
                else:
                    title = '...'
                for x in msg.elements():
                    if x.name=="subject":
                        title=x.__str__()
                        break

                s=self.users[bjid].getConfig("signature")
                if s:
                    body = body + u"\n--------\n" + s
                d=self.users[bjid].pool.defer(f=self.users[bjid].vclient.sendMessage,to_id=v_id,body=body,title=title)
                if (req and req.uri=='urn:xmpp:receipts'):
                    d.addCallback(self.msgDeliveryNotify,msg_id=msgid,jid=msg["from"],v_id=v_id,receipt=1,body=body,subject=title)
                else:
                    d.addCallback(self.msgDeliveryNotify,msg_id=msgid,jid=msg["from"],v_id=v_id,body=body,subject=title)
                d.addErrback(self.errorback)
            if (msg["to"]==self.jid and msg["from"]==self.jid):
                #print 'got echo t=',body
                try:
                    self.pollMgr.watchdog=int(body)
                except:
                    print_exc()
    def convertDb(self,ulist):
        print "got user list"
        print "length: ",len(ulist)
        cnt=0
        woep=0
        ad=0
        for i in ulist:
            bjid=i[0]
            print "jid: ",repr(bjid),
            u=user(self,bjid,noLoop=True)
            try:
                u.readData()
                print "already in new format. skipping"
                ad+=1
            except:
                u.parseDbData([i])
                if (u.email and u.password):
                    print repr(u.password)
                    u.saveData()
                    print "done"
                    cnt +=1
                else:
                    print "user w/o email or pass. skipping"
                    woep+=1
        print "total: ",len(ulist)
        print "converted:",cnt
        print "skipped (already done):",ad
        print "skipped (no email/pass):",woep

    def msgDeliveryNotify(self,res,msg_id,jid,v_id,receipt=0,body=None,subject=None):
        """
        Send delivery notification if message successfully sent
        use receipt flag if needed to send receipt
        """
        msg=domish.Element((None,"message"))
        #if res!=0:
        #    if body:
        #        msg.addElement("body").addContent(body)
        #    if subject:
        #        msg.addElement("subject").addContent(subject)
        msg["to"]=jid
        if (v_id):
            msg["from"]="%s@%s"%(v_id,self.jid)
        else:
            msg["from"]=self.jid
        msg["id"]=msg_id
        if res == 0 and receipt:
            msg.addElement("received",'urn:xmpp:receipts')
        elif res == 0:
            return #no reciepts needed and no errors
        elif res == 2:
            err = msg.addElement("error")
            err.attributes["type"]="wait"
            err.attributes["code"]="500"
            err.addElement("resource-constraint","urn:ietf:params:xml:ns:xmpp-stanzas")
            err.addElement("too-many-stanzas","urn:xmpp:errors")
            err.addElement("text","urn:ietf:params:xml:ns:xmpp-stanzas").addContent(u"Слишком часто посылаете сообщения. Подождите немного.")
        else:
            err = msg.addElement("error")
            err.attributes["type"]="cancel"
            err.attributes["code"]="500"
            err.addElement("undefined-condition","urn:ietf:params:xml:ns:xmpp-stanzas")
            err.addElement("text","urn:ietf:params:xml:ns:xmpp-stanzas").addContent(u"Капча на сайте или ошибка сервера")

        self.xmlstream.send(msg)

    def onIq(self, iq):
        """
        Act on the iq stanza that has just been received.
        """
        #log.msg(iq["type"])
        #log.msg(iq.firstChildElement().toXml().encode("utf-8"))
        bjid=pyvkt.bareJid(iq["from"])
        if (iq["type"]=="get"):
            query=iq.query
            if (query):
                ans=xmlstream.IQ(self.xmlstream,"result")
                ans["to"]=iq["from"]
                ans["from"]=iq["to"]
                ans["id"]=iq["id"]
                q=ans.addElement("query",query.uri)
                if (query.uri=="http://jabber.org/protocol/disco#info"):
                    try:
                        node=query["node"]
                    except KeyError:
                        node=u''
                    if (node=='http://jabber.org/protocol/commands' or node[:4]=="cmd:"):
                        self.xmlstream.send(self.commands.onDiscoInfo(iq))
                        return
                    elif(node==''):
                        if (iq["to"]==self.jid):
                            q.addElement("identity").attributes={"category":"gateway","type":"vkontakte.ru","name":"Vkontakte.ru transport [pyvk-t]"}
                            if (self.isActive):
                                q.addElement("feature")["var"]="jabber:iq:register"
                            q.addElement("feature")["var"]="jabber:iq:gateway"
                            q.addElement("feature")["var"]="jabber:iq:version"
                            if (self.hasUser(bjid)):
                                q.addElement("feature")["var"]="jabber:iq:search"
                            q.addElement("feature")["var"]="jabber:iq:last"
                            q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
                            q.addElement("feature")["var"]='http://jabber.org/protocol/stats'
                            #q.addElement("feature")["var"]="stringprep"
                            #q.addElement("feature")["var"]="urn:xmpp:receipts"
                        else:
                            q.addElement("identity").attributes={"category":"pubsub","type":"pep"}
                            #q.addElement("feature")["var"]="stringprep"
                            q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
                            q.addElement("feature")["var"]="urn:xmpp:receipts"
                            q.addElement("feature")["var"]="jabber:iq:version"
                            #if(self.cachePath):
                                #q.addElement("feature")["var"]="jabber:iq:avatar"
                    else:
                        err=ans.addElement("error")
                        err["type"]="cancel"
                        err.addElement('item-not-found','urn:ietf:params:xml:ns:xmpp-stanzas')
                    ans.send()
                    return
                elif (query.uri=="http://jabber.org/protocol/disco#items"):
                    if (query.hasAttribute("node")):
                        q["node"]=query["node"]
                        if (query["node"]=="http://jabber.org/protocol/commands"):
                            self.xmlstream.send(self.commands.onDiscoItems(iq))
                            return
                        elif(query["node"]=="friendsonline"):
                            if (self.hasUser(bjid)):
                                for i in self.users[bjid].onlineList:
                                    cname=u'%s %s'%(self.users[bjid].onlineList[i]["first"],self.users[bjid].onlineList[i]["last"])
                                    q.addElement("item").attributes={"node":"http://jabber.org/protocol/commands",'name':cname,'jid':"%s@%s"%(i,self.jid)}
                    else:
                        q.addElement("item").attributes={"node":"http://jabber.org/protocol/commands",'name':'Pyvk-t commands','jid':self.jid}
                        if (self.hasUser(bjid)):
                            q.addElement("item").attributes={"node":"friendsonline",'name':'Friends online','jid':self.jid}
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:register"):
                    #TODO asynchronous?
                    self.sendRegistrationForm(ans,q)
                    return
                elif (query.uri=="http://jabber.org/protocol/stats") and (iq["to"]==self.jid): #statistic gathering
                    usersTotal = None
                    if not query.children:
                        q.addElement("stat")["name"] = "time/uptime"
                        q.addElement("stat")["name"] = "users/online"
                        #q.addElement("stat")["name"] = "users/total"
                        if self.logger:
                            q.addElement("stat")["name"] = "bandwidth/packets-in"
                            q.addElement("stat")["name"] = "bandwidth/packets-out"
                    else:
                        for i in query.children:
                            #print type(i)
                            if (type(i)==unicode):
                                continue
                            t=q.addElement("stat")
                            t['name']=i["name"]
                            if i["name"]=='time/uptime':
                                t['units']='seconds'
                                t['value']=str(int(time.time()-self.startTime))
                            elif i["name"]=='users/online':
                                t['units']='users'
                                t['value']=str(len(self.users))
                            #elif i["name"]=='users/total':
                                #t['units']='users'
                                #t['value']=len(self.users)
                                #usersTotal = t
                            elif i["name"]=="bandwidth/packets-in" and self.logger:
                                t['units']='packets'
                                t['value']= str(self.logger.packetsIn)
                            elif i["name"]=="bandwidth/packets-out" and self.logger:
                                t['units']='packets'
                                t['value']=str(self.logger.packetsOut)
                            else:
                                e=t.addElement("error","Service Unavailable")
                                e["code"]="503"
                    #if usersTotal:
                        #qq=self.dbpool.runQuery("SELECT count(jid) FROM users;")
                        #qq.addCallback(self.sendTotalStats,ans,usersTotal)
                    #else:
                    #self.sendTotlalStats()
                    ans.send()
                    #print ans
                    return
                elif query.uri=="jabber:iq:last" and (iq["to"]==self.jid):
                    q["seconds"]=str(int(time.time()-self.startTime))
                    ans.send()
                    return

                elif (query.uri=="jabber:iq:version"):
                    q.addElement("name").addContent("pyvk-t [twisted]")
                    q.addElement("version").addContent(self.revision)
                    q.addElement("os").addContent(platform.system()+" "+platform.release()+" "+platform.machine())
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:gateway"):
                    q.addElement("desc").addContent(u"Пожалуйста, введите id пользователя на сайте вконтакте.ру.\nУзнать, какой ID у пользователя Вконтакте можно, например, так:\nЗайдите на его страницу. В адресной строке будет http://vkontakte.ru/profile.php?id=0000000\nЗначит его ID - 0000000")
                    q.addElement("prompt").addContent("Vkontakte ID")
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:search" and self.hasUser(bjid)):
                    q.addElement("instructions").addContent(u"Use the enclosed form to search. If your Jabber client does not support Data Forms, visit http://shakespeare.lit/")
                    x=q.addElement("x","jabber:x:data")
                    x['type']='form'
                    x.addElement("instructions").addContent(u"Введите произвольный текст по которому будет произведен поиск")
                    hidden=x.addElement("field")
                    hidden['type']='hidden'
                    hidden['var']='FORM_TYPE'
                    hidden.addElement('value').addContent(u'jabber:iq:search')
                    text=x.addElement("field")
                    text['type']='text-single'
                    text['label']=u'Текст'
                    text['var']='text'
                    ans.send()
                    return
            vcard=iq.vCard
            if (vcard):
                dogpos=iq["to"].find("@")
                if(dogpos!=-1):
                    try:
                        v_id=int(iq["to"][:dogpos])
                    except:
                        log.msg("bad JID: %s"%iq["to"])
                        pass
                    else:
                        #log.msg("id: %s"%v_id)
                        if (self.hasUser(bjid)):
                            #self.users[bjid].pool.callInThread(time.sleep(1))
                            self.users[bjid].pool.call(self.getsendVcard,jid=iq["from"],v_id=v_id,iq_id=iq["id"])
                            return
                        else:
                            ans=xmlstream.IQ(self.xmlstream,"result")
                            ans["to"]=iq["from"]
                            ans["from"]=iq["to"]
                            ans["id"]=iq["id"]
                            err = ans.addElement("error")
                            err.attributes["type"]="auth"
                            #err.attributes["code"]="400"
                            err.addElement("not-authorized","urn:ietf:params:xml:ns:xmpp-stanzas")
                            t=err.addElement("text",'urn:ietf:params:xml:ns:xmpp-stanzas')
                            t["xml:lang"]="ru"
                            t.addContent(u"Для запроса vCard необходимо подключиться.\nДля подключения отправьте /login или используйте ad-hoc.")
                            self.xmlstream.send(err)
                            return
                            #err.addElement("too-many-stanzas","urn:xmpp:errors")
                else:
                    ans=xmlstream.IQ(self.xmlstream,"result")
                    ans["to"]=iq["from"]
                    ans["from"]=iq["to"]
                    ans["id"]=iq["id"]
                    q=ans.addElement("vCard","vcard-temp")
                    q.addElement("FN").addContent("vkontakte.ru transport")
                    q.addElement("URL").addContent("http://pyvk-t.googlecode.com")
                    q.addElement("DESC").addContent("Vkontakte.ru jabber transport\nVersion: %s"%self.revision)
                    if self.show_avatars:
                        try:
                            req=open("avatar.png")
                            photo=base64.encodestring(req.read())
                            p=q.addElement(u"PHOTO")
                            p.addElement("TYPE").addContent("image/png")
                            p.addElement("BINVAL").addContent(photo.replace("\n",""))
                        except:
                            print 'cannot load avatar'
                    
                    ans.send()
                    return
                    
        if (iq["type"]=="set"):
            query=iq.query
            if (query):
                if (query.uri=="jabber:iq:register"):
                    bjid=pyvkt.bareJid(iq["from"])
                    if (query.remove):
                        try:
                            os.unlink("%s/%s/%s"%(self.datadir,bjid[:1],bjid))
                        except OSError:
                            pass
                        return
                    print "new user: %s"%pyvkt.bareJid(iq["from"])
                    email=""
                    pw=""
                    for i in filter(lambda x:type(x)==twisted.words.xish.domish.Element,query.children):
                        if (i.name=="email"):
                            try:
                                email=i.children[0]
                            except IndexError:
                                #empty email
                                # TODO error stranza
                                print "fixme: error stranza"
                                return
                        if (i.name=="password"):
                            try:
                                pw=i.children[0]
                            except IndexError:
                                #empty password
                                # TODO error stranza
                                print "fixme: error stranza"
                                return
                    #FIXME asynchronous!!
                    u=user(self,pyvkt.bareJid(iq["from"]))
                    try:
                        u.readData()
                    except:
                        print_exc()
                        print "cant read data. possible new user"
                        u.config={}
                    u.email=email
                    u.password=pw
                    u.saveData()
                    self.register2(bjid,iq['id'])
                    return
                if (query.uri=="jabber:iq:gateway"):
                    for prompt in query.elements():
                        if prompt.name=="prompt":
                            ans=xmlstream.IQ(self.xmlstream,"result")
                            ans["to"]=iq["from"]
                            ans["from"]=iq["to"]
                            ans["id"]=iq["id"]
                            q=ans.addElement("query",query.uri)
                            q.addElement("jid").addContent("%s@%s"%(prompt,iq["to"]))
                            ans.send()
                            return
                elif (query.uri=="jabber:iq:search") and (self.hasUser(bjid)):
                        time.sleep(1)
                        self.users[bjid].pool.call(self.getSearchResult,jid=iq["from"],q=query,iq_id=iq["id"])
                        return

            cmd=iq.command
            if (cmd):
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(f=self.commands.onIqSet,iq=iq)
                else:
                    d=threads.deferToThread(f=self.commands.onIqSet,iq=iq)
                d.addCallback(self.xmlstream.send)
                d.addErrback(self.errorback)
                return
        iq = create_reply(iq)
        iq["type"]="error"
        err=iq.addElement("error")
        err["type"]="cancel"
        err.addElement("feature-not-implemented","urn:ietf:params:xml:ns:xmpp-stanzas")
        #print iq
        self.xmlstream.send(iq)

    def sendRegistrationForm(self,ans,q):
        """Sends registration form with old email if registered before
           'ans' parameter is stanza to be sent,
           'q' - is query child of ans
        """
        q.addElement("instructions").addContent(u"Введите email и пароль, используемые на vkontakte.ru")
        email=q.addElement("email")
        u=user(self,ans['to'],noLoop=True)
        try:
            u.readData()
            email.addContent(u.email)
            q.addElement("registered")
        except IOError, err:
            if (err.errno==2):
                pass
            else:
                print_exc()
        except:
            print_exc()
        q.addElement("password")
        ans.send()

    def sendTotalStats(self,data,ans,u):
        """send service stats as iq"""
        try:
            t=data[0][0]
            u["value"]=str(int(t))
        except IndexError:
            pass
        ans.send()

    def sendStatsMessage(self,to):
        total=0
        #FIXME
        ret=u"%s из %s пользователей в сети\n%s секунд аптайм\n%s входящих, %s исходящих пакетов\nxmpp траффик %sK/%sK"%(len(self.users),str(total),int(time.time()-self.startTime),self.logger.packetsIn,self.logger.packetsOut,self.logger.bytesIn/1024,self.logger.bytesOut/1024)
        self.sendMessage(self.jid,to,ret)

    def getUserList(self):
        ret=[]
        for i in os.listdir(self.datadir):
            dn=self.datadir+'/'+i
            if (os.path.isdir(dn)):
                for u in os.listdir(dn):
                    ret.append(u)
        return ret
        
    def sendProbes(self,to):
        n=0
        ulist=self.getUserList()
        for u in ulist:
            if not self.hasUser(u):
                self.sendPresence(self.jid,u,t="probe",sepThread=True)
                print repr(u)
                n+=1
                time.sleep(0.1)
        print "sendprobes done"
        ret=u"%s запросов отправлено. Пользователей всего - %s"%(n,len(ulist))
        #print ret.encode('utf-8')
        
        self.sendMessage(self.jid,to,ret,sepThread=True)

    def register2(self,jid,iq_id,success=0):
        #FIXME failed registration
        try:
            os.remove("%s/%s"%(self.cookPath,pyvkt.bareJid(jid)))
        except OSError:
            pass
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]=self.jid
        ans["id"]=iq_id
        ans.send()
        self.sendPresence(self.jid,jid,"subscribe")
        self.sendPresence(self.jid,jid,"subscribed")
        #pr=domish.Element(('',"presence"))
        #pr["type"]="subscribe"
        #pr["to"]=jid
        #pr["from"]=self.jid
        #self.xmlstream.send(pr)
        #pr=domish.Element(('',"presence"))
        #pr["type"]="subscribed"
        #pr["to"]=jid
        #pr["from"]=self.jid
        #self.xmlstream.send(pr)
        self.sendMessage(self.jid,jid,u"/get roster для получения списка\n/login для подключения\nТех.поддержка в конференции: pyvk-t@conference.jabber.ru")

    def sendFriendlist(self,fl,jid):
        #log.msg("fiendlist ",jid)
        #log.msg(fl)
        bjid=pyvkt.bareJid(jid)
        n=0
        if self.hasUser(bjid):
            for f in fl:
                src="%s@%s"%(f,self.jid)
                x=self.users[bjid].askSubscibtion(src,nick=u"%s %s"%(fl[f]["first"],fl[f]["last"]))
                if x: 
                    n+=1
            #self.sendPresence(src,jid,"subscribed")
            #self.sendPresence(src,jid,"subscribe")
            #return
            self.sendMessage(self.jid,jid,u"Отправлены запросы авторизации.")
        return

    def getSearchResult(self,jid,q,iq_id):
        """
        Send a search result we got from libvkontakte
        """
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]=self.jid
        ans["id"]=iq_id
        query=ans.addElement("query","jabber:iq:search")

        correct = 0
        text=u''
        for x in q.elements():
            if x.uri=='jabber:x:data' and x.hasAttribute('type') and x['type']=='submit':
                for j in x.elements():
                    if j.name=='field' and j.hasAttribute('var') and j['var']=='FORM_TYPE':
                        for v in j.elements():
                            if v.name=='value' and v.__str__()=='jabber:iq:search':
                                correct = 1
                                break
                    elif j.name=='field' and j.hasAttribute('var') and j['var']=='text':
                        for v in j.elements():
                            if v.name=='value':
                                text = v.__str__()
                                break
            if not correct: 
                text=u''
            else:
                break
        bjid=pyvkt.bareJid(jid)
        try:
            if text: 
                items=self.users[bjid].vclient.searchUsers(text)
                if items:
                    x=query.addElement("x","jabber:x:data")
                    x['type']='result'
                    hidden=x.addElement("field")
                    hidden['type']='hidden'
                    hidden['var']='FORM_TYPE'
                    hidden.addElement('value').addContent(u'jabber:iq:search')
                    item=x.addElement("reported")
                    field=item.addElement("field")
                    field['type']='jid-single'
                    field['label']=u'Jabber ID'
                    field['var']='jid'
                    field=item.addElement("field")
                    field['type']='text-single'
                    field['label']=u'Полное имя'
                    field['var']='FN'
                    field=item.addElement("field")
                    field['type']='text-single'
                    field['label']=u'Совпадение'
                    field['var']='matches'
                    field=item.addElement("field")
                    field['type']='text-single'
                    field['label']=u'Страница Вконтакте'
                    field['var']='url'
                    for i in items:
                        item=x.addElement("item")
                        field=item.addElement("field")
                        field['var']='jid'
                        field.addElement("value").addContent(i+u'@'+self.jid)
                        field=item.addElement("field")
                        field['var']='FN'
                        field.addElement("value").addContent(items[i]["name"])
                        field=item.addElement("field")
                        field['var']='matches'
                        field.addElement("value").addContent(items[i]["matches"])
                        field=item.addElement("field")
                        field['var']='url'
                        field.addElement("value").addContent(u"http://vkontakte.ru/id%s"%i)
        except:
            log.msg("some fcky error when searching")
        #log.msg(card)
        ans.send()


    def getsendVcard(self,jid,v_id,iq_id):
        """
        get vCard (user info) from vkontakte.ru and send it
        """
        #log.msg(jid)
        #log.msg(v_id)
        bjid=pyvkt.bareJid(jid)
        #try:
        card=self.users[bjid].vclient.getVcard(v_id, self.show_avatars)
        #except:
            #log.msg("some fcky error")
            #card = None

        #log.msg(card)
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]="%s@%s"%(v_id,self.jid)
        ans["id"]=iq_id
        vc=ans.addElement("vCard","vcard-temp")
        #if some card set
        if (card):
            #convert to unicode if needed
            for i in card:
                if (type(card[i])==type('')):
                    card[i]=card[i].decode("utf-8")
            if card.has_key("NICKNAME"):
                vc.addElement("NICKNAME").addContent(card["NICKNAME"])
            if card.has_key("FAMILY") or card.has_key("GIVEN"):
                n=vc.addElement("N")
                if card.has_key("FAMILY"):
                    n.addElement("FAMILY").addContent(card["FAMILY"])
                if card.has_key("GIVEN"):
                    n.addElement("GIVEN").addContent(card["GIVEN"])
            if card.has_key("FN"):
                vc.addElement("FN").addContent(card["FN"])
            if card.has_key(u'Веб-сайт:'):
                vc.addElement("URL").addContent(card[u"Веб-сайт:"])
            if card.has_key(u'День рождения:'):
                vc.addElement("BDAY").addContent(card[u"День рождения:"])
            #description
            descr=u""
            for x in (u"Семейное положение:",
                      u"Деятельность:",
                      u"Интересы:",
                      u"Любимая музыка:",
                      u"Любимые фильмы:",
                      u"Любимые телешоу:",
                      u"Любимые книги:",
                      u"Любимые игры:",
                      u"Любимые цитаты:"):
                if card.has_key(x):
                    descr+=x+u'\n'
                    descr+=card[x]
                    descr+=u"\n\n"
            if card.has_key(u'О себе:'):
                if descr: descr+=u"О себе:\n"
                descr+=card[u"О себе:"]
                descr+=u"\n\n"
            descr+="http://vkontakte.ru/id%s"%v_id
            descr=descr.strip()
            if descr:
                vc.addElement("DESC").addContent(descr)
            #phone numbers
            if card.has_key(u'Дом. телефон:'):
                tel = vc.addElement("TEL")
                tel.addElement("HOME")
                tel.addElement("NUMBER").addContent(card[u"Дом. телефон:"])
            if card.has_key(u'Моб. телефон:'):
                tel = vc.addElement(u"TEL")
                tel.addElement("CELL")
                tel.addElement("NUMBER").addContent(card[u"Моб. телефон:"])
            #avatar
            if self.show_avatars:
                #TODO roster 
                p=None
                if ans["from"] in self.users[bjid].roster:
                    if not self.users[bjid].roster[ans["from"]]:
                        self.users[bjid].roster[ans["from"]]={}
                    try:
                        oldurl=self.users[bjid].roster[ans["from"]]["avatar_url"]
                    except KeyError:
                        oldurl=u''
                    try:
                        oldhash=self.users[jid].roster[ans["from"]]["avatar_hash"]
                    except KeyError:
                        oldhash=u"nohash"
                    if "PHOTO" in card and card["PHOTO"]!=oldurl:
                        self.users[bjid].roster[ans["from"]]["avatar_url"]=card["PHOTO"]
                        print "card['PHOTO']=%s"%card["PHOTO"]
                        oldurl=card["PHOTO"]
                        if card["PHOTO"]:
                            oldhash="nohash"
                        else:
                            oldhash=""
                            self.users[bjid].roster[ans["from"]]["avatar_hash"]=""
                    if oldhash=="nohash" and oldurl:
                        h=self.users[bjid].vclient.getAvatar(oldurl,v_id,1)
                        if h:
                            p,self.users[bjid].roster[ans["from"]]["avatar_hash"]=h
                        else:
                            print "Error: no avatar"
                    elif oldurl:
                        p=self.users[bjid].vclient.getAvatar(oldurl,v_id)
                elif "PHOTO" in card:
                    p=self.vclient.getAvatar(card["PHOTO"],v_id)
                if p:
                    photo=vc.addElement(u"PHOTO")
                    photo.addElement("TYPE").addContent("image/jpeg")
                    photo.addElement("BINVAL").addContent(p.replace("\n",""))
            #adress
            if card.has_key(u'Город:'):
                vc.addElement(u"ADR").addElement("LOCALITY").addContent(card[u"Город:"])
        else:
            vc.addElement("DESC").addContent("http://vkontakte.ru/id%s"%v_id)
        ans.send()
            #log.msg(ans.toXml())

    def requestMessage(self,jid,msgid):
        #print "msg request"
        bjid=jid
        msg=self.users[bjid].vclient.getMessage(msgid)
        #log.msg(msg)
        #print msg
        self.sendMessage("%s@%s"%(msg["from"],self.jid),jid,pyvkt.unescape(msg["text"]),msg["title"])

    def submitMessage(self,jid,v_id,body,title):
        #log.msg((jid,v_id,body,title))
        bjid=jid
        try:
            self.users[bjid].vclient.sendMessage(to_id=v_id,body=body,title=title)
        except:
            print "submit failed"

    def updateStatus(self, bjid, text):
        """
        update site stuse if enabled
        """
        if (self.hasUser(bjid)):
            user=self.users[bjid]
        else:
            return
        if self.hasUser(bjid) and self.sync_status and not user.status_lock and user.getConfig("sync_status"):
            #print "updating status for",bjid,":",text.encode("ascii","replace")
            self.users[bjid].status_lock = 1
            self.users[bjid].vclient.setStatus(text)
            self.users[bjid].status_lock = 0

    def hasUser(self,bjid):
        #print "hasUser (%s)"%bjid
        if (self.users.has_key(bjid)):
            if self.users[bjid].state==2:
                return 1
            if self.users[bjid].state==4:
                try:
                    self.users[bjid].pool.stop()
                except:
                    pass
                try:
                    del self.users[bjid]
                except:
                    print_exc()
            return 0
        return 0
    def addResource(self,jid,prs=None):
        #print "addRes"
        bjid=pyvkt.bareJid(jid)
        #if (self.hasUser(bjid)==0):
        if (not self.users.has_key(bjid)):
            #print "creating user %s"
            self.users[bjid]=user(self,jid)
        self.users[bjid].addResource(jid,prs)

    def delResource(self,jid,to=None):
        #print "delResource %s"%jid
        bjid=pyvkt.bareJid(jid)
        if (self.hasUser(bjid)):
            #TODO resource magic
            self.users[bjid].delResource(jid)
        if (not self.users[bjid].resources) or to==self.jid:
            self.users[bjid].logout()

    def onPresence(self, prs):
        """
        Act on the presence stanza that has just been received.
        """
        if not prs.hasAttribute("from"):
            return
        bjid=pyvkt.bareJid(prs["from"])
        if(prs.hasAttribute("type")):
            if prs["type"]=="unavailable" and self.hasUser(bjid) and (prs["to"]==self.jid or self.users[bjid].subscribed(prs["to"]) or not self.roster_management):
                self.delResource(prs["from"],prs["to"])
                pr=domish.Element(('',"presence"))
                pr["type"]="unavailable"
                pr["to"]=prs["from"]
                pr["from"]=self.jid
                self.xmlstream.send(pr)
            elif(prs["type"]=="subscribe"):
                if self.hasUser(prs["from"]):
                    self.users[bjid].subscribe(pyvkt.bareJid(prs["to"]))
            elif(prs["type"]=="subscribed"):
                if self.hasUser(prs["from"]):
                    self.users[bjid].onSubscribed(pyvkt.bareJid(prs["to"]))
            elif(prs["type"]=="unsubscribe"):
                if self.hasUser(prs["from"]):
                    self.users[bjid].unsubscribe(pyvkt.bareJid(prs["to"]))
            elif(prs["type"]=="unsubscribed"):
                if self.hasUser(prs["from"]):
                    self.users[bjid].onUnsubscribed(pyvkt.bareJid(prs["to"]))
            return
        if (self.isActive or bjid==self.admin):
            self.addResource(prs["from"],prs)

    def updateFeed(self,jid,feed):
        ret=""
        if (not self.hasUser(pyvkt.bareJid(jid))):
            return
        for k in feed.keys():
            if (k in pyvkt.feedInfo) and ("count" in feed[k]) and feed[k]["count"]:
                ret=ret+u"Новых %s - %s\n"%(pyvkt.feedInfo[k]["message"],feed[k]["count"])
        ret = ret.strip()
        if self.hasUser(jid) and ret!=self.users[jid].status:
            self.users[jid].status = ret
            self.sendPresence(self.jid,jid,status=ret)
        ret=""
        try:
            if (feed["messages"]["count"]) and feed["messages"]["items"]:
                for i in feed ["messages"]["items"].keys():
                    #print "requesting message"
                    self.users[jid].pool.call(self.requestMessage,jid=jid,msgid=i)
        except KeyError:
            print_exc()
            pass
        oldfeed = self.users[jid].feed
        if self.hasUser(jid) and feed != self.users[jid].feed and ((oldfeed and self.users[jid].getConfig("feed_notify")) or (not oldfeed and self.users[jid].getConfig("start_feed_notify"))) and self.feed_notify:
            for j in pyvkt.feedInfo:
                if j!="friends" and j in feed and "items" in feed[j]:
                    gr=""
                    gc=0
                    for i in feed[j]["items"]:
                        if not (oldfeed and (j in oldfeed) and ("items" in oldfeed[j]) and (i in oldfeed[j]["items"])):
                            #it is a vkontakte.ru bug, when it stores null inside items. (e.g when there are invitaions to deleted groups)
                            if pyvkt.feedInfo[j]["url"] and feed[j]["items"]!="null":
                                try:
                                    gr+="\n  "+pyvkt.unescape(feed[j]["items"][i])+" [ "+pyvkt.feedInfo[j]["url"]%i + " ]"
                                except TypeError:
                                    print_exc()
                                    print repr(feed)
                                    print 'j:',j,'i:',i
                                    try:
                                        print 'feed[j]\n',repr(feed[j])
                                    except:
                                        pass
                            gc+=1
                    if gc:
                        if pyvkt.feedInfo[j]["url"]:
                            ret+=u"Новых %s - %s:%s\n"%(pyvkt.feedInfo[j]["message"],gc,gr)
                        else:
                            ret+=u"Новых %s - %s\n"%(pyvkt.feedInfo[j]["message"],gc)
            if ret:
                self.sendMessage(self.jid,jid,ret.strip())
            try:
                for i in feed["friends"]["items"]:
                    if not (oldfeed and ("friends" in oldfeed) and ("items" in oldfeed["friends"]) and i in oldfeed["friends"]["items"]):
                        text = u"Пользователь %s хочет добавить вас в друзья."%pyvkt.unescape(feed["friends"]["items"][i])
                        self.sendMessage("%s@%s"%(i,self.jid), jid, text, u"У вас новый друг!")
            except KeyError:
                pass
        self.users[jid].feed = feed

    def threadError(self,jid,err):
        return
        if (err=="banned"):
            self.sendMessage(self.jid,jid,u"Слишком много запросов однотипных страниц.\nКонтакт частично заблокировал доступ на 10-15 минут. На всякий случай, транспорт отключается")
        elif(err=="auth"):
            self.sendMessage(self.jid,jid,u"Ошибка входа. Возможно, неправильный логин/пароль.")
        try:
            self.users[pyvkt.bareJid(jid)].logout()
        except:
            pass
        self.sendPresence(self.jid,jid,"unavailable")
    def avatarChanged(self,v_id,user):
        print "avatar changed for id%s"%v_id
        if (self.pubsub):
            try:
                self.pubsub.updateAvatar(v_id,user)
            except:
                print_exc()
    def stopService(self, suspend=0,msg=None):
        #FIXME call this from different thread??
        print "stopping transport..."
        if (not suspend):
            print "stopping poolMgr..."
            self.pollMgr.alive=0
        if (len(self.users)==0):
            return
        #self.poolMgr.alive=0
        #print "stage 1: stopping users' loops, sending messages and presences..."

        for u in self.users.keys():
            if (self.hasUser(u)):
                #try:
                    #self.users[bjid].vclient.alive=0
                #except:
                    #pass
                if (msg):
                    self.sendMessage(self.jid,u,u"Транспорт отключается.\n[%s]"%msg)
                else:
                    self.sendMessage(self.jid,u,u"Транспорт отключается, в ближайшее время он будет запущен вновь.")
                self.sendPresence(self.jid,u,"unavailable")
                #try:
                    #self.usersOffline(u,self.users[u].vclient.onlineList)
                #except:
                    #pass
        #print "done"
        #time.sleep(15)
        dl=[]
        for i in self.users.keys():
            try:
                d=self.users[i].pool.defer(self.users[i].logout)
                dl.append(d)
            except AttributeError:
                pass
        print "%s logout()'s pending.. now we will wait..'"%len(dl)
        deflist=defer.DeferredList(dl)
        defer.waitForDeferred(deflist)
        print "done\ndeleting user objects"
        for i in self.users.keys():
            try:
                del self.users[i]
            except:
                pass
        if (len(threading.enumerate())):
            print "warning: some threads are still alive"
            print threading.enumerate()
        else:
            print "done"
        return None

    def sendMessage(self,src,dest,body,title=None,sepThread=False):
        msg=domish.Element((None,"message"))
        #try:
            #msg["to"]=dest.encode("utf-8")
        #except:
            #log.msg("sendMessage: possible charset error")
        msg["to"]=dest
        msg["from"]=src
        msg["type"]="chat"
        msg["id"]="msg%s"%(int(time.time())%10000)
        
        msg.addElement("body").addContent(body)
        if title:
            msg.addElement("subject").addContent(title)
        
        #FIXME "id"???
        try:
            
            if (0 and sepThread):
                reactor.callFromThread(self.xmlstream.send,msg)
            else:
                self.xmlstream.send(msg)            
        except UnicodeDecodeError:
            #FIXME user notify
            log.msg("unicode bug@sendMessage")
            try:
                print "jid: "%dest
            except:
                pass
            pass
    def sendPresence(self,src,dest,t=None,extra=None,status=None,show=None, nick=None,avatar=None,sepThread=False):
        pr=domish.Element((None,"presence"))
        if (t):
            pr["type"]=t
        try:
            dest=dest.decode('utf-8')
        except:
            pass
        pr["to"]=dest
        pr["from"]=src
        if(show):
            pr.addElement("show").addContent(show)
        #status
        if(status):
            if (type(status)==unicode):
                pr.addElement("status").addContent(status)
            else:
                #non-unicode status >>> FIXME
                pr.addElement("status").addContent(status.decode('utf-8'))
        #if contact goes offline we should not send extra information to supress traffic
        if (t!="unavailable"):
            pr.addElement("c","http://jabber.org/protocol/caps").attributes={"node":"http://pyvk-t.googlecode.com/caps","ver":self.revision}
            #nick
            if (nick):
                pr.addElement("nick",'http://jabber.org/protocol/nick').addContent(nick)
                if (type(nick)==unicode):
                    pr.addElement("nick",'http://jabber.org/protocol/nick').addContent(nick)
                else:
                    #non-unicode status >>> FIXME
                    pr.addElement("nick",'http://jabber.org/protocol/nick').addContent(nick.decode('utf-8'))
            #avatar
            if avatar!=None:#vcard based avatar
                x=pr.addElement("x")
                x["xmlns"]="vcard-temp:x:update"
                if avatar:#some avatar, possibly not ready
                    if avatar!="nohash":#got hash
                        x.addElement("photo").addContent(avatar)
                    else:#no hash ready
                        pass
                else:#empty avatar
                    x.addElement("photo")
                    pass
        try:
            if (0 and sepThread):
                reactor.callFromThread(self.xmlstream.send,pr)
            else:
                self.xmlstream.send(pr)
        except UnicodeDecodeError:
            log.msg("unicode bug@sendPresence")
            print_exc()
            try:
                print "jid: "%dest
            except:
                pass
            pass
    #def sendRosterItems(self,items,dest,act='modify')
        #msg=domish.Element((None,"message"))
        ##try:
            ##msg["to"]=dest.encode("utf-8")
        ##except:
            ##log.msg("sendMessage: possible charset error")
        #msg["to"]=dest
        #msg["from"]=self.jid
        #r=msg.addElement(x,'http://jabber.org/protocol/rosterx')
        #for v_id,nick in items:
            #r.addElement(item).attributes={'action'=act,jid="%s@%s"%(v_id,self.jid),name=nick}
        #self.xmlstream.send(msg)
    def __del__(self):
        print "stopping service..."
        self.stopService()
        self.pollMgr.stop()
        del self.pollMgr
        print "done"
    def errorback(self,err):
        print "ERR: error in deferred: %s (%s)"%(err.type,err.getErrorMessage)
        err.printTraceback()
    def signalHandler(self,sig,frame):
        if (sig==signal.SIGUSR1):
            print "caught SIGTUSR1, stopping transport"
            self.stopService()


