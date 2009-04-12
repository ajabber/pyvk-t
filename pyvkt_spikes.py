# -*- coding: utf-8 -*-
from twisted.python import failure
from twisted.internet import defer
from twisted.python import log, runtime, context, failure
import Queue
import threading,time
from traceback import print_stack, print_exc
from libvkontakte import authFormError
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
    def __init__(self,name=None):
        threading.Thread.__init__(self,target=self.loop,name=name)
        self.daemon=True
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
            except Exception, exc:
                print "Caught exception"
                print_exc()
                print "thread is alive!"
            try:
                elem["deferred"].callback(res)
            except KeyError:
                pass
            self.queue.task_done()
        return 0
class pollManager(threading.Thread):
    def __init__(self,trans):
        self.daemon=True
        threading.Thread.__init__(self,target=self.loop,name="Poll Manager")
        self.alive=1
        self.trans=trans
    def loop(self):
        while (self.alive):
            #print "poll cycle..."
            for u in self.trans.users:
                #print "poll for %s"%u
                if (self.trans.hasUser(u)):
                    try:
                        self.trans.users[u].pool.call(self.trans.users[u].thread.loopIntern)
                    except AttributeError:
                        print_exc()
                        print "this can be caused by incompleted login()"
                    except authFormError:
                        print "%s: got login form"
                        try:
                            self.trans.users[u].pool.call(self.trans.users[u].logout())
                            reactor.callFromThread(self.trans.sendMessage,src=self.trans.jid,dest=u,body=u"Ошибка: возможно, неверный логин/пароль")
                        except:
                            print_exc()
            time.sleep(10)
        
        




