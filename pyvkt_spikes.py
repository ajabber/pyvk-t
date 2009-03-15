# -*- coding: utf-8 -*-
from twisted.python import failure
from twisted.internet import defer
from twisted.python import log, runtime, context, failure
import Queue

def deferToThreadPool(reactor, threadpool, f, *args, **kwargs):
    d = defer.Deferred()
    threadpool.callInThread(threadpool._runWithCallback,d.callback,d.errback,f,args,kwargs)
    return d
