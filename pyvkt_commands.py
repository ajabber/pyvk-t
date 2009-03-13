# -*- coding: utf-8 -*-
from twisted.words.protocols.jabber import jid, xmlstream
from twisted.internet.defer import waitForDeferred
#from pyvkt_new import bareJid
def bareJid(jid):
    n=jid.find("/")
    if (n==-1):
        return jid
    return jid[:n]
class cmdManager:
    def __init__(self,trans):
        self.trans=trans
        self.cmdList={"test":basicCommand(trans),"echo":echoCmd(trans),'setstatus':setStatusCmd(trans)}
        self.transportCmdList={"test":basicCommand(trans),"echo":echoCmd(trans),'setstatus':setStatusCmd(trans),
            "login":loginCmd(trans),"logout":logoutCmd(trans)}
        self.contactCmdList={}
        self.adminCmdList={}
        self.admin=trans.admin
    def onMsg(self,jid,text,to_id=0):
        #return "not implemented"
        cmdList=self.transportCmdList
        cl=text.find(" ")
        if (cl==-1):
            args=[]
            node=text
        else:
            args=text[cl+1:].split(",")
            node=text[:cl]
        if (node=='list'):
            return repr(cmdList.keys())
        ret="command: '%s', args: %s"%(node,repr(args))
        if (cmdList.has_key(node)):
            cmd=cmdList[node]
            ar=self.assignArgs(cmd,args)
            print jid
            print "command: '%s', args: %s"%(node,repr(ar))
            
            res=cmd.run(jid,ar)
            print "cmd done"
            ret="[%s]\n%s"%(res["title"],res["message"])
        else:
            return "unknown command: %s"%node
        return ret
        pass
    def assignArgs(self,cmd,args):
        ret={}
        for i in cmd.args:
            try:
                ret[cmd.args[i]]=args[i]
            except IndexError:
                print("args error")
                return {}
        return ret
    def onIqSet(self,iq):
        node=iq.command["node"]
        cmdList=self.transportCmdList
        if (cmdList.has_key(node)):
            if (iq.command.x!=None):
                args=self.getXdata(iq.command.x)
            else:
                print "empty "
                args={}
            cmd=cmdList[node]
            
            res=cmd.run(iq["from"],args,0)
            resp=xmlstream.toResponse(iq)
            resp["type"]="result"
            c=resp.addElement("command",'http://jabber.org/protocol/commands')
            c["node"]=node
            c["status"]=res["status"]
            c["sessionid"]='0'
            x=c.addElement("x",'jabber:x:data')
            
            if (res.has_key("form")):
                act=c.addElement("actions")
                act["execute"]="next"
                act.addElement("next")
                x["type"]="form"
            else:
                x["type"]="result"
            try:
                x.addElement("title").addContent(res["title"])
            except:
                x.addElement("title").addContent(u"result")
            try:
                x.addElement("instructions").addContent(res["message"])
            except:
                pass
            try:
                fields=res["form"]["fields"]
                for i in fields:
                    x.addElement("field").attributes={"type":"text-single", 'var':i,'label':i}
            except:
                pass
            return resp
        else:
            #FIXME error strnza
            pass
    def getXdata(self,x):
        print("xdata")
        print(x.toXml())
        #x=elem.x
        ret={}
        if (x==None):
            print "none"
            return ret
        #TODO check namespace
        for f in x.children:
            if (type(f)!=unicode and f.name=='field'):
                try:
                    ret[f['var']]=f.value.children[0]
                except:
                    print("bad field: %s"%f.toXml())
        print "got ",ret
        return ret
    def onDiscoInfo(self,iq):
        resp=xmlstream.toResponse(iq)
        resp["type"]="result"
        q=resp.addElement("query",'http://jabber.org/protocol/disco#info')
        q["node"]=iq.query["node"]
        cmdList={}
        if (iq["to"]==self.trans.jid):
            cmdList=self.transportCmdList
        try:
            cmd=cmdList[iq.query["node"]]
        
            q.addElement("identity").attributes={"name":cmd["name"],"category":"automation","type":"command-node"}
        except:
            q.addElement("identity").attributes={"name":"unknown","category":"automation","type":"command-node"}
        # FIXME!!!!!!!
        q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
        q.addElement("feature")["var"]='jabber:x:data'
        return resp
        pass
    def onDiscoItems(self,iq):
        cmdList={}
        if (iq["to"]==self.trans.jid):
            cmdList=self.transportCmdList
        resp=xmlstream.toResponse(iq)
        resp["type"]="result"
        q=resp.addElement("query",'http://jabber.org/protocol/disco#items')
        q["node"]='http://jabber.org/protocol/commands'
        for i in cmdList:
            q.addElement("item").attributes={"jid":self.trans.jid, "node":i, "name":cmdList[i].name}
        return resp
class basicCommand:
    name="basic commnd"
    def __init__(self,trans):
        self.trans=trans
    def onMsg(self,jid,text):
        #return "not implemented"
        args=text.split(",")
        ret="command: '%s', args: %s"%(node,repr(args))
        return ret
        pass
    def run(self,jid,args,sessid="0",to_id=0):
        print "basic command: fogm %s with %s"%(jid,repr(args))
        return {"status":"completed","title":u"БУГОГА! оно работает!","message":u"проверка системы команд"}
class echoCmd(basicCommand):
    name="echo command"
    args={0:"text"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        print("echo from %s"%jid)
        print(args)
        try:
            self.trans.sendMessage(self.trans.jid,jid,args["text"])
        except KeyError:
            try:
                self.trans.sendMessage(self.trans.jid,jid,args[1])
            except:
                return {"status":"executing","title":u"echo command","form":{"fields":["text"]}}
        return {"status":"copleted","title":u"echo command",'message':'completed!'}
class setStatusCmd(basicCommand):
    name=u"Задать статус"
    args={0:"text"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        print("echo from %s"%jid)
        bjid=bareJid(jid)
        print(args)
        if (args.has_key("text")):
            print ("setting status...")
            #FIXME "too fast" safe!!!
            if (self.trans.threads.has_key(bjid)):
                print ("setting status...")
                self.trans.threads[bjid].setStatus(args["text"])
                print ("done")
            else:
                #print ("done")
                return {"status":"copleted","title":u"Установка статуса",'message':u'Не получилось.\nСкорее всего, вам надо подключиться (команда /login)'}
            print ("done")
        else:
            return {"status":"executing","title":u"Установка статуса","form":{"fields":["text"]},'message':u'Введите статус'}
        return {"status":"copleted","title":u"Установка статуса",'message':u'Похоже, статус установлен'}
class loginCmd(basicCommand):
    name=u"Подключиться"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=bareJid(jid)
        self.trans.login(bjid)
        return {"status":"copleted","title":u"Подключение",'message':u'Производится подключение...'}
class logoutCmd(basicCommand):
    name=u"Отключиться"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=bareJid(jid)
        self.trans.logout(bjid)
        return {"status":"copleted","title":u"Отключение",'message':u'Производится отключение...'}
        