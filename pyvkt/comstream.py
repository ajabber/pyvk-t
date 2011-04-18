# -*- coding: utf-8 -*-
import socket,errno,hashlib
#from xml.dom import minidom
#from xml.dom.minidom import Element
from lxml import etree
import threading,time
from threading import Thread
from Queue import Queue,Empty
from traceback import format_exc,extract_stack,format_list
import logging,time
import pyvkt.config as conf
from pyvkt.spikes import counter
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


if not hasattr(socket, 'create_connection'):
    def connect_socket(address):
        """Connect to *address* and return the socket object.

        Convenience function.  Connect to *address* (a 2-tuple ``(host,
        port)``) and return the socket object.

        Heavily inspired from the python 2.6 socket.create_connection()
        function.
        """
        msg = "getaddrinfo returns an empty list"
        host, port = address
        for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                sock.connect(sa)
                return sock

            except socket.error, msg:
                if sock is not None:
                    sock.close()
        raise socket.error, msg
else:
    connect_socket = socket.create_connection

newLoop=True
class xmlstream(object):
    "Да, я знаю, что тут костыль на костыле и костылем погоняет."
    alive=True
    connFailure=False
    fixNs=False
    stanzasIn=0
    stanzasOut=0
    enableDump=False
    sendHistory=['']*10
    loopNames=[None]
    slowThreshold=10
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
        self.counter=counter()
    def connect(self,host,port,secret):
        self.host=host
        self.port=port
        self.secret=secret
        #sock=socket.create_connection((host,port))
        sock=connect_socket((host,port))
        #FIXME connecting
        sock.send("<stream:stream xmlns='jabber:component:accept' xmlns:stream='http://etherx.jabber.org/streams' to='%s'>"%self.jid)
        #fil=sock.makefile(bufsize=1)
        rep=sock.recv(1000)
        rep=rep.replace("<?xml version='1.0'?>", "") # Replacing sock.recv(len("<?xml version='1.0'?>"))
        logging.debug('Received server auth answer: %s'%rep)
        ids=rep.find("id='")
        ide=rep.find("'",ids+5)
        sid=rep[ids+4:ide]
        hsh=hashlib.sha1(str(sid)+secret).hexdigest()
        resp="<handshake>%s</handshake>"%hsh
        sock.send(resp)
        if (0):
            sock.settimeout(None)
        else:
            sock.settimeout(3)
        self.sock=sock
        handshake_answer=self.getPacket(True)
        logging.debug('Received handshake answer: %s'%handshake_answer)
        #FIXME Namespaces
        if (handshake_answer=='<handshake/>'):
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
                    logging.error('buffer:\n%s'%(''.join(buf)))
                    raise Exception('connection failure')
                c=self.sock.recv(1)
                buf.append(c)
            except socket.error,e:
                if getattr(e, 'errno', None) is not None:
                    e_errno = e.errno
                elif type(getattr(e, 'error', None)) is tuple:
                    e_errno = e.error[0]
                elif type(getattr(e, 'args', None)) is tuple:
                    e_errno = e.args[0]
                else:
                    e_errno = errno.ESHUTDOWN # any value, but not not EAGAIN
                if (e_errno == errno.EAGAIN):
                    time.sleep(1)
                else:
                    self.connectionFailure=True
                    logging.exception('recvLoop failure')
                    logging.error('buffer:\n%s'%(''.join(buf)))
                    raise
        sn=''.join(buf)
        if (sn[-2:]=='/>'):
            if (self.enableDump):
                logging.warning("received %s"%sn)
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
                        logging.error('buffer:\n%s%s'%(es,''.join(buf)))
                        raise Exception('connection failure')
                    c=self.sock.recv(1)
                    buf.append(c)
                sn=''.join(buf)
                #sn=sn+self.sock.recv(1)
            except socket.error,e:
                if getattr(e, 'errno', None) is not None:
                    e_errno = e.errno
                elif type(getattr(e, 'error', None)) is tuple:
                    e_errno = e.error[0]
                elif type(getattr(e, 'args', None)) is tuple:
                    e_errno = e.args[0]
                else:
                    e_errno = errno.ESHUTDOWN # any value, but not not EAGAIN
                if (e_errno == errno.EAGAIN):
                    time.sleep(1)
                else:
                    self.connectionFalure=True
                    logging.exception('recvLoop failure')
                    logging.error('buffer:\n%s%s'%(es,''.join(buf)))
                    raise
        if (self.enableDump):
            logging.warning("received %s"%sn)
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
                #p=etree.fromstring(s)
                #if ('stream' in p.tag):
                    #logging.warning('stream stanza: %s\n'%tostring(p))
                self.recvQueue.put_nowait(s)
                self.stanzasIn+=1
            except:
                logging.error("queue error\n"+format_exc())
                #print_exc()
    def waitForReconnect(self):
        if(self.connFailure):
            logging.warning('wfr: lock')
            self.connected.acquire()
            self.connected.wait()
            self.connected.release()
            logging.warning ('wfr: respawn')
    
    def recvLoop2(self):
        buf=''
        tagname=None
        skip=0
        while (1):
            try:
                try:
                    tb=self.sock.recv(1024)
                except (socket.timeout, AttributeError):
                    # timeout or missing sock object
                    tb=''
                except socket.error,e:
                    if (e.errno == errno.EAGAIN):
                        logging.warning('eagain')
                        tb=''
                        #time.sleep(1)
                        #continue
                    else:
                        buf=''
                        self.connectionFailure=True
                        logging.exception('recvLoop failure')
                        logging.critical("recvLoop: stream error\n"+str(e))
                        self.connFailure=True
                        self.waitForReconnect()
                        continue
                if (len(tb)==0):
                    if (len(buf)):
                        logging.warning('tb empty. buf length: %s'%len(buf))
                    if (self.connFailure):
                        logging.warning('socket failure')
                        buf=''
                        self.waitForReconnect()
                    time.sleep(1)
                buf+=tb
                if (len(buf)>50000):
                    logging.warning('buffer too big: %s'%len(buf))
                    logging.warning('tagname: %s'%repr(tagname))
                while (1):
                    #begin position
                    bp=buf.find('<')
                    if (bp==-1):
                        break
                    # end of tagname position
                    tep=buf.find(' ',bp)
                    tep2=buf.find('>',bp)
                    if (tep2<tep and tep2!=-1):
                        tep=tep2

                    tagname=buf[bp+1:tep]
                    if (tagname.find('/')!=-1):
                        logging.error('bad tag: %s\nbuffer:%s'%(repr(tagname),repr(buf)))
                        buf=buf[tep:]
                        logging.warning('trying to re-use buffer')
                        continue
                    endtag='</%s>'%tagname
                    etp=buf.find(endtag,tep)
                    if (etp!=-1):
                        sep=buf.find('/>',tep,etp)
                        if (sep!=-1 and buf.find('>',tep,sep)==-1):
                            self.recvQueue.put_nowait(buf[bp:sep+2])
                            buf=buf[sep+2:]
                            continue
                        self.recvQueue.put_nowait(buf[bp:etp+len(endtag)])
                        buf=buf[etp+len(endtag):]
                        continue
                    else:
                        sep=buf.find('/>',tep)
                        if (sep!=-1 and buf.find('>',tep,sep)==-1):
                            self.recvQueue.put_nowait(buf[bp:sep+2])
                            buf=buf[sep+2:]
                            continue
                    break
            except:
                logging.exception('')
                    
    def sendLoop(self):
        while(1):
            try:
                task,st=self.sendQueue.get(True,10)
            except Empty:
                task=createElement('iq',{'from':self.jid,'to':self.jid,'id':'keepalive', 'type':'get'})
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
                    self.stanzasOut+=1
                    self.sendHistory.insert(0,s)
                    self.sendHistory.pop()
                except Exception, e:
                    logging.critical("send loop: stream error\n"+str(e))
                    self.connFailure=True
                    self.connected.acquire()
                    self.connected.wait()
                    self.connected.release()
                    logging.warning("send loop respawned")
                    self.send(task)
                   
    def send(self,packet):
        #TODO check for debug mode 
        if (fixNs):
            packet.tag='{jabber:client}%s'%packet.tag
        st=extract_stack(limit=2)
        try:
            self.sendQueue.put_nowait((packet,st))
        except queue.Full:
            logging.error('recvQueue full')
            t=packet.tag
            s=packet.get('from')
            d=packet.get('to')
            logging.error('dropped stanza: %s %s->%s'%(t,s,d))
            
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
    def printHistory(self):
        sl='\n'.join(self.sendHistory)
        logging.warning('last sent stanzas: \n%s'%sl)
    def loop(self,loopno=0):
        while(self.alive and loopno < len(self.loops)):
            try:
                st=self.recvQueue.get(True,10)
                self.stanzasIn+=1
                st=etree.fromstring(st)
            except Empty:
                pass
            except etree.XMLSyntaxError,e:
                if 'stream:error' in st:
                    logging.error('stream error stanza: %s'%repr(st))
                    if ('xml-not-well-formed' in st):
                        self.printHistory()
                else:
                    logging.error('bad xml: %s'%(repr(st)[:300]))
            else:
                if (st.get("to").find(self.jid)!=-1):
                    try:
                        t=time.time()
                        self.handlePacket(st,dbg=False)
                        t2=time.time()
                        if (t2-t>self.slowThreshold):
                            logging.warning('sooo slooooow (%s):\n%s'%(t2-t,etree.tostring(st)))
                    except:
                        logging.error("unhandled exception:\n"+format_exc().decode("utf-8"))
        logging.warning('loop %s stopped'%loopno)
    def addLoop(self):
        i=len(self.loops)
        logging.warning('starting loop %s'%i)
        t=Thread(target=self.loop,name="mainloop-%s"%i, kwargs={'loopno':i})
        t.daemon=True
        self.loops.append(t)
        t.start()

        return len(self.loops)
    def delLoop(self):
        del self.loops[len(self.loops)-1]
        logging.warning('stopping loop: len(loops)=%s'%len(self.loops))
        return len(self.loops)
    def main(self):
        if (newLoop):
            self.rt=Thread(target=self.recvLoop2,name='receiver')
        else:
            self.rt=Thread(target=self.recvLoop,name='receiver')
        self.rt.daemon=True
        self.rt.start()
        self.st=Thread(target=self.sendLoop,name='sender')
        self.st.daemon=True
        self.st.start()
        self.loops=[]
        for i in range(4):
            self.addLoop()
            #logging.info("starting mainloop-%s"%i)
            #t=Thread(target=self.loop,name="mainloop-%s"%i)
            
            #t.daemon=True
            #t.start()
            #self.loops.append(t)
        while(self.alive):
            try:
                if (self.connFailure):
                    logging.error('connection failure detected. Trying to reconnect')
                    try:
                        self.sock.close()
                        del self.sock
                    except AttributeError:
                        pass
                    logging.warning('waiting for recvloop to die...')
                    time.sleep(5)
                    if self.connect(host=self.host, port=self.port, secret=self.secret):
                        logging.error('connection established successfully')
                    else:
                        logging.error('can\'t re-establish connection. aborting.')
                        return
                        # maybe, sys.exit()?
                else:
                    #logging.warning('socket OK')
                    pass
                try:
                    st=self.recvQueue.get(True,10)
                    self.stanzasIn+=1
                    st=etree.fromstring(st)
                    #st=etree.fromstring(self.recvQueue.get(True,10))
                except etree.XMLSyntaxError,e:
                    if 'stream:error' in st:
                        logging.error('stream error stanza: %s'%repr(st))
                        if ('xml-not-well-formed' in st):
                            self.printHistory()
                    else:
                        logging.error('bad xml: %s'%(repr(st)[:300]))
                except Empty:
                    pass
                else:
                    #logging.warning('invoking handler (tag: %s)'%repr(st.tag))
                    if ('stream' in st.tag):
                        logging.warning('stream stanza: %s'%repr(tostring(st)))
                    if (st.get("to").find(self.jid)!=-1):
                        try:
                            self.handlePacket(st,dbg=False)
                        except:
                            logging.error("unhandled exception:\n"+format_exc().decode("utf-8"))
                            #logging.exception()
                    #logging.warning('handler finished')
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






