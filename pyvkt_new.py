# -*- coding: utf-8 -*-

"""
 Example component service.
 
"""
import time
import twisted
from twisted.words.protocols.jabber import jid, xmlstream
from twisted.application import internet, service
from twisted.internet import interfaces, defer, reactor
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
        log.msg("%s - RECV: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))

    def rawDataOut(self, buf):
        log.msg("%s - SEND: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))

def bareJid(jid):
    n=jid.find("/")
    if (n==-1):
        return jid
    return jid[:n]
class pyvk_t(component.Service,vkonClient):
    """
    Example XMPP component service using twisted words.

    Basic Echo - We return the xml that is sent us.
    
    """
    implements(IService)

    def __init__(self):
        config = ConfigParser.ConfigParser()
        config.read("pyvk-t_new.cfg")
        self.dbpool = adbapi.ConnectionPool(
            config.get("database","module"), 
            host=config.get("database","host"), 
            user=config.get("database","user"), 
            passwd=config.get("database","passwd"), 
            db=config.get("database","db"))
        self.threads={}
        self.pools={}
        #try:
        proc=os.popen("svnversion")
        s=proc.read()
        if(s=="exported" or s==""):
            self.revision="alpha"
        else:
            p=s.find(":")
            ver=s[p+1:-1]
            self.revision="svn rev. %s"%ver
        #except:
            #log.msg("can't ret revision")
            #self.revision="alpha"
            
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
        xmlstream.addObserver('/message', self.onMessage, 1)

    def onMessage(self, msg):
        """
        Act on the message stanza that has just been received.

        """
        body=msg.body.children[0]
        bjid=bareJid(msg["from"])
        if (body[0:1]=="/"):
            cmd=body[1:]
            log.msg(cmd.encode("utf-8"))
            if (cmd=="login"):
                self.login(bjid)
            if (self.threads.has_key(bjid) and self.threads[bjid]):
                if (cmd=="get roster"):
                    d=defer.execute(self.threads[bjid].getFriendList)
                    d.addCallback(self.sendFriendlist,jid=bjid)
            if (cmd=="help"):
                self.sendMessage(self.jid,msg["from"],u"/get roster для получения списка\n/login дла подключения")
            return

        #if (body[0:1]=="$" and bjid=="eqx@eqx.su"):
            #try:
                #eval(body[1:])
            #except:
                #log.msg("eval('%s') failed"%body)
            #return
        if(msg["to"]!=self.jid and self.threads.has_key(bjid)):
            dogpos=msg["to"].find("@")
            try:
                v_id=int(msg["to"][:dogpos])
            except:
                log.msg("bad JID: %s"%msg["to"])
                return
            self.pools[bjid].callInThread(self.submitMessage,jid=bjid,v_id=v_id,body=body,title="[sent by pyvk-t]")
        
            #TODO delivery notification
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
                    log.msg("info request")
                    ident=q.addElement("identity")
                    ident["category"]="gateway"
                    ident["type"]="vkontakte.ru"
                    ident["name"]="Vkontakte.ru Transport [twisted]"
                    q.addElement("feature").attributes={"category":"x-service","type":"pyvk-t","name":"Vkontakte.ru transport [twisted]"}
                    q.addElement("feature")["var"]="jabber:iq:register"
                    q.addElement("feature")["var"]="jabber:iq:gateway"
                    ans.send()
                    return
                elif (query.uri=="http://jabber.org/protocol/disco#items"):
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
                    
            vcard=iq.vCard
            if (vcard):
                #log.msg("vcard request")
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
                    ans.send()
                    return
                    
        if (iq["type"]=="set"):
            query=iq.query
            if (query):
                log.msg("from %s"%bareJid(iq["from"]))
                log.msg(query.toXml())
                email=""
                pw=""
                #log.msg(filter(lambda x:type(x)=='twisted.words.xish.domish.Element',query.children))
                for i in filter(lambda x:type(x)==twisted.words.xish.domish.Element,query.children):
                    log.msg(i)
                    if (i.name=="email"):
                        email=i.children[0]
                    if (i.name=="password"):
                        pw=i.children[0]
                #qq=self.dbpool.runQuery("SELECT * FROM users WHERE jid='%s'"%safe(bareJid(iq["from"])))
                qq=self.dbpool.runQuery("DELETE FROM users WHERE jid='%s';INSERT INTO users (jid,email,pass) VALUES ('%s','%s','%s')"%
                    (safe(bareJid(iq["from"])),safe(bareJid(iq["from"])),safe(email),safe(pw)))
                qq.addCallback(self.register2,jid=iq["from"],iq_id=iq["id"],success=1)
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
        if (self.threads.has_key(jid)):
            return
        self.threads[jid]=0
        mq="SELECT * FROM users WHERE jid='%s'"%safe(bareJid(jid))
        log.msg(mq)
        q=self.dbpool.runQuery(mq)
        q.addCallback(self.login1)
        pass
    def login1(self,data):
        t=data[0]
        defer.execute(self.createThread,data[0][0],data[0][1],data[0][2])
        self.sendPresence(self.jid,data[0][0])
    def loginFailed(self,data,jid):
        msg.log("login failed for %s"%jid)
        del self.threads[jid]
    def createThread(self,jid,email,pw):
        self.threads[jid]=vkonThread(cli=self,jid=jid,email=email,passw=pw)
        self.pools[jid]=ThreadPool(1,1)
        self.pools[jid].start()
        log.msg("%s,%s,%s"%(jid,email,pw))
        log.msg(self.threads)
        self.threads[jid].start()
        self.threads[jid].feedOnly=0
    #def usersOnline(self,jid,users):
        #log.msg(users)
    def sendFriendlist(self,fl,jid):
        log.msg("fiendlist ",jid)
        log.msg(fl)
        for f in fl:
            src="%s@%s"%(f,self.jid)
            log.msg(src)
            #self.sendPresence(src,jid,"subscribed")
            self.sendPresence(src,jid,"subscribe")
            #return
        return
    def getsendVcard(self,jid,v_id,iq_id):
        log.msg(jid)
        log.msg(v_id)
        bjid=bareJid(jid)
        try:
            card=self.threads[bjid].getVcard(v_id)
        except:
            log.msg("some fcky error")
            return

        log.msg(card)
        ans=xmlstream.IQ(self.xmlstream,"result")
        ans["to"]=jid
        ans["from"]="%s@%s"%(v_id,self.jid)
        ans["id"]=iq_id
        vc=ans.addElement("vCard","vcard-temp")
        if (card):
            if (type(card["fn"]!=unicode)):
                card["fn"]=card["fn"].decode("utf-8")
            vc.addElement("NICKNAME").addContent(card["fn"])
        vc.addElement("URL").addContent("http://vkontakte.ru/id%s"%v_id)
        ans.send()
        #log.msg(ans.toXml())
    def requestMessage(self,jid,msgid):
        msg=self.threads[jid].getMessage(msgid)
        log.msg(msg)
        self.sendMessage("%s@%s"%(msg["from"],self.jid),jid,msg["text"])
    def submitMessage(self,jid,v_id,body,title):
        log.msg((jid,v_id,body,title))
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
        except:
            log.msg("feed error")
        self.sendPresence(self.jid,jid,status=ret)
    def usersOnline(self,jid,users):
        for i in users:
            self.sendPresence("%s@%s"%(i,self.jid),jid)
    def usersOffline(self,jid,users):
        for i in users:
            self.sendPresence("%s@%s"%(i,self.jid),jid,t="unavailable")
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
            self.sendPresence(self.jid,u,"unavailable")
        print "done"
        return None
    def sendMessage(self,src,dest,body):
        msg=domish.Element((None,"message"))
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
        pr["to"]=dest
        pr["from"]=src
        if(status):
            pr.addElement("status").addContent(status)
        self.xmlstream.send(pr)
        

