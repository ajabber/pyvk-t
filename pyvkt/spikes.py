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
from traceback import print_stack, print_exc,format_exc,extract_stack,format_list
from libvkontakte import authFormError,HTTPError,UserapiSidError, tooFastError, PrivacyError, captchaError,UserapiJsonError
import pyvkt.general as gen
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
        
class reqQueue(threading.Thread):
    #daemon=True
    last='not started'
    lastTime=0
    def __init__(self,user,name=None):
        try:
            threading.Thread.__init__(self,target=self.loop,name=name)
        except UnicodeEncodeError:
            threading.Thread.__init__(self,target=self.loop,name="user_with_bad_jid")
        self.daemon=True
        self.user=user
        self.queue=Queue.Queue(400)
        self.alive=1
        self.ptasks={}
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
        
        qs=self.queue.qsize()
        logging.error('pool[%s]: queue full (%s)! timeout: %i \n*\t\tlast task: %80s, curr task: %80s'%(qs,self.name,t,self.last['foo'],repr(ct)))
        
    def stop(self):
        self.alive=0
        self.call(self.dummy)
        self.user=None
    def dummy(self):
        return
    def loopWrapper(self):
        #if 'eqx@eqx.su' in self.name:
        #    l=self.loop
        #    prof.runctx('l()',globals(), locals(), 'profile_%s'%time.time())
        #else:
            self.loop()
    def loop(self):
        self.last='just started'
        while(self.alive):
            try:
                elem=self.queue.get(block=True,timeout=10)
                self.last=elem
            except Queue.Empty:
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
            else:
                f=elem["foo"]
                last=repr(f)
                args=elem["args"]
                try:
                    self.lastTime=time.time()
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
                except captchaError:
                    self.user.trans.sendMessage(src=self.user.trans.jid,dest=self.user.bjid, body=u'Запрошенная операция не может быть выполнена из-за captcha-защиты на юзерапи. На данный момент обработка captcha не реализована.')
                except HTTPError,e:
                    logging.error("http error: "+str(e).replace('\n',', '))
                except UserapiSidError:
                    logging.error('userapi sid error (%s)'%self.user.bjid)
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
                        [logging.error('TB '+i) for i[:-1] in format_list(elem['stack'])]
                self.queue.task_done()
        #print "queue (%s) stopped"%self.user.bjid
        self.last='stopped'
        return 0
class pollManager(threading.Thread):
    def __init__(self,trans):
        threading.Thread.__init__(self,target=self.loop,name="Poll Manager")
        self.daemon=True
        self.watchdog=int(time.time())
        self.alive=1
        self.trans=trans
        self.updateInterval=30
        self.groupsNum=3
    def loop(self):
        pollInterval=5
        currGroup=0
        self.freeze=False
        while (self.alive):
            try:
                hook.printStats(self.trans)
            except:
                pass
            #logging.warning('poll')
            try:
                for u in self.trans.users.keys():
                    if (self.trans.hasUser(u) and (self.trans.users[u].loginTime%self.groupsNum==currGroup)):
                        try:
                            if(self.trans.users[u].refreshDone):
                                self.trans.users[u].vclient
                                self.trans.users[u].refreshDone=False
                                try:
                                    self.trans.users[u].pool.call(self.trans.users[u].refreshData)
                                except gen.QuietError:
                                    logging.warning('queue full. resetting refresh flag')
                                    self.trans.users[u].refreshDone=True
                                except Exception, e:
                                    logging.error('refresh freeze!\n%s'%str(e))
                            else:
                                logging.warning('skipping refresh for %s'%repr(u))
                                pass
                        except gen.NoVclientError:
                            print "user w/o client. skipping"
                        except:
                            logging.exception('')
                #print delta
                if (currGroup==0):
                    self.trans.sendMessage(src=self.trans.jid,dest=self.trans.jid,body='%s'%int(time.time()))
                currGroup +=1
                currGroup=currGroup%self.groupsNum
            except:
                logging.exception("GREPME")
            time.sleep(self.updateInterval)
        logging.warning("pollManager stopped")
    def stop(self):
        self.alive=0
#class Deferred1:
    #cblist=[]
    #def addCallback(self,foo,*args,**kwargs):
        #cb=(foo,args,kwargs)
        #self.cblist.append(cb)
    #def addErrback(self,foo,*args,**kwargs):
        #pass
    #def callback(self,res):
        #for i in self.cblist:
            #f,a,k=i
            #try:
                #f(res,*a,**k)
            #except:
                #logging.error(format_exc())
#class ThreadPool:
    #threads=[]
    #active=True
    #def __init__(self,threadNum=1,name='pool'):
        #self.q=Queue()
        
        #for i in range(threadNum):
            #t=Thread(name='%s[%s]'%(name,i),target=self.loop)
            #t.daemon=True
            #threads.append(t)
    #def start(self):
        #[t.start() for t in threads]
    #def stop(self):
        #self.active=False
    #def loop(self):
        #while(self.active):
            #try:
                #task=q.get(block=True,timeout=5)
            #except Queue.Empty:
                #pass
            #else:
                #d,f,k=task
                #try:
                    #res=f(**k)
                    #if (d):
                        #d.callback(res)
                #except:
                    #logging.error("unhandled exception:\n"+format_exc())
    #def defer(self,foo,**kw):
        #d=Deferred()
        #el=(d,foo,kw)
        #q.append(el)
        #return d
    #def call(self,foo,**kw):
        #el=(None,foo,kw)
        #q.append(el)
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


