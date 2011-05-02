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
from twisted.internet.defer import Deferred
import Queue
import threading,time,logging
from traceback import format_exc,extract_stack,format_list
from libvkontakte import authFormError,HTTPError,UserapiSidError, tooFastError, PrivacyError, captchaError,UserapiJsonError,UserapiCaptchaError
import pyvkt.general as gen
import asyncore
import socket
import re
import demjson
import weakref,gc
import cProfile as prof
try:
    import hook
    logging.warning('hooks loaded')
except:
    pass
class pseudoXml:
    def __init__(self):
        self.items={}
        self.children=[]
        self.attrs={}
    def __getitem__(self,n):
        return self.items[n]
    def __getattr__(self,n):
        return self.attrs[n]
    def hasAttribute(self,k):
        return self.attrs.has_key(k)
    def __nonzero__(self):
        return True
class reqQueue(object):
    __slots__=['last','lastTime','_thread','alive','queue','user','threadId','name','__weakref__','bjid']
    def __init__(self,user,bjid=None,ownThread=True):
        try:
            #n=str(name)
            j=str(bjid)
        except UnicodeEncodeError:
            #n=repr(name)
            j=repr(bjid)
        n='rq (%s)'%j
        if (False):
            self._thread=threading.Thread(target=self.loop,name='pool(%s)'%n)
            self._thread.daemon=True
        else:
            self._thread=None
        self.user=user
        self.name=n
        self.bjid=j
        self.queue=Queue.Queue()
        self.alive=1
        self.lastTime=time.time()
        self.last='init'
        self.threadId=None
    def start(self):
        self.user.trans.usrPool.addQueue(self)
        return
        if self._thread:
            self._thread.start()
    def len(self):
        return self.queue.qsize()
    def call(self,foo,**kw):
        elem={"foo":foo,"args":kw,'stack':extract_stack()}
        try:
            self.queue.put(elem,block=False)
        except Queue.Full:
            self.printFullError(foo)
            raise gen.QuietError()
    def defer(self,f,**kw):
        d=Deferred()
        elem={"foo":f,"args":kw,"deferred":d,'stack':extract_stack()}
        try:
            self.queue.put(elem,block=False)
        except Queue.Full:
            self.printFullError(f)
            raise gen.QuietError()
        return d
    def printFullError(self,ct):
        t=time.time()-self.lastTime
        if ('addResource' in str(ct)):
            return
        qs=self.queue.qsize()
        if (t>0.5):
            logging.error('pool[%s]: queue full (%s)! timeout: %i \n*\t\tlast task: %80s, curr task: %80s'%(qs,self.name,t,self.last['foo'],repr(ct)))
        
    def stop(self):
        self.alive=0
        self.last=None
        #self.call(self.dummy)
        self.user=None
        #print gc.get_referrers(self)
    def dummy(self):
        return
    def loopWrapper(self):
        #if 'eqx@eqx.su' in self.name:
        #    l=self.loop
        #    prof.runctx('l()',globals(), locals(), 'profile_%s'%time.time())
        #else:
            self.loop()
    def doNextTask(self,block=True):
        elem=None
        elem=self.queue.get(block=False)
        self.last=elem
        f=elem["foo"]
        last=repr(f)
        args=elem["args"]
        self.lastTime=time.time()
        try:
            res=f(**args)
            dt=time.time()-self.lastTime
            if (dt>15):
                logging.warning('slow [%6.4f] task done: %s '%(dt,repr(f)))
        except authFormError:
            logging.warn("%s: got login form")
            try:
                self.alive=0
                self.user.logout()
                self.user.trans.sendMessage(src=self.user.trans.jid,dest=self.user.bjid,body=u"Ошибка: возможно, неверный логин/пароль")
            except:
                logging.error(format_exc())
        except gen.NoVclientError:
            if (self.user):
                logging.error("err: no vClient (%s)"%repr(self.user.bjid))
            else:
                logging.warning("loop: self.user==None. aborting")
                return
        except PrivacyError:
            self.user.trans.sendMessage(src=self.user.trans.jid,dest=self.user.bjid, body=u'Запрошенная операция запрещена настройками приватности на сайте.')
            logging.warning('privacy error')
        except UserapiCaptchaError,e:
            logging.warning('userapi captcha error')
            link='http://userapi.com/data?act=captcha&csid=%s'%e.fcsid
            self.user.trans.sendMessage(src=self.user.trans.jid,dest=self.user.bjid, body=u'Невозможно выполнить операцию, captcha-защита.\nСмотрим картинку по ссылке %s и отправляем транспорту код командой ".captcha aaaaa", вместо aaaaa пишем код с картинки, затем проверяем, выполнилась ли операция (.history, .wall и т.п.)\nв случае ошибок запоминаем точное время попытки и заходим на pyvkt@conference.jabber.ru'%link)
        #except captchaError:
            #self.user.trans.sendMessage(src=self.user.trans.jid,dest=self.user.bjid, body=u'Запрошенная операция не может быть выполнена из-за captcha-защиты на юзерапи. На данный момент обработка captcha не реализована.')
        except HTTPError,e:
            logging.error("http error: "+str(e).replace('\n',', '))
        except UserapiSidError:
            logging.error('userapi sid error (%s) logging out.\nsid = %s'%self.user.bjid,self.user.vclient.sid)
            txt=u"Внутренняя ошибка транспорта (UseraspiSidError)"
            self.user.vclient.initCookies()
            self.user.logout()
            return
        except tooFastError:
            logging.warning('FIXME "too fast" error stanza')
        except gen.InternalError,e:
            logging.error('internal error: %s'%e)
            if e.fatal:
                logging.error('fatal error')
                return
            txt=u"Внутренняя ошибка транспорта (%s):\n%s"%(e.t,e.s)
            self.user.trans.sendMessage(src=self.user.trans.jid,dest=self.user.bjid,
                body=txt)
        except UserapiJsonError:
            logging.warning('userapi request failed')
        except Exception, exc:
            logging.exception('')
            logging.error('unhandled exception: %s'%exc)
            logging.error('task traceback:\n -%s'%(' -'.join(format_list(elem['stack']))))
            #[logging.error('TB '+i[:-1]) for i in format_list(elem['stack'])]
            #print "Caught exception"
            #print_exc()
            #print "thread is alive!"
            
        else:
            try:
                elem["deferred"].callback(res)
            except KeyError:
                pass
            except:
                logging.error('error in callback')
                logging.error(format_exc())
                [logging.error('TB '+i[:-1]) for i in format_list(elem['stack'])]
        self.queue.task_done()
    def loop(self):
        self.last='just started'
        try: 
            while(self.alive):
                try:
                    self.doNextTask()
                except Queue.Empty:
                    self.lastTime=time.time()
                    try:
                        self.user.trans
                    except Exception,e:
                        logging.warning ('can\'t get reference to transport. abort loop? (%s)'%str(e))
                    else:
                        try:
                            j=self.user.bjid
                            if self.user.trans.users.has_key(self.user.bjid):
                                if self.user.trans.users[self.user.bjid]!=self.user:
                                    logging.error('bad loop (%s). aborting.'%j)
                                    del self.user
                                    return
                            else:
                                #pass
                                logging.warning('queue for offline user? aborting.')
                                del self.user
                                return
                        except:
                            logging.exception('can\'t check user')
                    pass
        except:
            logging.exception('user loop fault\n')
        #print "queue (%s) stopped"%self.user.bjid
        self.last='stopped'
        return 0
class pollManager(object):
    def __init__(self,trans):
        self._thread=threading.Thread(target=self.loop,name="Poll Manager")
        self._thread.daemon=True
        self.watchdog=int(time.time())
        self.alive=1
        self.trans=trans
        self.groupsNum=3
        self.updateInterval=10.0
        self.minUpdateInterval=10./self.groupsNum
        self.maxUpdateInterval=60./self.groupsNum
        self.dynamicInterval=True
        self.dynIntervalSteps=3
        self.dynIntervalMin=0.03
        self.dynIntervalMax=0.2
    
    def start(self):
        self._thread.start()
    
    def loop(self):
        currGroup=0
        self.freeze=False
        skippedCnt=0
        totalCnt=0
        stepsToDecreaseInterval=self.dynIntervalSteps
        while (self.alive):
            try:
                hook.printStats(self.trans)
            except:
                pass
            #logging.warning('poll')
            try:
                ul=[u for u in self.trans.users.keys() if self.trans.hasUser(u) and (self.trans.users[u].loginTime%self.groupsNum==currGroup)]
                #for u in self.trans.users.keys():
                    #if (self.trans.hasUser(u) and (self.trans.users[u].loginTime%self.groupsNum==currGroup)):
                if currGroup==0:
                    skippedCnt=0
                    totalCnt=0
                totalCnt+=len(ul)
                for u in ul:
                    try:
                        upool=self.trans.users[u].pool
                        if(self.trans.users[u].refreshDone):
                            self.trans.users[u].vclient
                            self.trans.users[u].refreshDone=False
                            try:
                                upool.call(self.trans.users[u].refreshData)
                            except gen.QuietError:
                                logging.warning('queue full. resetting refresh flag')
                                self.trans.users[u].refreshDone=True
                            except Exception, e:
                                logging.error('refresh freeze!\n%s'%str(e))
                        else:

                            lastJob=upool.last['foo']
                            qlen=upool.queue.qsize()

                            skippedCnt+=1
                            if (qlen==0):
                                logging.warning('%s: empty queue. dropping refresh state'%
                                                repr(u))
                                self.trans.users[u].refreshDone=True
                                skippedCnt-=1
                            else:
                                logging.warning('skipping refresh for %s [queue: %s last: %s]'%
                                                (repr(u),qlen,lastJob))
                            #logging.warning('%s stack:\n%s'%(u,self.trans.userStack(u)))
                            if ((time.time()-upool.lastTime)>600):
                                logging.warning('%s: user loop freeze!'%u)
                                #self.trans.users[u].logout()
                                #logging.warning('%s: successfully logged out'%u)
                    except gen.NoVclientError:
                        print "user w/o client. skipping"
                    except:
                        logging.exception('')
                
                #print delta
                #if (currGroup==0):
                self.trans.sendMessage(src=self.trans.jid,dest=self.trans.jid,body='ping%s'%time.time())
                currGroup +=1
                currGroup=currGroup%self.groupsNum
                if (currGroup==0):
                    frac=float(skippedCnt)/totalCnt
                    logging.warning('skipped/total = %s'%frac)
                    if (self.dynamicInterval):
                        if (frac>self.dynIntervalMax and 
                            self.updateInterval<self.maxUpdateInterval):
                            self.updateInterval*=1.1
                            logging.warning('increasing update interval to %s'%self.updateInterval) 
                        if (frac<self.dynIntervalMin 
                            and self.updateInterval>self.minUpdateInterval):
                            stepsToDecreaseInterval-=1
                            logging.warning('STDI: %s'%stepsToDecreaseInterval)
                            if (stepsToDecreaseInterval==0):
                                self.updateInterval/=1.1
                                logging.warning('decreasing update interval to %s'%self.updateInterval) 
                                stepsToDecreaseInterval=self.dynIntervalSteps
                        else:
                            stepsToDecreaseInterval=self.dynIntervalSteps
            except:
                logging.exception("GREPME")
            time.sleep(self.updateInterval)
        logging.warning("pollManager stopped")
    def stop(self):
        self.alive=0
class Deferred111(object):
    __slots__=['_cblist']
    _cblist=[]
    def __init__(self):
        _cblist=[]
    def addCallback(self,foo,*args,**kwargs):
        cb=(foo,args,kwargs)
        self._cblist.append(cb)
    def addErrback(self,foo,*args,**kwargs):
        pass
    def callback(self,res):
        for i in self._cblist:
            f,a,k=i
            try:
                f(res,*a,**k)
            except:
                logging.exception('error in deferred\'s callback')
class UserThreadPool(object):
    __slots__=['_threads', '_queues','new_id','_switchQueueLock','trans']
    def __init__(self,trans):
        self.new_id=0
        self._switchQueueLock=threading.Lock()
        self.trans=trans
        self._threads={}
        self._queues=[]
    def stats(self):
        ql=[i.len() for i in self._threads]
        max=ql[0]
        min=ql[0]
        sum=0
        for i in ql:
            if i>max:
                max=i
            if i<min:
                min=i
            sum+=i
        avg=sum/len(ql)
    def selectQueue(self):
        self._queues=[i for i in self._queues if i()]
        qlist=[i for i in self._queues if i().threadId==None]
        #print qlist
        if not qlist:
            return None
        m=qlist[0]().len()
        ret=qlist[0]
        for i in qlist:
            if i().len()>m:
                ret=i
                m=i().len()
        if (m==0):
            return None
        return ret
    def addThread(self):
        nt=threading.Thread(name='userloop %s'%self.new_id,target=self.loop,kwargs={'t_id':self.new_id})
        nt.daemon=True
        self._threads[self.new_id]=nt
        nt.start()
        self.new_id+=1
    def loop(self,t_id):
        logging.warn('userloop %s started'%t_id)
        q=None
        while t_id in self._threads:
            try:
                q().doNextTask(block=False)
                #logging.warning('job done!')
            except (Queue.Empty,TypeError,AttributeError),e:
                #logging.warning('queue empty, looking for job...')
                self._threads[t_id].name='UL%s (NULL)'%t_id
                try:
                    q().threadId=None
                except (AttributeError,TypeError):
                    pass
                q=None
                self._switchQueueLock.acquire()
                #logging.warning('switch lock acquired!')
                try:
                    while not q:
                        q=self.selectQueue()
                        if not q:
                            logging.warning('no matching queues!')
                            time.sleep(1)
                    q().threadId=t_id
                    self._threads[t_id].name='UL%s (%s)'%(t_id,q().bjid)
                    #logging.warn('switched to %s'%q().name)
                except:
                    logging.exception('GREPME switch error')
                self._switchQueueLock.release()
            except:
                logging.exception('')
            pass
        if (q.threadId==t_id):
            q.threadId=None
        else:
            logging.error('thread id mismatch! %s and %s'%(t_id,q.threadId))
        logging.warning('userloop stopped')
    def addQueue(self,q):
        self._queues.append(weakref.ref(q))
class LongpollClient(asyncore.dispatcher):
    urlRe='http://([^/]*)(/.*)'

    def __init__(self, u):
        asyncore.dispatcher.__init__(self)
        url=u.vclient.getLongpollUrl(u.ts)
        host, path= re.match(self.urlRe, url).group(1,0)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect( (host, 80) )
        self._outBuffer = 'GET %s HTTP/1.0\r\n\r\n' % path
        self.inBuf=''
        self._user=u

    def handle_connect(self):
        pass

    def handle_close(self):
        try:
            pos=self.inBuf.find('\r\n\r\n')
            data=self.inBuf[pos+4:]
            try:
                data=demjson.decode(data)
            except demjson.JSONDecodeError:
                logging.warn("bad JSON string: "+repr(data))
                data={'updates':[]}
            self._user.pool.call(self._user.handleUpdate, 
                                 data=data)
        except:
            logging.exception("")
            
        self.close()

    def handle_read(self):
        self.inBuf+=self.recv(8192)

    def writable(self):
        return (len(self._outBuffer) > 0)

    def handle_write(self):
        sent = self.send(self._outBuffer)
        self._outBuffer = self._outBuffer[sent:]

class AsyncoreLooper(object):
    def __init__(self, trans):
        self._thread = threading.Thread(target=self.loop,name="AsyncoreLooper")
        self._thread.daemon = True
        self.trans = trans
        self._thread.start()
    def loop(self):
        while True:
            try:
                logging.warning('entering asyncore loop')
                asyncore.loop(10)
            except:
                logging.exception("")
            logging.warning('asyncore loop exitted')
            time.sleep(1)
        
class counter:
    data={}
    def __init__(self):
        logging.warning('counter.init')
    def add(self,key,val):
        try:
            s,c,m,M=self.data[key]
        except KeyError:
            s=0
            c=0
            m=1000
            M=0
        if (val>M):
            M=val
        if (val<m):
            m=val
        self.data[key]=(s+val, c+1, m, M)
    def toStr (self,sn=0):
        vals=[]
        for j in self.data:
            i=self.data[j]
            vals.append((i[1],i[2],i[3],i[0]/i[1],"%s: min %8.3f max %8.3f avg %8.3f cnt %s"%(j,i[2],i[3],i[0]/i[1],i[1])))
        vals.sort(lambda x, y: cmp(x[sn],y[sn]))
        return '\n'.join([i[3] for i in vals])


