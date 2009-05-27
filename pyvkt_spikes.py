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
from twisted.python import failure
from twisted.internet import defer,reactor
from twisted.python import log, runtime, context, failure
import Queue
import threading,time
from traceback import print_stack, print_exc
from libvkontakte import authFormError
import pyvkt_global as pyvkt
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
        elem={"foo":foo,"args":kw}
        self.queue.put(elem)
    def defer(self,f,**kw):
        d=defer.Deferred()
        elem={"foo":f,"args":kw,"deferred":d}
        self.queue.put(elem)
        return d
    def stop(self):
        self.alive=0
        self.call(self.dummy)
    def dummy(self):
        return
    def loop(self):
        while(self.alive):
            elem=self.queue.get(block=True)
            f=elem["foo"]
            args=elem["args"]
            try:
                res=f(**args)
            except authFormError:
                print "%s: got login form"
                try:
                    self.alive=0
                    self.user.logout()
                    reactor.callFromThread(self.user.trans.sendMessage,src=self.user.trans.jid,dest=self.user.bjid,body=u"Ошибка: возможно, неверный логин/пароль")
                except:
                    print_exc()
            except pyvkt.noVclientError:
                print "err: no vClient (%s)"%repr(self.user.bjid)
            except Exception, exc:
                print "Caught exception"
                print_exc()
                print "thread is alive!"
            else:
                try:
                    elem["deferred"].callback(res)
                except KeyError:
                    pass
                except:
                    print "GREPME unhandled exception in callback"
                    print_exc()
            self.queue.task_done()
        #print "queue (%s) stopped"%self.user.bjid
        return 0
class pollManager(threading.Thread):
    def __init__(self,trans):
        self.daemon=True
        threading.Thread.__init__(self,target=self.loop,name="Poll Manager")
        self.alive=1
        self.trans=trans
    def loop(self):
        while (self.alive):
            #print "poll", len(self.trans.users.keys()), 'user(s)'
            for u in self.trans.users.keys():
                #print "poll for %s"%u
                if (self.trans.hasUser(u)):
                    try:
                        if(self.trans.users[u].refreshDone):
                            self.trans.users[u].vclient
                            self.trans.users[u].refreshDone=False
                            self.trans.users[u].pool.call(self.trans.users[u].refreshData)
                    except pyvkt.noVclientError:
                        print "user w/o client. skipping"
                    except:
                        print "GREPME: unhandled exception"
                        print_exc()
            time.sleep(15)
        print "pollManager stopped"
    def stop(self):
        self.alive=0
    def __del__(self):
        self.alive=0
        threading.Thread.exit(self)
        




