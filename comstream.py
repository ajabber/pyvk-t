# -*- coding: utf-8 -*-
import socket,hashlib
#from xml.dom import minidom
#from xml.dom.minidom import Element
from lxml import etree
from threading import Thread
from Queue import Queue,Empty
from traceback import format_exc
import logging,time
def addChild(node,name,ns=None,attrs=None):
    if(ns):
        name='{%s}%s'%(ns,name)
        nsmap={None:ns}
    else:
        nsmap=None
    ret=etree.SubElement(node,name,nsmap=nsmap)
    if (attrs):
        for i in attrs.keys():
            ret.set(i,attrs[i])
    return ret
def createElement(tag,attrs=None):
    ret=etree.Element(tag)
    if (attrs):
        for i in attrs.keys():
            ret.set(i,attrs[i])
    return ret
def createReply(iq,t='result'):
    ret=etree.Element('iq')
    ret.set('from',iq.get('to'))
    ret.set('to',iq.get('from'))
    ret.set('id',iq.get('id'))
    ret.set('type',t)
    return ret
    
class xmlstream:
    alive=True
    def __init__(self,jid):
        self.jid=jid
        self.sendQueue=Queue()
        self.recvQueue=Queue()
        #print fil.read(10)
        #d=minidom.parseString("<stream:stream xmlns:stream='http://etherx.jabber.org/streams' xmlns='jabber:component:accept' id='1002154109' from='ratatoskr' />")

    def connect(self,host,port,secret):
        self.host=host
        self.port=port
        self.secret=secret
        sock=socket.create_connection((host,port))
        #FIXME connecting
        sock.send("<stream:stream xmlns='jabber:component:accept' xmlns:stream='http://etherx.jabber.org/streams' to='%s'>"%host)
        sock.recv(len("<?xml version='1.0'?>"))
        fil=sock.makefile(bufsize=1)
        rep= sock.recv(1000)
        ids=rep.find("id='")
        ide=rep.find("'",ids+5)
        sid=rep[ids+4:ide]
        hsh=hashlib.sha1(str(sid)+secret).hexdigest()
        resp="<handshake>%s</handshake>"%hsh
        sock.send(resp)
        self.sock=sock
        if (self.getPacket()=='<handshake/>'):
            return True
        return False

    def getPacket(self):
        sn=""
        while (1):
            c=self.sock.recv(1)
            sn=sn+c
            #print sn
            if (c=='>'):
                break
        if (sn[-2:]=='/>'):
            logging.debug("received %s"%sn)
            return sn
        es='</'+sn.split()[0][1:]+'>'
        les=len(es)
        while(sn[-les:]!=es):
            #print sn
            sn=sn+self.sock.recv(1)
        #print
        logging.debug("received %s"%sn)
        return sn
    def recvLoop(self):
        while(1):
            #print etree.fromstring(self.getPacket())
            try:
                s=None
                s=self.getPacket()
            except:
                logging.critical("stream error\n"+format_exc())
                time.sleep(1)
            try:
                self.recvQueue.put(etree.fromstring(s))
            except:
                logging.error("queue error\n"+format_exc())
                #print_exc()
    def sendLoop(self):
        while(1):
            task=self.sendQueue.get(True)
            try:
                try:
                    s=etree.tostring(task,encoding='utf-8')
                except TypeError:
                    logging.info("deprecated domish!")
                    s=task.toXml()
            except:
                logging.error("can't serialize\n"+format_exc())
            else:
                if (type(s)==unicode):
                    s=s.encode("utf-8")
                logging.debug("sending %s"%s.decode('utf-8'))
                try:
                    self.sock.send(s)
                except:
                    logging.error("can't send()\n"+format_exc())
                    logging.error("trying to reconnect...")
                    self.sock.close()
                    self.connect(self.host,self.port,self.secret)
                    
    def send(self,packet):
        self.sendQueue.put(packet)
    def revert(self,packet):
        f=packet.get("from")
        t=packet.get("to")
        packet.set("from",t)
        packet.set("to",f)
        return packet
    def handlePacket(self,st):
        #self.send(self.revert(st))
        pass
    def makeAnswer(self,iq):
        ret=etree.Element("iq")
        ret.set("to",iq.get("from"))
        ret.set("from",iq.get("to"))
        ret.set("id",iq.get("id"))
    def loop(self):
        while(self.alive):
            try:
                st=self.recvQueue.get(True,100)
            except Empty:
                pass
            else:
                if (st.get("to").find(self.jid)!=-1):
                    try:
                        self.handlePacket(st)
                    except:
                        logging.error("unhandled exception:\n"+format_exc().decode("utf-8"))

    def main(self):
        self.rt=Thread(target=self.recvLoop,name='receiver')
        self.rt.daemon=True
        self.rt.start()
        self.st=Thread(target=self.sendLoop,name='sender')
        self.st.daemon=True
        self.st.start()
        self.loops=[]
        for i in range(0):
            logging.info("starting mainloop-%s"%i)
            t=Thread(target=self.loop,name="mainloop-%s"%i)
            
            t.daemon=True
            t.start()
            self.loops.append(t)
        while(self.alive):
            try:
                try:
                    st=self.recvQueue.get(True,100)
                except Empty:
                    pass
                else:
                    if (st.get("to").find(self.jid)!=-1):
                        try:
                            self.handlePacket(st)
                        except:
                            logging.error("unhandled exception:\n"+format_exc().decode("utf-8"))
            except KeyboardInterrupt:
                logging.error("comstream: caught interrupt")
                if self.kbInterrupt():
                    pass
                else:
                    return
                return
                
        logging.warn("main loop stopped. goodbye!")
    def kbInterrupt(self):
        print "kbinterrupt"
        self.alive=0
        self.term()
        return False
                #self.send(self.revert(st))






