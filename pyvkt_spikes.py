# -*- coding: utf-8 -*-
from twisted.python import failure
from twisted.internet import defer
from twisted.python import log, runtime, context, failure
import Queue
import threading
from traceback import print_stack, print_exc
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
    def __init__(self):
        threading.Thread.__init__(self,target=self.loop)
        self.daemon=True
        self.queue=Queue.Queue(200)
        self.alive=1
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
        print "dummy"
        pass
    def loop(self):
        while(self.alive):
            print "waiting for task"
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
        return 0
