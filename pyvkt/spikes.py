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
#from twisted.python import failure
from twisted.internet import reactor
from twisted.internet.defer import Deferred
#from twisted.python import log, runtime, context, failure
import Queue
import threading,time,logging
from traceback import print_stack, print_exc,format_exc,extract_stack,format_list
from libvkontakte import authFormError,HTTPError,UserapiSidError, tooFastError
import pyvkt.general as gen
import cProfile as prof
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
        
def deferToThreadPool(reactor, threadpool, f, *args, **kwargs):
    #WARN "too fast"?
    print "deprecated deferToThreadPool"
    print "this in NOT an ERROR!"
    print_stack(limit=2)
    return threadpool.defer(f,**kwargs)
    
    d = defer.Deferred()
    threadpool.callInThread(threadpool._runWithCallback,d.callback,d.errback,f,args,kwargs)
    return d
class reqQueue(threading.Thread):
    daemon=True
    def __init__(self,user,name=None):
        self.daemon=True
        try:
            threading.Thread.__init__(self,target=self.loop,name=name)
        except UnicodeEncodeError:
            threading.Thread.__init__(self,target=self.loop,name="user_with_bad_jid")
        self.user=user
        self.queue=Queue.Queue(200)
        self.alive=1
        self.ptasks={}
    def callInThread(self,foo,**kw):
        print "deprecated callInThread"
        print "this in NOT an ERROR!"
        print_stack(limit=2)
        self.call(foo,**kw)
    def call(self,foo,**kw):
        elem={"foo":foo,"args":kw,'stack':extract_stack()}
        self.queue.put(elem)
    def defer(self,f,**kw):
        d=Deferred()
        elem={"foo":f,"args":kw,"deferred":d,'stack':extract_stack()}
        self.queue.put(elem)
        return d
    def stop(self):
        self.alive=0
        self.call(self.dummy)
        self.user=None
    def dummy(self):
        return

    def loop(self):
        while(self.alive):
            try:
                elem=self.queue.get(block=True,timeout=10)
            except Queue.Empty:
                pass
            else:
                f=elem["foo"]
                args=elem["args"]
                try:
                    res=f(**args)
                except authFormError:
                    logging.warn("%s: got login form")
                    try:
                        self.alive=0
                        self.user.logout()
                        reactor.callFromThread(self.user.trans.sendMessage,src=self.user.trans.jid,dest=self.user.bjid,body=u"Ошибка: возможно, неверный логин/пароль")
                    except:
                        logging.error(format_exc())
                except gen.NoVclientError:
                    if (self.user):
                        logging.error("err: no vClient (%s)"%repr(self.user.bjid))
                    else:
                        logging.warning("loop: self.user==None. aborting")
                        return
                except HTTPError,e:
                    logging.error("http error: "+str(e).replace('\n',', '))
                except UserapiSidError:
                    logging.error('userapi sid error (%s)'%self.user.bjid)
                except tooFastError:
                    logging.warning('FIXME "too fast" error stranza')
                except Exception, exc:
                    logging.error(format_exc())
                    logging.error('task traceback:')
                    [logging.error('TB '+i[:-1]) for i in format_list(elem['stack'])]
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
        return 0
class pollManager(threading.Thread):
    def __init__(self,trans):
        threading.Thread.__init__(self,target=self.loop,name="Poll Manager")
        self.daemon=True
        self.watchdog=int(time.time())
        self.alive=1
        self.trans=trans
    def loop(self):
        pollInterval=15
        groupsNum=5
        currGroup=0
        self.freeze=False
        while (self.alive):
            #print "poll", len(self.trans.users.keys()), 'user(s)'
            #delta=int(time.time())-self.watchdog
            #print 'out traffic %sK'%(self.trans.logger.bytesOut/1024)

            #if (delta>60):
                #print 'freeze detected!\nupdates temporary disabled'
                #print 'users online: %s'%len(self.trans.users)
                #for i in [5,10,30,60,120,300]:
                    #print '%s sec traffic: '%i,self.trans.logger.getTraffic(i)
                #if (delta>1200):
                    #print 'critical freeze. shutting down'
                    #self.trans.isActive=0
                    #self.trans.stopService()
                    #self.alive=0
                    #f=open('killme','w')
                    #f.write('1')
                    #f.close()
            #else:
            for u in self.trans.users.keys():
                if (self.trans.hasUser(u) and (self.trans.users[u].loginTime%groupsNum==currGroup)):
                    try:
                        if(self.trans.users[u].refreshDone):
                            self.trans.users[u].vclient
                            self.trans.users[u].refreshDone=False
                            self.trans.users[u].pool.call(self.trans.users[u].refreshData)
                    except gen.noVclientError:
                        print "user w/o client. skipping"
                    except:
                        logging.error(format_exc())
            #print delta
            if (currGroup==0):
                #print 'echo sent'
                self.trans.sendMessage(src=self.trans.jid,dest=self.trans.jid,body='%s'%int(time.time()))
            #print '10 sec traffic: ',self.trans.logger.getTraffic(10)                
            #print "cg",currGroup
            currGroup +=1
            currGroup=currGroup%groupsNum
            time.sleep(5)
        print "pollManager stopped"
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




