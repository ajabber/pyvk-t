# -*- coding: utf-8 -*-
from twisted.words.protocols.jabber import jid, xmlstream

class cmdManager:
    def __init__(self,trans):
        self.trans=trans
        self.cmdList={"test":basicCommand(trans),"echo":echoCmd(trans)}
    def onMsg(self,jid,text):
        #return "not implemented"
        
        args=text.split(",")
        node=args.pop(0)
        ret="command: '%s', args: %s"%(node,repr(args))
        return ret
        pass
    def onIqSet(self,iq):
        node=iq.command["node"]
        if (self.cmdList.has_key(node)):
            if (iq.command.x!=None):
                args=self.getXdata(iq.command.x)
            else:
                print "empty "
                args={}
            cmd=self.cmdList[node]
            
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
            if (f.name=='field'):
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
        q.command["node"]=iq.query["node"]
        
        try:
            cmd=self.cmdList[iq.query["node"]]
        
            q.addElement("identity").attributes={"name":cmd["name"],"category":"automation","type":"command-node"}
        except:
            q.addElement("identity").attributes={"name":"unknown","category":"automation","type":"command-node"}
        # FIXME!!!!!!!
        q.addElement("feature")["var"]='http://jabber.org/protocol/commands'
        q.addElement("feature")["var"]='jabber:x:data'
        return resp
        pass
    def onDiscoItems(self,iq):
        
        resp=xmlstream.toResponse(iq)
        resp["type"]="result"
        q=resp.addElement("query",'http://jabber.org/protocol/disco#items')
        q["node"]='http://jabber.org/protocol/commands'
        for i in self.cmdList:
            q.addElement("item").attributes={"jid":self.trans.jid, "node":i, "name":self.cmdList[i].name}
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
    def run(self,jid,args,sessid="0"):
        print "basic command: fogm %s with %s"%(jid,repr(args))
        return {"status":"completed","title":u"БУГОГА! оно работает!","message":u"проверка системы команд"}
class echoCmd(basicCommand):
    name="echo command"
    args={1:"text"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    
    def run(self,jid,args,sessid="0"):
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

