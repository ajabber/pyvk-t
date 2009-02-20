# -*- coding: utf-8 -*-
from  pyxmpp.jabberd.component import Component
import pyxmpp
import sys
import logging
from pyxmpp.all import JID,Iq,Presence,Message,StreamError
from pyvk_t_db import pyvk_t_db
from libvkontakte import *
import ConfigParser
class transp (Component,vkonClient):
    db=pyvk_t_db()
    test=""
    threads={}
    def __init__(self, jid=None, secret=None, server=None, port=5347, disco_name=u'PyXMPP based component', disco_category=u'x-service', disco_type=u'x-unknown', keepalive=0):
        Component.__init__(self, jid, secret, server, port, disco_name, disco_category, disco_type, keepalive)
        self.disco_info.add_feature("jabber:iq:register")
        self.disco_info.add_feature("jabber:iq:gateway")
#        self.disco_info.add_feature("http://jabber.org/protocol/commands")
        
    def idle(self,stream):
        stream=self.get_stream() 
        if stream: 
            stream.idle() 
    def getRegister(self, iq):
        print "wtf?? register attempt?"
        to=iq.get_to()
        if to and to!=self.jid:
            raise FeatureNotImplementedProtocolError, "Tried to register at non-null node"
        iq=iq.make_result_response()
        q=iq.new_query("jabber:iq:register")
        q.newTextChild(q.ns(),"instructions","Введи свое мыло и пароль на вконтакте.ру.")
        q.newChild(q.ns(),"email",None)
        q.newChild(q.ns(),"password",None)
        self.stream.send(iq)
        return True
    def setRegister(self,iq):
        to=iq.get_to()
        if to and to!=self.jid:
            raise FeatureNotImplementedProtocolError, "Tried to register at non-null node"
        remove=iq.xpath_eval("r:query/r:remove",{"r":"jabber:iq:register"})
        if remove:
            m=Message(from_jid=iq.get_to(),to_jid=iq.get_from(),stanza_type="chat",
                    body=u"Unregistered")
            self.stream.send(m)
            p=Presence(from_jid=iq.get_to(),to_jid=iq.get_from(),stanza_type="unsubscribe")
            self.stream.send(p)
            p=Presence(from_jid=iq.get_to(),to_jid=iq.get_from(),stanza_type="unsubscribed")
            self.stream.send(p)
            return True
        username=iq.xpath_eval("r:query/r:email",{"r":"jabber:iq:register"})
        if username:
            username=username[0].getContent()
        else:
            username=u""
        password=iq.xpath_eval("r:query/r:password",{"r":"jabber:iq:register"})
        if password:
            password=password[0].getContent()
        else:
            password=u""
        self.db.addUser(iq.get_from().bare().as_unicode(),username,password)
        self.db.sync()
        m=Message(from_jid=iq.get_to(),to_jid=iq.get_from(),stanza_type="chat",body=u"Регистрация произведена.")
        self.stream.send(m)
        p=Presence(from_jid=iq.get_to(),to_jid=iq.get_from(),stanza_type="subscribe")
        self.stream.send(p)
        iq=iq.make_result_response()
        self.stream.send(iq)
        return True
    def presence(self,stanza):
        jid=stanza.get_from().bare()
        ud=self.db.userData(jid.as_unicode())
        #FIXME use pyxmpp's jid instead of unicode string
        if (ud):
            print repr(stanza.get_type())
            if (stanza.get_type()==u"unavailable"):
                p=Presence(stanza_type=u"unavailable" ,to_jid=stanza.get_from(), from_jid=self.jid, show=stanza.get_show());
                self.stream.send(p)
                if (self.threads.has_key(jid)):
                    print "killing thread"
                    self.threads[jid].exit()
                    del self.threads[jid]
            else:
                
                if (stanza.get_type()==u"probe"):
                    pass
                    #self.startSession(jid,1)
                else:
                    p=Presence(stanza_type=u"available" ,to_jid=stanza.get_from(), from_jid=self.jid, show=stanza.get_show());
                    self.stream.send(p)
                    
                    self.startSession(jid,0)
                
        return True
    def usersOffline(self,jid,users):
        for u in users:
            tjid=pyxmpp.jid.JID.__new__(pyxmpp.jid.JID,domain=self.jid.domain,node_or_jid=str(u))
            p=Presence(
            stanza_type="unavailable",
            to_jid=jid,
            from_jid=tjid,
            status="http://vkontakte.ru/id%s"%u
            );
            self.stream.send(p)
        return True
    def usersOnline(self,jid,users):
        for u in users:
            tjid=pyxmpp.jid.JID.__new__(pyxmpp.jid.JID,domain=self.jid.domain,node_or_jid=str(u))
            p=Presence(
                stanza_type=None,
                to_jid=jid,
                from_jid=tjid
            );
            self.stream.send(p)
        return True
    def presenceControl(self,stanza):
        """Handle subscription control <presence/> stanzas -- acknowledge
        them."""
        p=stanza.make_accept_response()
        self.stream.send(p)
        return True
    def msgHandler(self,msg):
        txt=msg.get_body()
        jid=msg.get_from().bare()
        to_jid=msg.get_to()
        ud=self.db.userData(jid.as_unicode())
        if (ud):
            if (to_jid!=self.jid):
                if (self.threads.has_key(jid)):
                    if (self.threads[jid].sendMessage(to_id=to_jid.node,body=txt,title="[sent by pyvk-t]")==0):
                        m=Message(
                            from_jid=self.jid,
                            to_jid=jid,
                            stanza_type="chat",
                            body=u"Ошибка отправки сообщения. Скорее всего, вконтакт потребовал капчу. Попробуй убрать ссылки из сообщения."
                        )
                        self.stream.send(m)
                        

            if (txt=="get roster"):
                m=Message(
                    from_jid=self.jid,
                    to_jid=jid,
                    stanza_type="chat",
                    body=u"""Запрос списка друзей сопровождается большим количеством запросов авторизации.
Рекомендуется временно включить автоматическую авторизацию в клиенте.
Для подтверждения отправь 'get roster confirm'"""
                );
                self.stream.send(m)
            elif (txt=="get roster confirm"):
                if (self.threads.has_key(jid)):
                    rost=self.threads[jid].getFriendList()
                    m=Message(
                    from_jid=self.jid,
                    to_jid=jid,
                    stanza_type="chat",
                    body=u"Получаю список друзей... это может занять некоторое время..."
                    );
                    self.stream.send(m)
                    for i in rost:
                        newJid=pyxmpp.jid.JID.__new__(pyxmpp.jid.JID,node_or_jid="%s"%i,domain=self.jid.domain)
                        print repr(newJid)
                        p=Presence(from_jid=newJid,to_jid=msg.get_from(),stanza_type="subscribe")
                        self.stream.send(p)
                        p=Presence(from_jid=newJid,to_jid=msg.get_from(),stanza_type="subscribed")
                        self.stream.send(p)
                else:
                    #TODO err message
                    pass
                
            pass
        else:
            m=Message(
            from_jid=self.jid,
            to_jid=jid,
            stanza_type="chat",
            body=u"u r not registered, sorry"
            );
            self.stream.send(m)
            
            
        return True
    def getVcard(self,iq):
        #print "vcard"
        #print repr(iq.get_to())
        jid=iq.get_from().bare()
        if (iq.get_to()!=self.jid):
            if (self.threads.has_key(jid)):
                iq=iq.make_result_response()
                q=iq.new_query("vcard-temp","vCard")
                vc=self.threads[jid].getVcard(int(iq.get_from().node))
                #print vc
                q.newTextChild(q.ns(),"FN",vc["fn"])
                self.stream.send(iq)
        pass
    def startSession(self,jid,feedOnly=1):
        ud=self.db.userData(jid.as_unicode())
        if (ud):
            pass
        else:
            return 0
        if (self.threads.has_key(jid)):
            self.threads[jid].feedOnly=feedOnly
        else:
            p=Presence(
                stanza_type=None,
                to_jid=jid,
                from_jid=self.jid,
                show="away",
                status="logging in..."
            );
            self.stream.send(p)
            self.threads[jid]=vkonThread(cli=self,jid=jid,email=ud["email"],passw=ud["password"])
            #print "test"
            if (self.threads[jid].error):
                self.threads[jid].exit()
                p=Presence(
                stanza_type="unavailable",
                to_jid=jid,
                from_jid=self.jid,
                status="login error"
                );
                self.stream.send(p)
                return 0
            else:
                self.threads[jid].start()
                self.threads[jid].feedOnly=feedOnly
                return 1
                    
    def setCommand(self,cmd):
        print "set command"
    def getCommand(self,cmd):
        print "get command"
        q=cmd.get_query()
        #print str(q)
        for p in q.properties:
            print "name: ",p.name
            print "val:",p
        #print p
        #print p[0]
        
    def authenticated(self):
        Component.authenticated(self)
        self.stream.set_iq_get_handler("query","jabber:iq:register",self.getRegister)
        self.stream.set_iq_set_handler("query","jabber:iq:register",self.setRegister)
        self.stream.set_message_handler("chat",self.msgHandler,priority=0)
        #self.stream.set_iq_get_handler("query","http://jabber.org/protocol/disco#items",self.getCommand)
        #self.stream.set_iq_set_handler("query","http://jabber.org/protocol/disco#items",self.setCommand)
        self.stream.set_iq_get_handler("vCard","vcard-temp",self.getVcard)
        
        self.stream.set_presence_handler("available",self.presence)
        self.stream.set_presence_handler("probe",self.presence)
        
        self.stream.set_presence_handler("unavailable",self.presence)
        self.stream.set_presence_handler("subscribe",self.presenceControl)
        self.stream.set_presence_handler("unsubscribe",self.presenceControl)
        pass
    def feedChanged(self,jid,feed):
        dat=[]
        dat=feed
        ret=""
        #print jid
        for k in dat.keys():
            if (k!="user" and dat[k]["count"]):
                ret=ret+"new %s: %s\n"%(k,dat[k]["count"])
        if (feed["messages"]["count"] ):
            
            for i in feed ["messages"]["items"].keys():
                if (self.threads[jid].feedOnly):
                    m=Message(from_jid=sejf.jid,to_jid=jid,stanza_type="chat",body="you have new message(s)")
                    self.stream.send(m)
                    pass
                else:
                    msg=self.threads[jid].getMessage(i)
                    tjid=pyxmpp.jid.JID.__new__(pyxmpp.jid.JID,node_or_jid="%s"%msg["from"],domain=self.jid.domain)
                    m=Message(from_jid=tjid,to_jid=jid,stanza_type="chat",body="[%s]\n%s"%(msg["title"],msg['text']))
                    self.stream.send(m)
        if (self.threads[jid].feedOnly):
            ret="[shadow mode]\n%s"%ret
        p=Presence(
            stanza_type=None,
            to_jid=jid,
            from_jid=self.jid,
            status=ret
        );
        self.stream.send(p)
    def threadError(self,jid,message):
        m=Message(
        from_jid=self.jid,
        to_jid=jid,
        stanza_type="chat",
        body=u"Ошибка: %s"%message
        );
        self.stream.send(m)
        if (self.threads.has_key(jid)):
            self.threads[jid].exit()
            p=Presence(
                stanza_type="unavailable",
                to_jid=u,
                from_jid=self.jid,
                status="system error. u can try to reconnect."
            );
            self.stream.send(p)
    def disconnect(self):
        print "logging out..."
        for u in self.threads.keys():
            self.threads[u].exit()
            p=Presence(
                stanza_type="unavailable",
                to_jid=u,
                from_jid=self.jid,
                status="transport shutdown..."
            );
            self.stream.send(p)
        print "done"
        Component.disconnect(self)

logger=logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

config = ConfigParser.ConfigParser()
config.read("pyvk-t.cfg")

jid=pyxmpp.jid.JID.__new__(pyxmpp.jid.JID,domain=config.get("general","transport_jid"))
tr=transp(jid=jid,
    secret=config.get("general","secret"),
    server=config.get("general","server"),
    port=config.getint("general","port"),
    disco_name=config.get("general","disco_name"),keepalive=100)
tr.connect()
try:
    tr.loop(1)
except KeyboardInterrupt:
    print "disconnecting..."
    tr.disconnect()
    pass
    
