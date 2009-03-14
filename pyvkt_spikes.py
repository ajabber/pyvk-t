# -*- coding: utf-8 -*-
from twisted.python import failure
from twisted.internet import defer
from twisted.python import log, runtime, context, failure
import Queue
def callInThreadWithCallback(pool, onResult, func, *args, **kw):
    if pool.joined:
        return
    ctx = context.theContextTracker.currentContext().contexts[-1]
    o = (ctx, func, args, kw, onResult)
    pool.q.put(o)
    if pool.started:
        pool._startSomeWorkers()

def deferToThreadPool(reactor, threadpool, f, *args, **kwargs):
    d = defer.Deferred()
    def onResult(success, result):
        if success:
            reactor.callFromThread(d.callback, result)
        else:
            reactor.callFromThread(d.errback, result)
    callInThreadWithCallback(threadpool,onResult, f, *args, **kwargs)
    return d
