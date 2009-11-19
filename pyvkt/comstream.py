# -*- coding: utf-8 -*-
import socket,errno,hashlib
#from xml.dom import minidom
#from xml.dom.minidom import Element
from lxml import etree
import threading
from threading import Thread
from Queue import Queue,Empty
from traceback import format_exc,extract_stack,format_list
import logging,time
import pyvkt.config as conf
fixNs=False
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
    if (fixNs):
        nsmap={None:'{jabber:client}'}
    else:
        nsmap=None
    ret=etree.Element(tag, nsmap=nsmap)
    if (attrs):
        for i in attrs.keys():
            try:
                ret.set(i,attrs[i])
            except TypeError:
                logging.warning("wrong attribute: '%s': '%s'"%(i,attrs[i]))
                raise
    return ret
def createReply(iq,t='result'):
    ret=etree.Element('iq')
    ret.set('from',iq.get('to'))
    ret.set('to',iq.get('from'))
    ret.set('id',iq.get('id'))
    ret.set('type',t)
    return ret
    
class xmlstream:
    "Да, я знаю, что тут костыль на костыле и костылем погоняет."
    alive=True
    connFailure=False
    fixNs=False
    stranzasIn=0
    stranzasOut=0
    def __init__(self,jid):
        self.jid=jid
        self.sendQueue=Queue()
        self.recvQueue=Queue()
        self.connected=threading.Condition()
        if (conf.get('workarounds/fix_namespaces')):
            logging.warning('namespace workaround enabled')
            fixNs=True
        #print fil.read(10)
        #d=minidom.parseString("<stream:stream xmlns:stream='http://etherx.jabber.org/streams' xmlns='jabber:component:accept' id='1002154109' from='ratatoskr' />")

    def connect(self,host,port,secret):
        self.host=host
        self.port=port
        self.secret=secret
        sock=socket.create_connection((host,port))
        #FIXME connecting
        sock.send("<stream:stream xmlns='jabber:component:accept' xmlns:stream='http://etherx.jabber.org/streams' to='%s'>"%self.jid)
        sock.recv(len("<?xml version='1.0'?>"))
        fil=sock.makefile(bufsize=1)
        rep= sock.recv(1000)
        ids=rep.find("id='")
        ide=rep.find("'",ids+5)
        sid=rep[ids+4:ide]
        hsh=hashlib.sha1(str(sid)+secret).hexdigest()
        resp="<handshake>%s</handshake>"%hsh
        sock.send(resp)
        sock.settimeout(0)
        self.sock=sock

        if (self.getPacket(True)=='<handshake/>'):
            self.connFailure=False
            self.connected.acquire()
            self.connected.notifyAll()
            self.connected.release()            
            return True
        return False

    def getPacket(self, ignoreFail=False):
        #TODO use cStringIO?
        sn=""
        buf=[]
        c=None
        while (c!='>'):
            try:
                
                if (self.connFailure and not ignoreFail):
                    raise Exception('connection failure')
                c=self.sock.recv(1)
                buf.append(c)
                #sn=sn+c
                #print sn
                #if (c=='>'):
                    #break
            except socket.error,e:
                if (e.errno == errno.EAGAIN):
                    time.sleep(1)
                else:
                    self.connectionFailure=True
                    logging.exception('recvLoop failure')
                    raise
        sn=''.join(buf)
        if (sn[-2:]=='/>'):
            logging.debug("received %s"%sn)
            return sn
        es='</'+sn.split()[0][1:]+'>'
        les=len(es)
        while(sn[-les:]!=es):
            #print sn
            try:
                buf=[sn]
                c=None
                while(c!='>'):
                    if (self.connFailure and not ignoreFail):
                        raise Exception('connection failure')                
                    c=self.sock.recv(1)
                    buf.append(c)
                sn=''.join(buf)    
                #sn=sn+self.sock.recv(1)
            except socket.error,e:
                if (e.errno == errno.EAGAIN):
                    time.sleep(1)
                else:
                    self.connectionFalure=True
                    logging.exception('recvLoop failure')
                    raise

        #print
        logging.debug("received %s"%sn)
        return sn
    def recvLoop(self):
        while(1):
            #print etree.fromstring(self.getPacket())
            try:
                s=None
                s=self.getPacket()
            except Exception ,e:
                logging.critical("recv loop: stream error\n"+str(e))
                self.connFailure=True
                self.connected.acquire()
                self.connected.wait()
                self.connected.release()
                logging.warning ('recvLoop: respawned')
                continue
            try:
                self.recvQueue.put(etree.fromstring(s))
                self.stranzasIn+=1
            except:
                logging.error("queue error\n"+format_exc())
                #print_exc()
    def sendLoop(self):
        while(1):
            try:
                task,st=self.sendQueue.get(True,10)
            except Empty:
                task=createElement('iq',{'from':self.jid,'to':self.jid,'id':'keepalive'})
                logging.info('sending keepalive')
            try:
                s=etree.tostring(task,encoding='utf-8')
            except:
                logging.error("can't serialize\n"+format_exc())
                logging.error("bad packet came from\n%s"%''.join(format_list(st)))
            else:
                if (type(s)==unicode):
                    s=s.encode("utf-8")
                logging.debug("sending %s"%s.decode('utf-8'))
                try:
                    self.sock.send(s)
                    self.stranzasOut+=1
                except Exception, e:
                    logging.critical("send loop: stream error\n"+str(e))
                    self.connFailure=True
                    self.connected.acquire()
                    self.connected.wait()
                    self.connected.release()                    
                    logging.warning("send loop respawned")
                    self.send(task)
                    #try:
                        #self.sock.close()
                        #del self.sock
                    #except:
                        #logging.exception('')
                    #self.connect(self.host,self.port,self.secret)
                    
    def send(self,packet):
        #TODO check for debug mode 
        if (fixNs):
            packet.tag='{jabber:client}%s'%packet.tag
        st=extract_stack(limit=2)
        self.sendQueue.put((packet,st))
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
        for i in range(1):
            logging.info("starting mainloop-%s"%i)
            t=Thread(target=self.loop,name="mainloop-%s"%i)
            
            t.daemon=True
            t.start()
            self.loops.append(t)
        while(self.alive):
            try:
                try:
                    st=self.recvQueue.get(True,10)
                except Empty:
                    if (self.connFailure):
                        logging.error('connection failure detected. Trying to reconnect')
                        self.sock.close()
                        del self.sock
                        if self.connect(host=self.host, port=self.port, secret=self.secret):
                            logging.error('connection established siccessfully')
                        else:
                            logging.error('can\'t re-establish connection. aborting.')
                            return
                            # maybe, sys.exit()?
                    pass
                else:
                    if (st.get("to").find(self.jid)!=-1):
                        try:
                            self.handlePacket(st)
                        except:
                            logging.error("unhandled exception:\n"+format_exc().decode("utf-8"))
                            #logging.exception()
            except KeyboardInterrupt:
                logging.error("comstream: caught interrupt")
                if self.kbInterrupt():
                    pass
                else:
                    return
                return
            except:
                logging.critical("exception in main loop:")
                logging.exception('')
                
        logging.warn("main loop stopped. goodbye!")
    def kbInterrupt(self):
        print "kbinterrupt"
        self.alive=0
        self.term()
        return False
                #self.send(self.revert(st))






