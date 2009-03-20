# -*- coding: utf-8 -*-
from twisted.python import failure
from twisted.internet import defer
from twisted.python import log, runtime, context, failure
import Queue
import threading
from traceback import print_stack
def deferToThreadPool(reactor, threadpool, f, *args, **kwargs):
    #WARN "too fast"?
    print "deprecated deferToThreadPool"
    print "this in NOT ERROR!"
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
        print "this in NOT ERROR!"
        print_stack(limit=2)
        self.call(foo,**kw)
    def call(self,foo,**kw):
        elem={"foo":foo,"args":kw}
        self.queue.put(elem)
    def defer(self,foo,**kw):
        d=defer.Deferred()
        elem={"foo":foo,"args":kw,"deferred":d}
        self.queue.put(elem)
        return d
    def stop(self):
        self.alive=0
    def loop(self):
        while(self.alive):
            print "waiting for task"
            elem=self.queue.get(block=True)
            f=elem["foo"]
            args=elem["args"]
            res=f(**args)
            try:
                elem["deferred"].callback(res)
            except KeyError:
                pass
        return 0
