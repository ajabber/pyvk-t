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

from base64 import b64encode, b64decode
from traceback import print_stack, print_exc,format_exc
import sys,os,platform,threading,signal,cPickle,time,ConfigParser, hashlib
import subprocess,traceback

from pyvkt.user import user,UnregisteredError
import pyvkt.general as gen
import pyvkt.user,pyvkt.commands, pyvkt.comstream
from libvkontakte import *
from pyvkt.spikes import pollManager,pseudoXml,UserThreadPool
from pyvkt.comstream import addChild,createElement
#import lxml.etree
from lxml import etree
from lxml.etree import SubElement,tostring
from threading import Lock
import gc,inspect
import pyvkt.config as conf
from pyvkt.control import ControlSocketListener
from datetime import datetime

class pyvk_t(pyvkt.comstream.xmlstream):

    startTime = time.time()
    logger=None
    terminating=False
    isActive=1
    latency=0
    timeCounters={'feed':0.,'online':0.,'status':0.,'wall':0.}
    callCounters={'feed':0.,'online':0.,'status':0.,'wall':0.}
    def __init__(self,jid):
        pyvkt.comstream.xmlstream.__init__(self,jid)
        self.httpIn = 0
        self.sync_status = 1
        self.show_avatars=conf.get('features','avatars')
        self.datadir=conf.get ('storage','datadir')
        self.roster_management= 1
        self.cachePath=conf.get('storage','cache')
        self.cookPath=conf.get('storage','cookies')
        self.name=conf.get('general','service_name')
        self.pubsub=None
        self.users={}
        self.admins=conf.get('general','admin').split()
        if (conf.get('general','control_socket')):
            logging.warning('starting CSL')
            self.csl=ControlSocketListener(self)
            self.csl.start()
        else:
            logging.warning('ControlSocket disabled')

        self.admin=self.admins[0]
        #self.config=config
        try:
            d=os.path.dirname(os.path.realpath(__file__))
            d=os.path.abspath('%s/..'%d)
            proc=subprocess.Popen(["svnversion", d],stdout=subprocess.PIPE).stdout
            
            s=proc.read()
            if(s=="exported" or s==""):
                self.revision="alpha"
            else:
                p=s.find(":")
                ver=s[p+1:-1]
                self.revision="svn-rev.%s"%ver
        except OSError:
               self.revision="alpha"
        self.commands=pyvkt.commands.cmdManager(self)
        self.pollMgr=pollManager(self)
        self.usrPool=UserThreadPool(self)
        for i in range(3):
            self.usrPool.addThread()
        self.usrLock=Lock()
        self.unregisteredList=[]
        signal.signal(signal.SIGUSR1,self.signalHandler)
        signal.signal(signal.SIGUSR2,self.signalHandler)
    def addPerfStats(self,tc, cc):
        for i in tc.keys():
            self.timeCounters[i]+=tc[i]
            self.callCounters[i]+=cc[i]
    def handlePacket(self,st,dbg):
        try:
            if (st.tag.endswith("message")):
                return self.onMsg(st)
            if (st.tag.endswith("iq")):
                return self.onIq(st)
            if (st.tag.endswith("presence")):
                return self.onPresence(st, dbg)
            logging.warning('strange packet from %s'%repr(st.get('from')))
        except gen.QuietError:
            return
            logging.warning('QuietError')
    def onMsg(self,msg):
        src=msg.get("from")
        dest=msg.get("to")
        v_id=gen.jidToId(dest)
        if (msg.get("type")=='error'):
            return None
        if (v_id==-1):
            return None
        body=msg.find("body")
        if (body==None):
            body=msg.find("{jabber:client}body")
            if (body!=None):
                logging.warning('need to fix namespace!')
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
                self.sendMessage(self.jid,src,u"Теперь команда пишется без пробела: .getroster")
                return
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(self.users[bjid].vclient.getFriendList)
                    d.addCallback(self.sendFriendlist,jid=bjid)
                else:
                    self.sendMessage(self.jid,src,u"Сначала необходимо подключиться")
            elif (cmd=="help"):
                self.sendMessage(self.jid,src,u""".getroster - запрос списка контактов\n.list - список остальных команд""")
            else:
                #print cmd
                #logging.warning("TEXTCMD '%s' %s -> %s"%(cmd,src,dest))
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(f=self.commands.onMsg,jid=src,text=cmd,v_id=v_id)
                    cb=lambda (x):self.sendMessage(dest,src,x)
                    d.addCallback(cb)
                    d.addErrback(self.errorback)
                else:
                    self.sendMessage(dest,src,self.commands.onMsg(jid=src,text=cmd,v_id=v_id))
            return

        if (body[0:1]=="#" and bjid in self.admins and dest==self.jid):
            req=msg.find('{urn:xmpp:receipts}request')
            if (req!=None):
                self.msgDeliveryNotify(0,msg_id=msgid,jid=src,v_id=0,receipt=1)
                # admin commands
            cmd=body[1:]

            logging.warning("admin command: '%s'"%cmd)
            resp=self.adminCmd(cmd)
            if (type(resp)==unicode):
                pass
                #resp=resp.encode('utf-8')
            else:
                resp=str(resp)
            self.sendMessage(self.jid,src,resp)
            return
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
            #elif (cmd[:7]=='traffic'):
                #try:
                    #self.sendMessage(self.jid,msg["from"],"Traffic: %s"%repr(self.logger.getTraffic(int(cmd[7:]))))
                #except:
                    #print_exc()

            #else:
                #self.sendMessage(self.jid,src,"unknown command: '%s'"%cmd)
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
            if (s):
                body = body + u"\n--------\n" + s
            d=self.users[bjid].pool.defer(f=self.users[bjid].vclient.sendMessage,to_id=v_id,body=body,title=title)
            req=msg.find('{urn:xmpp:receipts}request')
            if (req!=None):
                d.addCallback(self.msgDeliveryNotify,msg_id=msgid,jid=src,v_id=v_id,receipt=1,body=body,subject=title)
            else:
                d.addCallback(self.msgDeliveryNotify,msg_id=msgid,jid=src,v_id=v_id,body=body,subject=title)
            d.addErrback(self.errorback)
        if src==self.jid and body[:4]=='ping':
            self.latency=time.time()-float(body[4:])
            if (self.latency>600):
                logging.error("critical overload. disabling updates.")
                self.pollMgr.updateInterval=300
            elif (self.latency>180):
                logging.warning("performance troubles. increasing update interval.")
                self.pollMgr.updateInterval=30
            #else:
                #self.pollMgr.updateInterval=15
         
    def adminCmd(self,cmd):
        if (cmd[:4]=="stop"):
            self.isActive=0
            if (cmd=="stop"):
                self.stopService(suspend=True)
            else:
                self.stopService(suspend=True,msg=cmd[5:])
            return "'%s' done"%cmd
        elif (cmd=="start"):
            self.isActive=1
        elif (cmd=="sendprobes"):
            self.sendProbes(src)
        elif (cmd=="collect"):
            gc.collect()
        elif (cmd[:4]=="eval"):
            try:
                res=repr(eval(cmd[5:]))
                logging.warning("eval: "+repr(res))
                return '#eval: %s'%repr(res)
            except Exception,e:
                logging.error("exec failed"+format_exc())
                return '#eval: exception:\n%s'%str(e)
        elif (cmd[:4]=="exec"):
            try:
                execfile("inject.py")
                return 'Ok'
            except:
                logging.exception("exec failed")
            return 'fail'
        elif (cmd=='savestate'):
            try:
                self.saveState()
                return 'state saved'
            except:
                logging.exception('')

        elif (cmd=='restorestate'):
            try:
                self.restoreState()
                return 'state restored'
            except:
                logging.exception('')
        elif (cmd=="users"):
            count = 0
            ret = u''
            for i in self.users.keys():
                if (self.hasUser(i)):
                    ret=ret+u"\nxmpp:%s"%(i)
                    count+=1
            return "%s user(s) online"%count + ret
        elif (cmd=="stats"):
            #TODO async request
            return self.getStatsMessage()

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
            return True
        #elif (cmd[:7]=='traffic'):
            #try:
                #self.sendMessage(self.jid,msg["from"],"Traffic: %s"%repr(self.logger.getTraffic(int(cmd[7:]))))
            #except:
                #print_exc()

        else:
            return "unknown command: '%s'"%cmd
        return 'something wrong'
    def startPoll(self):
        self.pollMgr.start()
    def msgDeliveryNotify(self,res,msg_id,jid,v_id,receipt=0,body=None,subject=None):
        """
        Send delivery notification if message successfully sent
        use receipt flag if needed to send receipt
        """
        #logging.warning('receipt: res=%s'%res)
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
        if res == 0:
            if (receipt):
                addChild(msg,'received','urn:xmpp:receipts')
            else:
                #logging.warning('disabled')
                return
            #msg.addElement("received",'urn:xmpp:receipts')
        #elif res == 0:
            #return #no reciepts needed and no errors
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
        #logging.warning('receipt sent')
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
            return
        bjid=gen.bareJid(src)
        ans=createElement('iq',attrs={'from':dest,'to':src, 'id':iq.get('id'),'type':'result'})
        #logging.warning(iq.get('type'))
        logging.info("RECV: iq (%s) %s -> %s"%(iq.get('type'),src,dest))
        if (iq.get('type')=='error'):
            return False
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
                        cname=u'%s %s'%(self.users[bjid].onlineList[gen.jidToId(dest)]["first"],self.users[bjid].onlineList[gen.jidToId(dest)]["last"])                        
                        SubElement(a,'identity',category='pubsub',type='pep', name=cname)
                        #addChild(a,'identity',attrs={'category':'pubsub','type':'pep'})
                        features=[
                            "jabber:iq:version",
                            'http://jabber.org/protocol/commands',
                            "urn:xmpp:receipts"
                            ]
                    for i in features:
                        SubElement(a,'feature',var=i)
                elif (node=='friendsonline'):
                    addChild(a,'identity',attrs={"name":u'Друзья в сети',"category":"automation","type":"command-list"})
                elif (node=="http://jabber.org/protocol/commands" or node[:4]=='cmd:'):
                    self.send(self.commands.onDiscoInfo(iq))
                    return True
                else:
                    if (node):
                        ans.set('node', node)
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
                                #addChild(a,"item",attrs={"node":"http://jabber.org/protocol/commands",'name':cname,'jid':"%s@%s"%(i,self.jid)})
                                addChild(a,"item",attrs={"node":"",'name':cname,'jid':"%s@%s"%(i,self.jid)})
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
                        'users/online':('users',str(len(self.users))),
                        'bandwith/packets-in':('packets', str(self.stanzasIn)),
                        'bandwith/packets-out':('packets', str(self.stanzasOut))
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
                    values=['time/uptime','users/online','bandwith/packets-in','bandwith/packets-out']
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
                            
                            with open("avatar.png") as req:
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
                        os.unlink("%s/%s/%s_json"%(self.datadir,bjid[:1],bjid))
                    except OSError:
                        pass
                    return
                if (r.find("{jabber:iq:register}remove")!=None):
                    logging.warning ("FIXME namespace in register/remove")
                    try:
                        os.unlink("%s/%s/%s_json"%(self.datadir,bjid[:1],bjid))
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
                    #u.config={}
                    pass
                u.email=email
                u.password=pw
                u.cookies=[]
                u.blocked=False
                u.instanceReady=True
                u.saveData()
                #try:
                    #os.unlink("%s/%s"%(self.cookPath,bjid))
                #except OSError:
                    #pass
                ans=createElement("iq",{'type':'result','to':src,'from':dest,'id':iq.get('id')})
                self.send(ans)
                self.sendPresence(self.jid,src,"subscribe")
                self.sendPresence(self.jid,src,"subscribed")
                self.sendMessage(self.jid,src,u".getroster для получения списка\n.login для подключения\nТех.поддержка в конференции: pyvk-t@conference.jabber.ru")
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
                if (self.hasUser(bjid)):
                    d=self.users[bjid].pool.defer(f=self.commands.onIqSet,iq=iq)
                    d.addCallback(self.send)
                    return True
                else:
                    self.send(self.commands.onIqSet(iq))
                    return True
        if (iq.find('{urn:xmpp:time}time')!=None):
            pass
        elif(iq.find('{http://jabber.org/protocol/pubsub}pubsub')!=None):
            pass
        else:
            if (len(iq)):
                if ('error' in iq[0].tag):
                    for i in iq[0]:
                        nsl=i.tag.find('}')
                        tagname=i.tag[nsl+1:]
                        logging.warning ("error stanza '%s' %s -> %s"%(tagname, src,dest))
                    return
                else:
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

    def getStatsMessage(self):
        ret="users online: %s\nuptime: %s\nactive threads: %s"%(len(self.users),int(time.time()-self.startTime),len(threading.enumerate()))
        return ret

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

    def sendProbe(self,bjid):
        u=user(self,bjid,noLoop=True)
        u.readData()
        fr=u.roster.keys()[0]
        del u
        #logging.warning('sending probe to %s'%bjid)
        self.sendPresence(src=fr,dest=bjid,t='probe')
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
            return
        card=self.users[bjid].vclient.getVcard(v_id, self.show_avatars)
        if (not card):
            logging.warning('can\'t get vcard: id%s -> %s'%(v_id,jid))
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
                #logging.warning('state=4')
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
        #logging.warning('acq')

        if (not self.usrLock.acquire(False)):
            #logging.warning('abrt')
            return
        #logging.warning('acq\'d')
        try:
            try:
                u=self.users[bjid]
            except KeyError:
            #if (not self.users.has_key(bjid)):
                #print "creating user %s"
                self.users[bjid]=user(self,jid,captcha_key=captcha_key)
                u=self.users[bjid]
        except Exception,e:
            if (type(e)==gen.QuietError):
                logging.error('QuietError (%s): %s'%(bjid,e))
            else:
                logging.exception('')
            self.usrLock.release()
            self.sendPresence(self.jid,bjid,'unavailable',status='Internal error. Please, try again later.')
            return
        self.usrLock.release()
        #logging.warning('released')
        u.pool.call(u.addResource,jid=jid,prs=prs)
    def checkZombie(self,bjid):
        try:
            u=self.users[bjid]
        except KeyError:
            return False
        if (u.state==1 and u.loginTime-time.time()>600):
            logging.warning('%s: zombie detected! invoking logout() from main pool'%bjid)
            user.logout()
            logging.warning('%s: zombie defeated!'%bjid)
            return True
        return False
    def delResource(self,jid, to=None,dbg=False):
        bjid=gen.bareJid(jid)
        #if (dbg):
            #logging.warning('start')
        #if (self.checkZombie(bjid)):
            #return
        try:
            user=self.users[bjid]
        except KeyError:
            return            
        if (to==self.jid):
            try:
                user.pool.call(user.logout)
            except:
                logging.exception('')
            return

        #try:
        
        user.pool.call(user.delResource,jid=jid)

    def onPresence(self, prs, dbg):
        """
        Act on the presence stanza that has just been received.
        """
        ptype=prs.get("type")
        if (dbg):
            #logging.warning('start (%s)'%ptype)
            if (ptype=='unavailable'):
                logging.warning(repr(tostring(prs)))
        src=prs.get("from")
        dest=prs.get("to")
        #logging.info("RECV: prs %s -> %s type=%s"%(src,dest,ptype))
        bjid=gen.bareJid(src)
        if(ptype):
            if ptype=="unavailable" and self.hasUser(bjid) and (dest==self.jid or self.users[bjid].subscribed(dest) or not self.roster_management):
                #if (dbg):
                    #logging.warning('delres')
                self.delResource(src,dest,dbg=dbg)
                self.sendPresence(dest,src,t='unavailable')
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
            #if (dbg):
                #logging.warning('done')
            return
        if (self.isActive or bjid==self.admin):
            self.addResource(src,prs)

    def updateFeed(self,jid,feed):
        #FIXME bjid?
        ret=""
        if (not self.hasUser(gen.bareJid(jid))):
            return
        user=self.users[jid]
        for k in feed.keys():
            if (k in gen.feedInfo) and ("count" in feed[k]) and feed[k]["count"]:
                ret=ret+u"Новых %s - %s\n"%(gen.feedInfo[k]["message"],feed[k]["count"])
        ret = ret.strip()
        s=conf.get('features/status')
        if (s):
            ret=ret+'\n{%s}'%s
        if ret!=self.users[jid].status:
            user.status = ret
            self.sendPresence(self.jid,jid,status=ret)
        ret=""
        try:
            if (feed["messages"]["count"]) and feed["messages"]["items"]:
                idlist=[int (i) for i in feed ["messages"]["items"].keys()]
                inmsgs=user.vclient.getInboxMessages(num=100)
                #for i in inmsgs['messages']: print i
                in_idlist=[int(i['id']) for i in inmsgs['messages']]
                ml=[i for i in inmsgs['messages'] if int(i['id']) in idlist]
                for i in ml:
                    if (len(i['text'])>160):
                        # запрашиваем заново, т.к. юзерапи режет сообщения до 192(?) символов
                        umsgs=user.vclient.getInboxMessages(num=10, v_id=i['from'])
                        msgtext=i['text']
                        for j in umsgs['messages']:
                            if j['id']==i['id']:
                                msgtext=j['text']
                                break
                        if (msgtext!=i['text']):
                            logging.warning('long message fixed. length: %s -> %s'%(len(i['text']),len(msgtext)))
                            i['text']=msgtext
                        else:
                            logging.warning('long message not fixed. length: %s'%(len(i['text'])))
                    self.sendMessage(src='%s@%s'%(i['from'],self.jid), dest=jid, body=i['text'])
                    #logging.warning ('%s sent'%i)
                    print 'http://vkontakte.ru/mail.php?id=4475'
                    url='http://m.vkontakte.ru/letter%s?'%i['id']
                    print url
                    user.vclient.getHttpPage(url)

                    #_t=user.vclient.getHttpPage('http://vkontakte.ru/mail.php?act=show&id=%s'%i['id'],referer='Referer=http://vkontakte.ru/mail.php?id=%s'%user.v_id)
        except KeyError:
            logging.exception('')
            #print_exc()
            pass
        except:
            logging.warning("bad feed\n"+repr(feed)+"\nexception: "+format_exc())
        oldfeed = self.users[jid].feed
        if feed != self.users[jid].feed and ((oldfeed and self.users[jid].getConfig("feed_notify")) or (not oldfeed and self.users[jid].getConfig("start_feed_notify"))):
            for j in gen.feedInfo:
                if j!="friends" and j in feed and "items" in feed[j] and feed[j]['items']:
                    gr=""
                    gc=0
                    for i in feed[j]["items"]:
                        try:
                            if (i in oldfeed[j]['items']):
                                continue
                        except (KeyError, TypeError):
                            pass
                        #if not (oldfeed and (j in oldfeed) and ("items" in oldfeed[j]) and (i in oldfeed[j]["items"])):
                            #it is a vkontakte.ru bug, when it stores null inside items. (e.g when there are invitaions to deleted groups)
                        if gen.feedInfo[j]["url"] and feed[j]["items"]!="null":
                            try:
                                gr+="\n  "+gen.unescape(feed[j]["items"][i])+" [ "+gen.feedInfo[j]["url"]%i + " ]"
                            except TypeError:
                                logging.exception('')
                                #print_exc()
                                #print repr(feed)
                                #print 'j:',j,'i:',i
                                #try:
                                    #print 'feed[j]\n',repr(feed[j])
                                #except:
                                    #pass
                        gc+=1
                    if gc:
                        if gen.feedInfo[j]["url"]:
                            ret+=u"Новых %s - %s:%s\n"%(gen.feedInfo[j]["message"],gc,gr)
                        else:
                            ret+=u"Новых %s - %s\n"%(gen.feedInfo[j]["message"],gc)
            if ret:
                self.sendMessage(self.jid,jid,ret.strip())
            #try:
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
            #except:
                #logging.warning("bad feed\n"+repr(feed)+"\nexception: "+format_exc())
                
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
        ulist=self.users.keys()
        for u in ulist:
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
        ulist=self.users.keys()
        for i in ulist:
            try:
                d=self.users[i].pool.defer(self.users[i].logout)
                dl.append(d)
            except:
                logging.exception('')
            #except AttributeError, gen.QuietError:
                #pass
        print "%s logout()'s pending.. now we will wait..'"%len(dl)
        time.sleep(5)
        for i in range(10):
            names=[j.name for j in threading.enumerate()]
            pools=[j for j in names if 'pool' in j]
            if (len(pools)==0):
                break
            logging.warning('waiting for pools (%s)'%len(pools))
            if (len(pools)<5):
                logging.warning(str(pools))
            time.sleep(5)
        #print "done\ndeleting user objects"
        for i in self.users.keys():
            try:
                del self.users[i]
            except:
                pass
        if (len(threading.enumerate())):
            logging.warning('alive threads\n%s'%('\n'.join([str(i) for i in threading.enumerate()])))
            #print threading.enumerate()
        else:
            print "done"
        return None

    def sendMessage(self,src,dest,body,title=None,sepThread=False,mtime=None):
        msg=createElement("message",{'to':dest,'from':src,'type':'chat','id':"msg%s"%(int(time.time())%10000)})
        if type(mtime)==int:
            SubElement(msg,"delay",{"xmlns":"urn:xmpp:delay","stamp":datetime.fromtimestamp(mtime).isoformat()})
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
                logging.warning('bad status: %.80s'%repr(status))
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
            logging.warning('stopping service')
            self.stopService(suspend=True)
            #self.alive=False
        elif (sig==signal.SIGUSR2):
            logging.error('got SIGUSR2. executing hook...')
            try:
                execfile("inject.py")
            except:
                logging.error("exec failed"+format_exc())
        #elif (sig==signal.SUGHUP):
            #logging.error ('caught SIGHUP. reloading config...')
            #logging.

    def kbInterrupt(self):
        print "threads:"
        for i in threading.enumerate():
            pass
            #print '    %s (%s)'%(i.name,i.daemon)
        return True
    def saveState(self):
        fn='%s/%s'%(conf.get ('storage','datadir'),'state.json')
        olist=self.users.keys()
        ret={'version':'0.1'}
        ret['users_online']=olist
        j=demjson.JSON(compactly=False)
        with open(fn,'w') as cfile:
            cfile.write(j.encode(ret).encode('utf-8'))
    def restoreState(self):
        fn='%s/%s'%(conf.get ('storage','datadir'),'state.json')
        with open(fn,'r') as cfile:
            f=cfile.read()
        j=demjson.JSON(compactly=False)
        data=j.decode(f.decode('utf-8'))
        if data['version']=='0.1':
            probeCnt=0
            probeTotal=len(data['users_online'])
            for i in data['users_online']:
                probeCnt+=1
                try:
                    logging.warning('autoreconnect: [%s/%s]sending probe to %s'%(probeCnt,probeTotal,i))
                    self.sendProbe(i)
                except:
                    logging.exception('')
    def userStack(self,bjid):
        
        try:
            fr=sys._current_frames()[self.users[bjid].pool._thread.ident]
            ret=(''.join(traceback.format_stack(fr)))
            #logging.warning(ret)
            return ret
        except:
            logging.exception('')


 
        

