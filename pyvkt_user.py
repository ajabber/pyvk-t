# -*- coding: utf-8 -*-
import libvkontakte
from twisted.python.threadpool import ThreadPool
import pyvkt_global as pyvkt
class user:
    def __init__(self,trans,jid):
        bjid.pyvkt.bareJid(jid)
        self.trans=trans
        self.bjid=bjid
        self.resources=[jid]
        pass
    def addResource(self,jid):
        if (jid in self.resources):
            pass
        else:
            self.resources.append(jid)
            #TODO resend presence
    def delResource(self,jid):
        if (jid in self.resources):
            self.resources.remove(jid)
        #TODO any resources left?
    def createThread(self,jid,email,pw):
        jid=bareJid(jid)
        self.thread=vkonThread(cli=self,jid=jid,email=email,passw=pw)
        del self.locks[jid]
        self.pool=ThreadPool(1,1)
        self.pool.start()
        self.thread.start()
        self.thread.feedOnly=0
    def login(self):
        # TODO bare jid?
        if (self.trans.isActive==0 and bareJid(jid)!=self.trans.admin):
            #log.msg("isActive==0, login attempt aborted")
            self.jrans.sendMessage(self.trans.jid,bjid,u"В настоящий момент транспорт неактивен, попробуйте подключиться позже")
            #WARN bjid?
            return
        if (self.lock==1):
            return
        #TODO locks?
        self.lock=1
        mq="SELECT * FROM users WHERE jid='%s'"%safe(bareJid(jid))
        #log.msg(mq)
        q=self.trans.dbpool.runQuery(mq)
        q.addCallback(self.login1)
    def login1(self,data):
        t=data[0]
        bjid=data[0][0].lower()
        defer.execute(self.createThread,jid=bjid,email=data[0][1],pw=data[0][2])
        try:
            if (data[0][3]==" "):
                self.config={}
            self.config=cPickle.loads(b64decode(data[0][3]))
            print 'got config',self.config
        except:
            self.config={}
            log.msg("config field not found! please add it to your database (see pyvk-t_new.sql for details)")
        
        p = self.trans.foregroundPresence(bjid)
        if p:
            self.trans.sendPresence(self.trans.jid,bjid,status=p["status"],show=p["show"])
            #FIXME "too fast"!!
            self.pool.callInThread(self.updateStatus,bjid=bjid,text=p["status"])
        else:
            self.trans.sendPresence(self.trans.jid,bjid)

    def loginFailed(self,data,jid):
        msg.log("login failed for %s"%jid)
        del self.thread
    def logout(self,bjid):
        try:
            defer.execute(self.thread.logout).addCallback(self.delThread,bjid=bjid)
        except KeyError:
            pass
        try:
            self.pools[jid].stop()
            del self.pools[jid]
        except KeyError:
            pass
        try:
            del self.usrconf[bjid]
        except KeyError:
            pass
    def delThread(self):
        del self.thread
    def hasReource(self,jid):
        """
        return 1 if
            bare jid set and has any resources available
            full jid set and is available
        otherwise returns 0 
        """
        bjid=bareJid(jid)
        #barejid - just check if any resources available
        if jid==bjid and self.resources.has_key(bjid) and len(self.resources[bjid]):
            return 1
        #full jid - check for certain resource
        if jid!=bjid and self.resources.has_key(bjid) and self.resources[bjid].has_key(jid):
            return 1
        #nothing
        return 0

        
        
        
        
        
        
        
        
        
        
        
