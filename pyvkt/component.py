#! /usr/bin/python
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
#import twisted
#from twisted.application import internet, service
from twisted.internet import interfaces, defer, reactor,threads
#from twisted.python import log
#from twisted.words.xish import domish
#from twisted.words.protocols.jabber.xmlstream import IQ
#from twisted.enterprise import adbapi 
#from twisted.enterprise.adbapi import safe 
#from twisted.words.protocols.jabber.ijabber import IService
#from twisted.words.protocols.jabber import component,xmlstream,jid

from base64 import b64encode,b64decode
#from zope.interface import Interface, implements
from base64 import b64encode,b64decode
from traceback import print_stack, print_exc,format_exc
import sys,os,platform,threading,signal,cPickle,sha,time,ConfigParser

from pyvkt.user import user,UnregisteredError
import pyvkt.general as gen
import pyvkt.user,pyvkt.commands
from libvkontakte import *
from pyvkt.spikes import pollManager,pseudoXml
import pyvkt.comstream
from pyvkt.comstream import addChild,createElement
import lxml.etree
from lxml import etree
from lxml.etree import SubElement,tostring
from threading import Lock
import gc,inspect
import pyvkt.config as conf
def create_reply(elem):
    """ switch the 'to' and 'from' attributes to reply to this element """
    # NOTE - see domish.Element class to view more methods 
    frm = elem['from']
    elem['from'] = elem['to']
    elem['to']   = frm

    return elem

#class LogService(component.Service):
    #"""
    #A service to log incoming and outgoing xml to and from our XMPP component.

    #"""
    #packetsIn = 0
    #packetsOut = 0
    #bytesIn = 0
    #bytesOut = 0
    #logIn=[]
    #logOut=[]
    #def transportConnected(self, xmlstream):
        #xmlstream.rawDataInFn = self.rawDataIn
        #xmlstream.rawDataOutFn = self.rawDataOut

    #def rawDataIn(self, buf):
        #self.packetsIn += 1
        #try:
            #self.logIn.append((time.time(),len(buf)))
            
        #except:
            #print_exc()
        #try:
            #self.bytesIn += len(buf)
        #except:
            #pass
        ##log.msg("%s - RECV: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        #pass

    #def rawDataOut(self, buf):
        #self.packetsOut += 1
        #try:
            #self.logOut.append((time.time(),len(buf)))
            #pass
        #except:
            #print_exc()
        #try:
            #self.bytesOut += len(buf)
        #except:
            #pass
        ##log.msg("%s - SEND: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        #pass
    #def getTraffic(self,t):
        #ct=time.time()
        #bt=ct-t
        #dt=ct-600
        
        ##print self.logIn
        #self.logIn=filter(lambda x:x[0]>dt,self.logIn,)
        #self.logOut=filter(lambda x:x[0]>dt,self.logOut)
        #il=filter(lambda x:x[0]>bt,self.logIn)
        #ol=filter(lambda x:x[0]>bt,self.logOut)
        #oc=0
        #ic=0
        #for i in il:ic+=i[1]
        #for i in ol:oc+=i[1]
        #return (ic,oc)
        
class pyvk_t(pyvkt.comstream.xmlstream):

    startTime = time.time()
    logger=None
    terminating=False
    isActive=1
    def __init__(self,jid):
        pyvkt.comstream.xmlstream.__init__(self,jid)
        self.httpIn = 0
        self.sync_status = 1
        self.show_avatars=conf.get('features','avatars')
        self.datadir=conf.get ('storage','datadir')
        self.roster_management= 1
        self.feed_notify= 1
        self.cachePath=conf.get('storage','cache')
        self.cookPath=conf.get('storage','cookies')
        self.name=conf.get('general','service_name')
        self.pubsub=None
        self.users={}
        self.admin=conf.get('general','admin')
        #self.config=config
        #try:
        proc=os.popen("svnversion")
        s=proc.read()
        if(s=="exported" or s==""):
            self.revision="alpha"
        else:
            p=s.find(":")
            ver=s[p+1:-1]
            self.revision="notwisted-branch-rev.%s"%ver
        self.commands=pyvkt.commands.cmdManager(self)
        self.pollMgr=pollManager(self)
        self.usrLock=Lock()
        self.unregisteredList=[]
        signal.signal(signal.SIGUSR1,self.signalHandler)
        signal.signal(signal.SIGUSR2,self.signalHandler)
    def handlePacket(self,st):
        if (st.tag=="message"):
            return self.onMsg(st)
        if (st.tag=="iq"):
            return self.onIq(st)
        if (st.tag=="presence"):
            return self.onPresence(st)
        logging.warning('unexpected stranza: "%s"'%st.tag)
    def onMsg(self,msg):
        src=msg.get("from")
        dest=msg.get("to")
        v_id=gen.jidToId(dest)
        if (msg.get("type")=='error'):
            return None
        if (v_id==-1):
            return None
        body=msg.find("body")
        logging.info("RECV: msg %s -> %s '%s'"%(src,dest,body))
        
        if (body==None or body.text==None):
            #logging.warning('strange message: %s'%tostring(msg))
            return
        body=body.text
        
        msgid=msg.get("id")
        bjid=gen.bareJid(src)
        if body[0:1]=='.':
            req=msg.find('{urn:xmpp:receipts}request')
            if (req!=None):
                self.msgDeliveryNotify(0,msg_id=msgid,jid=src,v_id=0,receipt=1)
            cmd=body[1:].rstrip()
            #if (self.users.has_key(bjid) and self.users[bjid].vclient and cmd=="get roster"):
            if (cmd=="get roster"):
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(self.users[bjid].vclient.getFriendList)
                    d.addCallback(self.sendFriendlist,jid=bjid)
                else:
                    self.sendMessage(self.jid,src,u"Сначала необходимо подключиться")
            elif (cmd=="help"):
                self.sendMessage(self.jid,src,u""".get roster - запрос списка контактов\n.list - список остальных команд""")
            else:
                #print cmd
                logging.warning("TEXTCMD '%s' %s -> %s"%(cmd,src,dest))
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(f=self.commands.onMsg,jid=src,text=cmd,v_id=v_id)
                    cb=lambda (x):self.sendMessage(dest,src,x)
                    d.addCallback(cb)
                    d.addErrback(self.errorback)
                else:
                    self.sendMessage(dest,src,self.commands.onMsg(jid=src,text=cmd,v_id=v_id))
            return

        if (body[0:1]=="#" and bjid==self.admin and dest==self.jid):
            req=msg.find('{urn:xmpp:receipts}request')
            if (req!=None):
                self.msgDeliveryNotify(0,msg_id=msgid,jid=src,v_id=0,receipt=1)
                # admin commands
            cmd=body[1:]

            logging.warning("admin command: '%s'"%cmd)
            if (cmd[:4]=="stop"):
                self.isActive=0
                if (cmd=="stop"):
                    self.stopService(suspend=True)
                else:
                    self.stopService(suspend=True,msg=cmd[5:])
                self.sendMessage(self.jid,src,"'%s' done"%cmd)
            elif (cmd=="start"):
                self.isActive=1
            elif (cmd=="sendprobes"):
                threads.deferToThread(self.sendProbes,src)
            elif (cmd=="collect"):
                gc.collect()
            elif (cmd[:4]=="eval"):
                try:
                    logging.warning("eval: "+repr(eval(cmd[5:])))
                except:
                    logging.error("exec failed"+format_exc())
            elif (cmd[:4]=="exec"):
                try:
                    execfile("inject.py")
                except:
                    logging.error("exec failed"+format_exc())
            elif (cmd=="users"):
                count = 0
                ret = u''
                for i in self.users.keys():
                    if (self.hasUser(i)):
                        ret=ret+u"\nxmpp:%s"%(i)
                        count+=1
                ret=u"%s user(s) online"%count + ret
                self.sendMessage(self.jid,src,ret)
            elif (cmd=="stats"):
                #TODO async request
                self.sendStatsMessage(src)

            #elif (cmd=="resources"):
                #count = 0
                #rcount = 0
                #ret = u''
                #for i in self.users.keys():
                    #if (self.hasUser(i)):
                        #for j in self.users[i].resources.keys():
                            #ret=ret+u"\nxmpp:%s %s(%s)[%s]"%(j,self.users[i].resources[j]["show"],self.users[i].resources[j]["status"],self.users[i].resources[j]["priority"])
                            #rcount +=1
                        #ret=ret+u"\n"
                        #count+=1
                #ret=u"%s(%s) user(s) online"%(count,rcount) + ret
                #self.sendMessage(self.jid,src,ret)
            #elif (cmd[:6]=="roster"):#Получение информации о ростере человека
                #logging.error("fixme")
                #j=cmd[7:]
                #if not j:
                        #j=src
                #j=pyvkt.bareJid(j)
                #ret=u'Ростер %s:\n'%j
                #if self.hasUser(j):
                    #ret = ret + u'\tКоличество контактов: %s\n'%len(self.users[j].roster)
                    #ret = ret + u'\tРазмер данных в БД: %s'%len(b64encode(cPickle.dumps(self.users[j].roster,2)))
                #else:
                    #ret = u'Пользователь %s не в сети, можете посмотреть его ростер в базе'%j
                #self.sendMessage(self.jid,msg["from"],ret)
            #elif(cmd=="stats2"):
                #for i in self.users.keys():
                    #try:
                        #print i
                        ##print "a=%s l=%s"%(self.users[i].active,self.users[i].lock)
                    #except:
                        #pass
            elif (cmd[:4]=="wall"):
                for i in self.users:
                    self.sendMessage(self.jid,i,"[broadcast message]\n%s"%cmd[5:])
                self.sendMessage(self.jid,src,"'%s' done"%cmd)
            #elif (cmd[:7]=='traffic'):
                #try:
                    #self.sendMessage(self.jid,msg["from"],"Traffic: %s"%repr(self.logger.getTraffic(int(cmd[7:]))))
                #except:
                    #print_exc()


            else:
                self.sendMessage(self.jid,src,"unknown command: '%s'"%cmd)
            return
            #logging.error("fixme: sending messages")op
            #return
        if(src!=self.jid and self.hasUser(bjid) and v_id):
            if self.users[bjid].getConfig("jid_in_subject"):
                title = "xmpp:%s"%bjid
            else:
                title = '...'
            try:
                title=msg.find("subject").text
            except:
                pass
            s=self.users[bjid].getConfig("signature")
            if s:
                body = body + u"\n--------\n" + s
            d=self.users[bjid].pool.defer(f=self.users[bjid].vclient.sendMessage,to_id=v_id,body=body,title=title)
            req=msg.find('{urn:xmpp:receipts}request')
            if (req!=None):
                d.addCallback(self.msgDeliveryNotify,msg_id=msgid,jid=src,v_id=v_id,receipt=1,body=body,subject=title)
            else:
                d.addCallback(self.msgDeliveryNotify,msg_id=msgid,jid=src,v_id=v_id,body=body,subject=title)
            d.addErrback(self.errorback)
    def startPoll(self):
        self.pollMgr.start()        
    def msgDeliveryNotify(self,res,msg_id,jid,v_id,receipt=0,body=None,subject=None):
        """
        Send delivery notification if message successfully sent
        use receipt flag if needed to send receipt
        """
        if (v_id):
            src="%s@%s"%(v_id,self.jid)
        else:
            src=self.jid
        #msg=domish.Element((None,"message"))
        if (msg_id):
            msg=createElement("message",{'to':jid,'from':src,'id':msg_id})
        else:
            logging.warning('receipt request without id. %s -> %s'%(src,jid))
            msg=createElement("message",{'to':jid,'from':src})
            #if res!=0:
        #    if body:
        #        msg.addElement("body").addContent(body)
        #    if subject:
        #        msg.addElement("subject").addContent(subject)
        #msg["to"]=jid
        #msg["id"]=msg_id
        if res == 0 and receipt:
            addChild(msg,'received','urn:xmpp:receipts')
            #msg.addElement("received",'urn:xmpp:receipts')
        elif res == 0:
            return #no reciepts needed and no errors
        elif res == 2:
            err=addChild(msg,'error',attrs={'type':'wait','code':'500'})
            addChild(err,"resource-constraint","urn:ietf:params:xml:ns:xmpp-stanzas")
            addChild(err,"too-many-stanzas","urn:xmpp:errors")
            addChild(err,"text","urn:ietf:params:xml:ns:xmpp-stanzas").text=u"Слишком часто посылаете сообщения. Подождите немного."
        else:
            err=addChild(msg,'error',attrs={'type':'cancel','code':'500'})
            addChild(err,"undefined-condition","urn:ietf:params:xml:ns:xmpp-stanzas")
            addChild(err,"text","urn:ietf:params:xml:ns:xmpp-stanzas").text=u"Капча на сайте или ошибка сервера"

        self.send(msg)
    def onIq(self,iq):
        #return False
        def getQuery(iq,ans,ns):
            #print etree.tostring(iq)
            r=iq.find('{%s}query'%ns)
            #print r
            if r==None:
                return (None,None)
            logging.info('query ns: %s'%ns)
            a=addChild(ans,'query',ns)
            return (r,a)
        src=iq.get("from")
        dest=iq.get("to")
        iq_id=iq.get('id')
        if (not iq_id):
            #TODO error stranza
            logging.warning('iq stranza without id: %s -> %s'%(src,dest))
            return
        bjid=gen.bareJid(src)
        ans=createElement('iq',attrs={'from':dest,'to':src, 'id':iq.get('id'),'type':'result'})
        #logging.warning(iq.get('type'))
        logging.info("RECV: iq (%s) %s -> %s"%(iq.get('type'),src,dest))
        if (iq.get('type')=='get'):
            #FIXME TODO commands
            r,a=getQuery(iq,ans,'http://jabber.org/protocol/disco#info')
            if r!=None:
                node=r.get("node",'')
                #logging.warning(node)
                if (node==''):
                    if (dest==self.jid):
                        addChild(a,'identity',attrs={'category':'gateway','type':'vkontakte.ru','name':self.name})
                        features=[
                            "jabber:iq:register",
                            "jabber:iq:gateway",
                            "jabber:iq:version",
                            "jabber:iq:last",
                            'http://jabber.org/protocol/commands',
                            'http://jabber.org/protocol/stats',
                            "urn:xmpp:receipts"
                            ]
                        if (self.hasUser(src)):
                            #features.append("jabber:iq:search")
                            pass
                    else:
                        SubElement(a,'identity',category='pubsub',type='pep')
                        addChild(a,'identity',attrs={'category':'pubsub','type':'pep'})
                        features=[
                            "jabber:iq:version",
                            'http://jabber.org/protocol/commands',
                            "urn:xmpp:receipts"
                            ]
                    for i in features:
                        SubElement(a,'feature',var=i)
                elif (node=='friendsonline'):
                    addChild(a,'identity',attrs={"name":u'Друзья в сети',"category":"automation","type":"command-node"})
                elif (node=="http://jabber.org/protocol/commands" or node[:4]=='cmd:'):
                    self.send(self.commands.onDiscoInfo(iq))
                    
                else:
                    ans.set('type','error')
                    addChild(ans,'item-not-found','urn:ietf:params:xml:ns:xmpp-stanzas',{'type':'cancel'})
                self.send(ans)
                return True
            r,a=getQuery(iq,ans,'http://jabber.org/protocol/disco#items')
            if r!=None:
                node=r.get("node")
                if (node):
                    a.set('node',node)
                    if (node=='friendsonline'):
                        if (self.hasUser(bjid)):
                            for i in self.users[bjid].onlineList:
                                cname=u'%s %s'%(self.users[bjid].onlineList[i]["first"],self.users[bjid].onlineList[i]["last"])
                                addChild(a,"item",attrs={"node":"http://jabber.org/protocol/commands",'name':cname,'jid':"%s@%s"%(i,self.jid)})
                        #FIXME 'not found' stranza
                    elif (node=="http://jabber.org/protocol/commands"):
                        self.send(self.commands.onDiscoItems(iq))
                        return
                        
                else:
                    addChild(a,'item',attrs={"node":"http://jabber.org/protocol/commands",'name':'Pyvk-t commands','jid':self.jid})
                    if (dest==self.jid and self.hasUser(bjid)):
                        addChild(a,'item',attrs={"node":"friendsonline",'name':'Friends online [broken]','jid':self.jid})
                        #q.addElement("item").attributes={"node":"friendsonline",'name':'Friends online','jid':self.jid}
                self.send(ans)
                return True
            r,a=getQuery(iq,ans,'http://jabber.org/protocol/stats')
            if r!=None:
                if (len(r)):
                    values={
                        'time/uptime':('seconds',str(int(time.time()-self.startTime))),
                        'users/online':('users',str(len(self.users)))
                        }
                    for i in r:
                        name=i.get('name')
                        if (values.has_key(name)):
                            v=values[name]
                            addChild(a,'stat',attrs={'name':name,'units':v[0],'value':v[1]})
                        else:
                            s=addChild(a,'stat',attrs={'name':name})
                            addChild(s,'error',attrs={'code':'404'})
                else:
                    values=['time/uptime','users/online']
                    for i in values:
                        addChild(a,'stat',attrs={'name':i})
                self.send(ans)
                return True
            r,a=getQuery(iq,ans,'jabber:iq:last')
            if r!=None:
                a.set('seconds',str(int(time.time()-self.startTime)))
                self.send(ans)
                return True
            r,a=getQuery(iq,ans,'jabber:iq:version')
            if r!=None:
                values={'name':'pyvk-t','version':self.revision,'os':platform.system()+" "+platform.release()+" "+platform.machine()}
                for i in values:
                    addChild(a,i).text=values[i]
                self.send(ans)
                return True
            r,a=getQuery(iq,ans,'jabber:iq:register')
            if r!=None:
                addChild(a,'instructions').text=u"Введите email и пароль, используемые на vkontakte.ru"
                #q.addElement("instructions").addContent()
                
                email=addChild(a,"email")
                u=user(self,bjid,noLoop=True)
                try:
                    u.readData()
                    email.text=u.email
                    addChild(a,"registered")
                except IOError, err:
                    if (err.errno==2):
                        pass
                    else:
                        print_exc()
                except UnregisteredError:
                    pass
                except:
                    print_exc()
                addChild(a,"password")
                self.send(ans)
                return True
            vcard=iq.find("{vcard-temp}vCard")
            if (vcard!=None):
                dogpos=dest.find("@")
                if(dogpos!=-1):
                        #log.msg("id: %s"%v_id)
                    if (self.hasUser(bjid)):
                        #self.users[bjid].pool.callInThread(time.sleep(1))
                        v_id=gen.jidToId(dest)
                        self.users[bjid].pool.call(self.getsendVcard,jid=src,v_id=v_id,iq_id=iq.get("id"))
                        return
                        pass
                    else:
                        ans=createElement("iq",{'type':'result','to':src,'from':dest,'id':iq.get("id")})
                        err=addChild(ans,"error",attrs={'type':'auth','code':'400'})
                        addChild(err,"non-authorized",'urn:ietf:params:xml:ns:xmpp-stanzas')
                        t=addChild(err,"text",'urn:ietf:params:xml:ns:xmpp-stanzas')
                        #t.set("xml:lang","ru")
                        t.text=u"Для запроса vCard необходимо подключиться.\nДля подключения отправьте .login или используйте ad-hoc."
                        self.send(ans)
                        return
                            #err.addElement("too-many-stanzas","urn:xmpp:errors")
                else:
                    ans=createElement("iq",{'type':'result','to':src,'from':dest,'id':iq.get("id")})
                    q=etree.SubElement(ans,"{vcard-temp}vCard")
                    #q=ans.addElement("vCard","vcard-temp")
                    addChild(q,"FN").text=self.name
                    addChild(q,"URL").text="http://pyvk-t.googlecode.com"
                    addChild(q,"DESC").text="Vkontakte.ru jabber transport\nVersion: %s"%self.revision
                    #print etree.tostring(ans)
                    if self.show_avatars:
                        try:
                            req=open("avatar.png")
                            photo=base64.encodestring(req.read())
                            p=etree.SubElement(ans,"PHOTO")
                            etree.SubElement(q,"TYPE").text="image/png"
                            etree.SubElement(q,"BINVAL").text=photo.replace("\n","")
                        except:
                            logging.warning('cannot load avatar')
                            print_exc()
                    self.send(ans)
                    return
            #TODO search and jabber:iq:gateway
        if (iq.get("type")=="set"):
            #query=iq.query
            r,a=getQuery(iq,ans,'jabber:iq:register')
            if (r!=None):
                q=r
                #FIXME rename q -> r
                bjid=gen.bareJid(src)
                if (r.find("remove")!=None):
                    try:
                        os.unlink("%s/%s/%s"%(self.datadir,bjid[:1],bjid))
                    except OSError:
                        pass
                    return
                if (r.find("{jabber:iq:register}remove")!=None):
                    logging.warning ("FIXME namespace in register/remove")
                    try:
                        os.unlink("%s/%s/%s"%(self.datadir,bjid[:1],bjid))
                    except OSError:
                        pass
                    return
                    
                logging.warning("new user: %s"%bjid)
                try:
                    email=q.find("{jabber:iq:register}email").text
                    pw=q.find("{jabber:iq:register}password").text
                except AttributeError:
                    logging.warning("iq:register: can't find email or pass. TODO: error message")
                    iq.set('type','error')
                    iq.set('to',src)
                    iq.set('from',dest)
                    e=addChild(iq,'error',attrs={'code':'406','type':'modify'})
                    addChild(e,'non-acceptable','urn:ietf:params:xml:ns:xmpp-stanzas')
                    logging.warn(etree.tostring(iq))
                    self.send(iq)
                    return True
                if (not (email and pw)):
                    logging.warning("register: empty email or password")
                #FIXME asynchronous!!
                u=user(self,gen.bareJid(src))
                try:
                    u.readData()
                except:
                    #logging.info("registration: cant read data. possible new user")
                    u.config={}
                u.email=email
                u.password=pw
                u.saveData()
                ans=createElement("iq",{'type':'result','to':src,'from':dest,'id':iq.get('id')})
                self.send(ans)
                self.sendPresence(self.jid,src,"subscribe")
                self.sendPresence(self.jid,src,"subscribed")
                self.sendMessage(self.jid,src,u".get roster для получения списка\n.login для подключения\nТех.поддержка в конференции: pyvk-t@conference.jabber.ru")
                return True
                #if (query.uri=="jabber:iq:gateway"):
                    #for prompt in query.elements():
                        #if prompt.name=="prompt":
                            #ans=xmlstream.IQ(self.xmlstream,"result")
                            #ans["to"]=src
                            #ans["from"]=dest
                            #ans["id"]=iq["id"]
                            #q=ans.addElement("query",query.uri)
                            #q.addElement("jid").addContent("%s@%s"%(prompt,dest))
                            #self.send(ans)
                            #return
                #elif (query.uri=="jabber:iq:search") and (self.hasUser(bjid)):
                        #time.sleep(1)
                        #self.users[bjid].pool.call(self.getSearchResult,jid=src,q=query,iq_id=iq["id"])
                        #return
            #r,a=getQuery(iq,ans,'jabber:iq:register')
            c=iq.find('{http://jabber.org/protocol/commands}command')
            if (c!=None):
                #logging.warning('command')
                
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(f=self.commands.onIqSet,iq=iq)
                    d.addCallback(self.send)
                    return True
                else:
                    self.send(self.commands.onIqSet(iq))
                    return True
                    #d=threads.deferToThread(f=self.commands.onIqSet,iq=iq)
                    #d.addCallback(self.send)
                    #d.addErrback(self.errorback)
            #cmd=iq.command
            #if (cmd):
                #if (self.hasUser(bjid)):
                    #d=self.users[bjid].pool.defer(f=self.commands.onIqSet,iq=iq)
                #else:
                    #d=threads.deferToThread(f=self.commands.onIqSet,iq=iq)
                #return
        if (iq.find('{urn:xmpp:time}time')!=None):
            pass
        elif(iq.find('{http://jabber.org/protocol/pubsub}pubsub')!=None):
            pass
        else:
            if (len(iq)):
                logging.warning("not implemented: %s -> %s\t%s"%(src,dest,etree.tostring(iq[0])))
            else:
                if (src==dest):
                    logging.info ('keepalive received')
                return
                
        iq = createElement("iq",{'type':'error','to':src,'from':dest,'id':iq.get("id")})
        addChild(iq,"feature-not-implemented",'urn:ietf:params:xml:ns:xmpp-stanzas')
        self.send(iq)                        
        return False
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
        self.send(ans)

    def sendTotalStats(self,data,ans,u):
        """send service stats as iq"""
        try:
            t=data[0][0]
            u["value"]=str(int(t))
        except IndexError:
            pass
        self.send(ans)

    def sendStatsMessage(self,to):
        ret=u"%s пользователей в сети\n%s секунд аптайм\n%s threads active"%(len(self.users),int(time.time()-self.startTime),len(threading.enumerate()))
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
            os.remove("%s/%s"%(self.cookPath,gen.bareJid(jid)))
        except OSError:
            pass
        ans=createElement("iq",{'type':'result','to':jid,'from':self.jid,'id':iq_id})

        self.send(ans)
        self.sendPresence(self.jid,jid,"subscribe")
        self.sendPresence(self.jid,jid,"subscribed")

        self.sendMessage(self.jid,jid,u".get roster для получения списка\n.login для подключения\nТех.поддержка в конференции: pyvk-t@conference.jabber.ru")

    def sendFriendlist(self,fl,jid):

        bjid=gen.bareJid(jid)
        n=0
        if self.hasUser(bjid):
            for f in fl:
                src="%s@%s"%(f,self.jid)
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
                x=self.users[bjid].askSubscibtion(src,nick=nick)
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
        bjid=gen.bareJid(jid)
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
            logging.warning("some fcky error when searching")
        #log.msg(card)
        self.send(ans)


    def getsendVcard(self,jid,v_id,iq_id):
        """
        get vCard (user info) from vkontakte.ru and send it
        """
        bjid=gen.bareJid(jid)
        if (not self.hasUser(bjid)):
            #TODO error stranza
            logging.warning("unauthorised vcard request. TODO error stranza")
            return
        card=self.users[bjid].vclient.getVcard(v_id, self.show_avatars)
        if (not card):
            logging.warning('can\'t get vcard: id%s -> %s'%(v_id,jid))
            #FIXME error stranza
            return
        ans=createElement("iq",{'type':'result','to':jid,'from':"%s@%s"%(v_id,self.jid),'id':iq_id})
        vc=addChild(ans,'vCard','vcard-temp')
        def addField(name,key):
            try:
                SubElement(vc,name).text=card[key]
            except KeyError:
                pass
            except ValueError:
                logging.warning('unicode error.\n%s'%repr(card[key]))
        if (card):
            for i in card:
                if (type(card[i])==type('')):
                    card[i]=card[i].decode("utf-8")
                    # is it necessary?
            pass
        for i in (("NICKNAME","NICKNAME"),("FN",'FN'),(u'Веб-сайт:',"URL"),(u'День рождения:',"BDAY")):
            k,n=i
            addField(n,k)
        descr=u""
        for x in (u"Семейное положение:",
                    u"Деятельность:",
                    u"Интересы:",
                    u"Любимая музыка:",
                    u"Любимые фильмы:",
                    u"Любимые телешоу:",
                    u"Любимые книги:",
                    u"Любимые игры:",
                    u"Любимые цитаты:",
                    u'О себе:'):
            if card.has_key(x):
                descr+=x+u'\n'
                descr+=card[x]
                descr+=u"\n\n"
        descr+="http://vkontakte.ru/id%s"%v_id
        descr=descr.strip()
        try:
            SubElement(vc,"DESC").text=descr
        except ValueError,e:
            SubElement(vc,"DESC").text='[invalid data]'
            logging.error('vcard: bad descr: (%s)'%(e))
        if self.show_avatars:
            #TODO roster 
            p=None
            if ans.get("from") in self.users[bjid].roster:
                if not self.users[bjid].roster[ans.get("from")]:
                    self.users[bjid].roster[ans.get("from")]={}
                try:
                    oldurl=self.users[bjid].roster[ans.get("from")]["avatar_url"]
                except KeyError:
                    oldurl=u''
                try:
                    oldhash=self.users[jid].roster[ans.get("from")]["avatar_hash"]
                except KeyError:
                    oldhash=u"nohash"
                if "PHOTO" in card and card["PHOTO"]!=oldurl:
                    self.users[bjid].roster[ans.get("from")]["avatar_url"]=card["PHOTO"]
                    print "card['PHOTO']=%s"%card["PHOTO"]
                    oldurl=card["PHOTO"]
                    if card["PHOTO"]:
                        oldhash="nohash"
                    else:
                        oldhash=""
                        self.users[bjid].roster[ans.get("from")]["avatar_hash"]=""
                if oldhash=="nohash" and oldurl:
                    h=self.users[bjid].vclient.getAvatar(oldurl,v_id,1)
                    if h:
                        p,self.users[bjid].roster[ans.get("from")]["avatar_hash"]=h
                    else:
                        print "Error: no avatar"
                elif oldurl:
                    p=self.users[bjid].vclient.getAvatar(oldurl,v_id)
            elif "PHOTO" in card:
                p=self.vclient.getAvatar(card["PHOTO"],v_id)
            if p:
                photo=SubElement(vc,u"PHOTO")
                SubElement(photo,"TYPE").text="image/jpeg"
                SubElement(photo,"BINVAL").text=p.replace("\n","")
        self.send(ans)
        return
    def requestMessage(self,jid,msgid):
        #print "msg request"
        bjid=jid
        msg=self.users[bjid].vclient.getMessage(msgid)
        #log.msg(msg)
        #print msg
        self.sendMessage("%s@%s"%(msg["from"],self.jid),jid,gen.unescape(msg["text"]),msg["title"])

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
    def addResource(self,jid,prs=None,captcha_key=None):
        #print "addRes"
        bjid=gen.bareJid(jid)
        #if (self.hasUser(bjid)==0):
        self.usrLock.acquire()
        if (not self.users.has_key(bjid)):
            #print "creating user %s"
            self.users[bjid]=user(self,jid,captcha_key=captcha_key)
        self.usrLock.release()
        self.users[bjid].addResource(jid,prs)

    def delResource(self,jid,to=None):
        #print "delResource %s"%jid
        bjid=gen.bareJid(jid)
        if (self.hasUser(bjid)):
            #TODO resource magic
            self.users[bjid].delResource(jid)
        if (not self.users[bjid].resources) or to==self.jid:
            self.users[bjid].logout()

    def onPresence(self, prs):
        """
        Act on the presence stanza that has just been received.
        """
        ptype=prs.get("type")
        src=prs.get("from")
        dest=prs.get("to")
        logging.info("RECV: prs %s -> %s type=%s"%(src,dest,ptype))
        bjid=gen.bareJid(src)
        if(ptype):
            if ptype=="unavailable" and self.hasUser(bjid) and (dest==self.jid or self.users[bjid].subscribed(dest) or not self.roster_management):
                self.delResource(src,dest)
                self.sendPresence(dest,src,t='unavailable')
                
                #pr=domish.Element(('',"presence"))
                #pr["type"]="unavailable"
                #pr["to"]=src
                #pr["from"]=self.jid
                #self.send(pr)
            elif(ptype=="subscribe"):
                if self.hasUser(src):
                    self.users[bjid].subscribe(gen.bareJid(dest))
            elif(ptype=="subscribed"):
                if self.hasUser(src):
                    self.users[bjid].onSubscribed(gen.bareJid(dest))
            elif(ptype=="unsubscribe"):
                if self.hasUser(src):
                    self.users[bjid].unsubscribe(gen.bareJid(dest))
            elif(ptype=="unsubscribed"):
                if self.hasUser(src):
                    self.users[bjid].onUnsubscribed(gen.bareJid(dest))
            return
        if (self.isActive or bjid==self.admin):
            self.addResource(src,prs)

    def updateFeed(self,jid,feed):
        ret=""
        if (not self.hasUser(gen.bareJid(jid))):
            return
        for k in feed.keys():
            if (k in gen.feedInfo) and ("count" in feed[k]) and feed[k]["count"]:
                ret=ret+u"Новых %s - %s\n"%(gen.feedInfo[k]["message"],feed[k]["count"])
        ret = ret.strip()
        s=conf.get('features/status')
        if (s):
            ret=ret+'\n{%s}'%s
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
        except:
            logging.warning("bad feed\n"+repr(feed)+"\nexception: "+format_exc())        
        oldfeed = self.users[jid].feed
        if self.hasUser(jid) and feed != self.users[jid].feed and ((oldfeed and self.users[jid].getConfig("feed_notify")) or (not oldfeed and self.users[jid].getConfig("start_feed_notify"))) and self.feed_notify:
            for j in gen.feedInfo:
                if j!="friends" and j in feed and "items" in feed[j] and feed[j]['items']:
                    gr=""
                    gc=0
                    for i in feed[j]["items"]:
                        if not (oldfeed and (j in oldfeed) and ("items" in oldfeed[j]) and (i in oldfeed[j]["items"])):
                            #it is a vkontakte.ru bug, when it stores null inside items. (e.g when there are invitaions to deleted groups)
                            if gen.feedInfo[j]["url"] and feed[j]["items"]!="null":
                                try:
                                    gr+="\n  "+gen.unescape(feed[j]["items"][i])+" [ "+gen.feedInfo[j]["url"]%i + " ]"
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
                        if gen.feedInfo[j]["url"]:
                            ret+=u"Новых %s - %s:%s\n"%(gen.feedInfo[j]["message"],gc,gr)
                        else:
                            ret+=u"Новых %s - %s\n"%(gen.feedInfo[j]["message"],gc)
            if ret:
                self.sendMessage(self.jid,jid,ret.strip())
            try:
                #FIXME wtf 'null' in items?
                #FIXME oldfeed?
                try:
                    nfl=feed['friends']['items']
                    nfl[0]
                except (KeyError,TypeError),e:
                    pass
                    #warning ('feed: no new friends? '+str(e))
                else:
                    for i in nfl:
                        try:
                            if i in oldfeed["friends"]["items"]:
                                continue
                        except (KeyError, TypeError):
                            logging.warning('feed error defeated! =)')
                        text = u"Пользователь %s хочет добавить вас в друзья."%gen.unescape(feed["friends"]["items"][i])
                        self.sendMessage("%s@%s"%(i,self.jid), jid, text, u"У вас новый друг!")
                            
                            #old friendlist
                            
                        #if (not (oldfeed and ("friends" in oldfeed) and ("items" in oldfeed["friends"]) and i in oldfeed["friends"]["items"])) or (not oldfeed["friends"]["items"]):
                            #text = u"Пользователь %s хочет добавить вас в друзья."%gen.unescape(feed["friends"]["items"][i])
                            #self.sendMessage("%s@%s"%(i,self.jid), jid, text, u"У вас новый друг!")
            #except KeyError:
                #pass
            except:
                logging.warning("bad feed\n"+repr(feed)+"\nexception: "+format_exc())
                
        self.users[jid].feed = feed

    def threadError(self,jid,err):
        return
        if (err=="banned"):
            self.sendMessage(self.jid,jid,u"Слишком много запросов однотипных страниц.\nКонтакт частично заблокировал доступ на 10-15 минут. На всякий случай, транспорт отключается")
        elif(err=="auth"):
            self.sendMessage(self.jid,jid,u"Ошибка входа. Возможно, неправильный логин/пароль.")
        try:
            self.users[gen.bareJid(jid)].logout()
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
                try:
                    self.usersOffline(u,self.users[u].vclient.onlineList)
                except:
                    pass
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
        time.sleep(15)
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
        msg=createElement("message",{'to':dest,'from':src,'type':'chat','id':"msg%s"%(int(time.time())%10000)})
        SubElement(msg,'body').text=body
        if title:
            SubElement(msg,'title').text=title
        self.send(msg)
    def sendPresence(self,src,dest,t=None,extra=None,status=None,show=None, nick=None,avatar=None,sepThread=False):
        pr=createElement("presence",{"from":src,'to':dest})
        if (t):
            pr.set('type',t)
        if(show):
            SubElement(pr,'show').text=show
        if(status):
            try:
                SubElement(pr,'status').text=status
            except ValueError:
                SubElement(pr,'status').text=status.replace('\0','')
                logging.warning('null byte in status: fixed')
                
        #if contact goes offline we should not send extra information to supress traffic
        if (t!="unavailable"):
            addChild(pr,'c',ns="http://jabber.org/protocol/caps",attrs={"node":"http://pyvk-t.googlecode.com/caps","ver":self.revision})
            if (nick):
                addChild(pr,'nick','http://jabber.org/protocol/nick').text=nick
            if avatar!=None:#vcard based avatar
                x=addChild(pr,"x",'vcard-temp:x:update')
                if avatar:#some avatar, possibly not ready
                    if avatar!="nohash":#got hash
                        SubElement(x,'photo').text=avatar
                    else:#no hash ready
                        pass
                else:#empty avatar
                    SubElement(x,'photo')
        self.send(pr)
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
    def term(self):
        if (self.terminating):
            sys.exit(1)
        else:
            self.terminating=1
            #self.alive=0
            self.stopService()
    def errorback(self,err):
        print "ERR: error in deferred: %s (%s)"%(err.type,err.getErrorMessage)
        err.printTraceback()
    def signalHandler(self,sig,frame):
        logging.warn("got signal %s"%sig)
        if (sig==signal.SIGUSR1):
            #print "caught SIGTUSR1, stopping transport"
            #self.stopService()
            self.alive=False
        elif (sig==signal.SIGUSR2):
            logging.error('got SIGUSR2. executing hook...')
            try:
                execfile("inject.py")
            except:
                logging.error("exec failed"+format_exc())

    def kbInterrupt(self):
        print "threads:"
        for i in threading.enumerate():
            print '    %s (%s)'%(i.name,i.daemon)
        return True

