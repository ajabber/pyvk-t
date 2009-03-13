# -*- coding: utf-8 -*-

"""
 Example component service.
 
"""
import time
import twisted
from twisted.words.protocols.jabber import jid, xmlstream
from twisted.application import internet, service
from twisted.internet import interfaces, defer, reactor,threads
from twisted.python import log
from twisted.words.xish import domish
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.enterprise import adbapi 
from twisted.enterprise.util import safe 

from twisted.words.protocols.jabber.ijabber import IService
from twisted.words.protocols.jabber import component,xmlstream
from libvkontakte import *
from zope.interface import Interface, implements
import ConfigParser
from twisted.internet import defer
from twisted.python.threadpool import ThreadPool
import sys,os
import pyvkt_commands
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
    
    def transportConnected(self, xmlstream):
        xmlstream.rawDataInFn = self.rawDataIn
        xmlstream.rawDataOutFn = self.rawDataOut

    def rawDataIn(self, buf):
        #log.msg("%s - RECV: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        pass

    def rawDataOut(self, buf):
        #log.msg("%s - SEND: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))
        pass

def bareJid(jid):
    n=jid.find("/")
    if (n==-1):
        return jid
    return jid[:n]
class pyvk_t(component.Service,vkonClient):

    implements(IService)

    def __init__(self):
        config = ConfigParser.ConfigParser()
        confName="pyvk-t_new.cfg"
        if(os.environ.has_key("PYVKT_CONFIG")):
            confName=os.environ["PYVKT_CONFIG"]
        config.read(confName)
        self.dbpool = adbapi.ConnectionPool(
            config.get("database","module"), 
            host=config.get("database","host"), 
            user=config.get("database","user"), 
            passwd=config.get("database","passwd"), 
            db=config.get("database","db"))
            
        if config.has_option("features","avatars"):
            self.show_avatars = config.getboolean("features","avatars")
        else:
            self.show_avatars = 0
        self.threads={}
        self.pools={}
        self.usrconf={}
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
            self.revision="svn rev. %s"%ver
        #self.commands=pyvktCommands(self)
        self.commands=pyvkt_commands.cmdManager(self)
        #except:
            #log.msg("can't ret revision")
            #self.revision="alpha"
        self.isActive=1
        #self.commands=
        # FIXME 
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

    def onMessage(self, msg):
        """
        Act on the message stanza that has just been received.

        """
        if (msg.body):
            body=msg.body.children[0]
            bjid=bareJid(msg["from"])
            if (body[0:1]=="/"):
                cmd=body[1:]
                log.msg(cmd.encode("utf-8"))
                if (cmd=="login"):
                    self.login(bjid)
                elif (self.threads.has_key(bjid) and self.threads[bjid] and cmd=="get roster"):
                    d=defer.execute(self.threads[bjid].getFriendList)
                    d.addCallback(self.sendFriendlist,jid=bjid)
                elif (cmd=="help"):
                    self.sendMessage(self.jid,msg["from"],u"/get roster для получения списка\n/login для подключения")
                else:
                    d=threads.deferToThread(f=self.commands.onMsg,jid=bjid,text=cmd)
                    cb=lambda (x):self.sendMessage(self.jid,msg["from"],x)
                    d.addCallback(cb)
                return

            if (body[0:1]=="#" and bjid==self.admin):
                # admin commands
                cmd=body[1:].decode('utf-8')
                
                log.msg("admin command: '%s'"%cmd)
                if (cmd=="stop"):
                    self.isActive=0
                    self.stopService()
                    self.sendMessage(self.jid,msg["from"],"'%s' done"%cmd)
                elif (cmd=="start"):
                    self.isActive=1
                elif (cmd=="stats"):
                    ret="%s user(s) online"%len(self.threads)
                    for i in self.threads:
                        ret=ret+"\nxmpp:%s"%i
                    self.sendMessage(self.jid,msg["from"],ret)
                elif (cmd[:4]=="wall"):
                    for i in self.threads:
                        self.sendMessage(self.jid,i,"[brodcast message]\n%s"%cmd[5:])
                    self.sendMessage(self.jid,msg["from"],"'%s' done"%cmd)
                else:
                    self.sendMessage(self.jid,msg["from"],"unknown command: '%s'"%cmd)
                return
            if(msg["to"]!=self.jid and self.threads.has_key(bjid)):
                dogpos=msg["to"].find("@")
                try:
                    v_id=int(msg["to"][:dogpos])
                except:
                    log.msg("bad JID: %s"%msg["to"])
                    return
                req=msg.request
                if(req==None):
                    print "legacy message"
                    self.pools[bjid].callInThread(self.submitMessage,jid=bjid,v_id=v_id,body=body,title="[sent by pyvk-t]")
                else:
                    if (req.uri=='urn:xmpp:receipts'):

                        #old versions of twisted does not have deferToThreadPool function
                        if hasattr(threads,"deferToThreadPool"):
                            d=threads.deferToThreadPool(
                                reactor=reactor,
                                threadpool=self.pools[bjid],
                                f=self.threads[bjid].sendMessage,to_id=v_id,body=body,title="[sent by pyvk-t]")
                        else:
                            d=threads.deferToThread(f=self.threads[bjid].sendMessage,to_id=v_id,body=body,title="[sent by pyvk-t]")
                        d.addCallback(self.msgDeliveryNotify,msg_id=msg["id"],jid=msg["from"],v_id=v_id)
                
            #TODO delivery notification
    def msgDeliveryNotify(self,res,msg_id,jid,v_id):
        """
        Send delivery notification if message successfully sent
        """
        msg=domish.Element((None,"message"))
        try:
            msg["to"]=jid.decode("utf-8")
        except:
            msg["to"]=jid
        msg["from"]="%s@%s"%(v_id,self.jid)
        msg["id"]=msg_id
        if res == 0:
            msg.addElement("received",'urn:xmpp:receipts')
        elif res == 2:
            err = msg.addElement("error")
            err.attributes["type"]="wait"
            err.attributes["code"]="400"
            err.addElement("unexpected-request","urn:ietf:params:xml:ns:xmpp-stanzas")
            err.addElement("too-many-stanzas","urn:xmpp:errors")
        else:
            err = msg.addElement("error")
            err.attributes["type"]="cancel"
            err.attributes["code"]="500"
            err.addElement("undefined-condition","urn:ietf:params:xml:ns:xmpp-stanzas")
        self.xmlstream.send(msg)

    def onIq(self, iq):
        """
        Act on the iq stanza that has just been received.
        """
        #log.msg(iq["type"])
        #log.msg(iq.firstChildElement().toXml().encode("utf-8"))
        bjid=bareJid(iq["from"])
        if (iq["type"]=="get"):
            query=iq.query
            if (query):
                ans=xmlstream.IQ(self.xmlstream,"result")
                ans["to"]=iq["from"]
                ans["from"]=iq["to"]
                ans["id"]=iq["id"]
                q=ans.addElement("query",query.uri)
                if (query.uri=="http://jabber.org/protocol/disco#info"):
                    if (query.hasAttribute("node")):
                        self.xmlstream.send(self.commands.onDiscoInfo(iq))
                        return
                    else:
                        if (iq["to"]==self.jid):
                            q.addElement("identity").attributes={"category":"gateway","type":"vkontakte.ru","name":"Vkontakte.ru transport [twisted]"}
                            q.addElement("feature")["var"]="jabber:iq:register"
                            q.addElement("feature")["var"]="jabber:iq:gateway"
                            q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
                            #q.addElement("feature")["var"]="stringprep"
                            q.addElement("feature")["var"]="urn:xmpp:receipts"
                            
                        else:
                            q.addElement("identity").attributes={"category":"pubsub","type":"pep"}
                            #q.addElement("feature")["var"]="stringprep"
                            q.addElement("feature")["var"]="urn:xmpp:receipts"
                        ans.send()
                        return
                elif (query.uri=="http://jabber.org/protocol/disco#items"):
                    if (query.hasAttribute("node")):
                        q["node"]=query["node"]
                        if (query["node"]=="http://jabber.org/protocol/commands"):
                            self.xmlstream.send(self.commands.onDiscoItems(iq))
                            return
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:register"):
                    q.addElement("instructions").addContent(u"Введите email и пароль, используемые на vkontakte.ru")
                    q.addElement("email")
                    q.addElement("password")
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:version"):
                    q.addElement("name").addContent("pyvk-t [twisted]")
                    q.addElement("version").addContent(self.revision)
                    ans.send()
                    return
                elif (query.uri=="jabber:iq:gateway"):
                    q.addElement("desc").addContent(u"Пожалуйста, введите id ползователя на сайте вконтакте.ру.\nУзнать, какой ID у пользователя Вконтакте можно, например, так:\nЗайдите на его страницу. В адресной строке будет http://vkontakte.ru/profile.php?id=0000000\nЗначит его ID - 0000000")
                    q.addElement("prompt").addContent("Vkontakte ID")
                    ans.send()
                    return
                    
            vcard=iq.vCard
            if (vcard):
                #log.msg("vcard request")
                log.msg("vcard legacy")
                dogpos=iq["to"].find("@")
                if(dogpos!=-1):
                    try:
                        v_id=int(iq["to"][:dogpos])
                    except:
                        log.msg("bad JID: %s"%iq["to"])
                        pass
                    else:
                        #log.msg("id: %s"%v_id)
                        if (self.pools.has_key(bjid)):
                            time.sleep(1)
                            self.pools[bjid].callInThread(self.getsendVcard,jid=iq["from"],v_id=v_id,iq_id=iq["id"])
                            return
                        else:
                            log.msg("thread not found!")
                else:
                    ans=xmlstream.IQ(self.xmlstream,"result")
                    ans["to"]=iq["from"]
                    ans["from"]=iq["to"]
                    ans["id"]=iq["id"]
                    q=ans.addElement("vCard","vcard-temp")
                    q.addElement("FN").addContent("vkontakte.ru transport")
                    q.addElement("URL").addContent("http://pyvk-t.googlecode.com")
                    q.addElement("DESC").addContent("Vkontakte.ru jabber transport\nVersion: %s"%self.revision)
                    ans.send()
                    return
                    
        if (iq["type"]=="set"):
            query=iq.query
            if (query):
                if (query.uri=="jabber:iq:register"):
                    if (query.remove):
                        qq=self.dbpool.runQuery("DELETE FROM users WHERE jid='%s'"%safe(bareJid(iq["from"])))
                        return
                    log.msg("from %s"%bareJid(iq["from"]))
                    log.msg(query.toXml())
                    email=""
                    pw=""
                    for i in filter(lambda x:type(x)==twisted.words.xish.domish.Element,query.children):
                        log.msg(i)
                        if (i.name=="email"):
                            email=i.children[0]
                        if (i.name=="password"):
                            pw=i.children[0]
                    qq=self.dbpool.runQuery("DELETE FROM users WHERE jid='%s';INSERT INTO users (jid,email,pass) VALUES ('%s','%s','%s')"%
                        (safe(bareJid(iq["from"])),safe(bareJid(iq["from"])),safe(email),safe(pw)))
                    qq.addCallback(self.register2,jid=iq["from"],iq_id=iq["id"],success=1)
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
            cmd=iq.command
            if (cmd):
                d=threads.deferToThread(f=self.commands.onIqSet,iq=iq)
                d.addCallback(self.xmlstream.send)
                return
        iq = create_reply(iq)
        iq["type"]="error"
        err=iq.addElement("error")
        err["type"]="cancel"
        err.addElement("feature-not-implemented","urn:ietf:params:xml:ns:xmpp-stanzas")
        #print iq
        self.xmlstream.send(iq)
    def register2(self,qres,jid,iq_id,success):
        #FIXME failed registration
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]=self.jid
        ans["id"]=iq_id
        ans.send()
        pr=domish.Element(('',"presence"))
        pr["type"]="subscribe"
        pr["to"]=jid
        pr["from"]=self.jid
        self.xmlstream.send(pr)
        pr=domish.Element(('',"presence"))
        pr["type"]="subscribed"
        pr["to"]=jid
        pr["from"]=self.jid
        self.xmlstream.send(pr)
        self.sendMessage(self.jid,jid,u"/get roster для получения списка\n/login дла подключения")
    def login(self,jid):
        # TODO bare jid?
        if (self.isActive==0 and bareJid(jid)!=self.admin):
            log.msg("isActive==0, login attempt aborted")
            self.sendMessage(self.jid,jid,u"В настоящий момент транспорт неактивен, попробуйте подключиться позже")
            return
        if (self.threads.has_key(jid)):
            return
        self.threads[jid]=0
        mq="SELECT * FROM users WHERE jid='%s'"%safe(bareJid(jid))
        #log.msg(mq)
        q=self.dbpool.runQuery(mq)
        q.addCallback(self.login1)
        pass
    def login1(self,data):
        t=data[0]
        defer.execute(self.createThread,jid=data[0][0],email=data[0][1],pw=data[0][2])
        try:
            self.usrconf[t[0]]=t[3]
        except:
            log.msg("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
            self.usrconf[t[0]]=None
        self.sendPresence(self.jid,data[0][0])
    def loginFailed(self,data,jid):
        msg.log("login failed for %s"%jid)
        del self.threads[jid]
    def createThread(self,jid,email,pw):
        self.threads[jid]=vkonThread(cli=self,jid=jid,email=email,passw=pw)
        self.pools[jid]=ThreadPool(1,1)
        self.pools[jid].start()
        #log.msg("%s,%s,%s"%(jid,email,pw))
        #log.msg(self.threads)
        self.threads[jid].start()
        self.threads[jid].feedOnly=0
    #def usersOnline(self,jid,users):
        #log.msg(users)
    def sendFriendlist(self,fl,jid):
        #log.msg("fiendlist ",jid)
        #log.msg(fl)
        for f in fl:
            src="%s@%s"%(f,self.jid)
            log.msg(src)
            #self.sendPresence(src,jid,"subscribed")
            self.sendPresence(src,jid,"subscribe")
            #return
        return
    def getsendVcard(self,jid,v_id,iq_id):
        #log.msg(jid)
        #log.msg(v_id)
        bjid=bareJid(jid)
        try:
            card=self.threads[bjid].getVcard(v_id, self.show_avatars)
        except:
            log.msg("some fcky error")
            card = None

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
            for x in (u"Деятельность:",
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
            if card.has_key(u'PHOTO') and self.show_avatars:
                photo=vc.addElement(u"PHOTO")
                photo.addElement("TYPE").addContent("image/jpeg")
                photo.addElement("BINVAL").addContent(card[u"PHOTO"].replace("\n",""))
            #adress
            if card.has_key(u'Город:'):
                vc.addElement(u"ADR").addElement("LOCALITY").addContent(card[u"Город:"])
        else:
            vc.addElement("DESC").addContent("http://vkontakte.ru/id%s"%v_id)
        ans.send()
            #log.msg(ans.toXml())

    def requestMessage(self,jid,msgid):
        msg=self.threads[jid].getMessage(msgid)
        #log.msg(msg)
        self.sendMessage("%s@%s"%(msg["from"],self.jid),jid,msg["text"])

    def submitMessage(self,jid,v_id,body,title):
        #log.msg((jid,v_id,body,title))
        try:
            self.threads[jid].sendMessage(to_id=v_id,body=body,title=title)
        except:
            print "submit failed"

    def onPresence(self, prs):
        """
        Act on the presence stanza that has just been received.
        """
        jid=bareJid(prs["from"])
        if(prs.hasAttribute("type")):
            if (prs["type"]=="unavailable"):
                try:
                    self.threads[jid].exit()
                    del self.threads[jid]
                    self.pools[jid].stop()
                    del self.pools[jid]
                except:
                    log.msg("logout fail")
                    pass
                #FIXME
                pr=domish.Element(('',"presence"))
                pr["type"]="unavailable"
                pr["to"]=jid
                pr["from"]=self.jid
                self.xmlstream.send(pr)
            elif(prs["type"]=="subscribe"):
                self.sendPresence(prs["to"],prs["from"],"subscribed")
            return
        if (prs["to"]==self.jid):
            self.login(bareJid(prs["from"]))
        
        #pr=domish.Element(('',"presence"))
        #pr["to"]=jid
        #pr["from"]=self.jid
        #self.xmlstream.send(pr)
    def feedChanged(self,jid,feed):
        ret=""
        for k in feed.keys():
            if (k!="user" and feed[k]["count"]):
                ret=ret+"new %s: %s\n"%(k,feed[k]["count"])
        try:
            if (feed["messages"]["count"] ):
                for i in feed ["messages"]["items"].keys():
                    self.pools[jid].callInThread(self.requestMessage,jid=jid,msgid=i)
            #if (feed["groups"]["count"]):
                #for i in feed["groups"]["items"]:
                    #ret=ret+"\n"+feed["groups"]["items"][i]+" [http://vkontakte.ru/club%s]"%i
        except:
            log.msg("feed error")
        self.sendPresence(self.jid,jid,status=ret)
    def usersOnline(self,jid,users):
        for i in users:
            self.sendPresence("%s@%s"%(i,self.jid),jid)
    def usersOffline(self,jid,users):
        for i in users:
            self.sendPresence("%s@%s"%(i,self.jid),jid,t="unavailable")
    def threadError(self,jid,err):
        if (err=="banned"):
            self.sendMessage(self.jid,jid,"Слишком много запросов однотипных страниц.\nКонтакт частично заблокировал доступ на 10-15 минут. На всякий случай, транспорт отключается")
        elif(err=="auth"):
            self.sendMessage(self.jid,jid,"Ошибка входа. Возможно, неправильный логин/пароль.")
        try:
            self.threads[jid].exit()
            del self.threads[jid]
            self.pools[jid].stop()
            del self.pools[jid]
        except:
            pass
        self.sendPresence(self.jid,jid,"unavailable")
    def stopService(self):
        print "logging out..."
        for u in self.threads.keys():
            try:
                self.threads[u].exit()
                del self.threads[u]
                self.pools[u].stop()
                del self.pools[u]
            except:
                pass
            self.sendMessage(self.jid,u,u"Транспорт отключается, в ближайшее время он будет запущен вновь.")
            self.sendPresence(self.jid,u,"unavailable")
        print "done"
        return None
    def sendMessage(self,src,dest,body):
        msg=domish.Element((None,"message"))
        try:
            msg["to"]=dest.decode("utf-8")
        except:
            msg["to"]=dest
        msg["from"]=src
        msg["type"]="chat"
        msg["id"]="msg%s"%(int(time.time())%10000)
        msg.addElement("body").addContent(body)
        
        #FIXME "id"???
        self.xmlstream.send(msg)
    def sendPresence(self,src,dest,t=None,extra=None,status=None):
        pr=domish.Element((None,"presence"))
        if (t):
            pr["type"]=t
        pr["to"]=unicode(dest)
        pr["from"]=src
        if(status):
            pr.addElement("status").addContent(status)
        pr.addElement("c","http://jabber.org/protocol/caps").attributes={"node":"http://pyvk-t.googlecode.com","ver":self.revision}
        self.xmlstream.send(pr)
        

