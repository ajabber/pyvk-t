# -*- coding: utf-8 -*-
from twisted.words.protocols.jabber import jid, xmlstream
from twisted.internet.defer import waitForDeferred
#try:
    #from twisted.internet.threads import deferToThreadPool
#except:
from pyvkt_spikes import deferToThreadPool
from traceback import print_stack
import pyvkt_global as pyvkt


class cmdManager:
    def __init__(self,trans):
        self.trans=trans
        self.cmdList={"echo":echoCmd(trans),'setstatus':setStatusCmd(trans)}
        self.transportCmdList={"echo":echoCmd(trans),
                'setstatus':setStatusCmd(trans),
                "login":loginCmd(trans),
                "logout":logoutCmd(trans),
                "config":setConfigCmd(trans)}
        self.contactCmdList={"history":getHistioryCmd(trans),"wall":sendWallMessageCmd(trans),"friend":addDelFriendCmd(trans)}
        self.adminCmdList={}
        self.admin=trans.admin
    def makeCmdList(self,s_jid,v_id):
        ret={}
        bjid=pyvkt.bareJid(s_jid)
        #print bjid,v_id
        if (v_id==0):
            for i in self.transportCmdList:
                ret[i]=self.transportCmdList[i]
            if (bjid==self.admin):
                for i in self.adminCmdList:
                    ret[i]=self.adminCmdList[i]
        else:
            for i in self.contactCmdList:
                ret[i]=self.contactCmdList[i]
        #print ret
        return ret
    def onMsg(self,jid,text,v_id=0):
        #print "command:", text
        cmdList=self.makeCmdList(jid,v_id)
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
            ar=cmd.assignArgs(args)
            #print jid
            #print "command: '%s', args: %s"%(node,repr(ar))
            
            res=cmd.run(jid,ar,to_id=v_id)
            try:
                txt=res["message"]
            except:
                txt=' '
            if (res.has_key("form")):
                f=cmd.reprForm(res["form"])
                txt="%s\n%s"%(txt,f)
            #print "cmd done"
            ret="[cmd:%s]\n%s"%(res["title"],txt)
        else:
            return "unknown command: %s"%node
        return ret
        pass
    def onIqSet(self,iq):
        node=iq.command["node"]
        v_id=pyvkt.jidToId(iq["to"])
        cmdList=self.makeCmdList(iq["from"],v_id)
        #cmdList=self.transportCmdList
        if (cmdList.has_key(node)):
            if (iq.command.x!=None):
                args=self.getXdata(iq.command.x)
            else:
                #print "empty "
                args={}
            cmd=cmdList[node]
            
            res=cmd.run(iq["from"],args,to_id=v_id)
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
                    try:
                        ft=fields[i][0]
                    except IndexError:
                        ft='text-single'
                    try:
                        fd=fields[i][1]
                    except IndexError:
                        fd=i
                    try:
                        val=fields[i][2]
                        #print "val=",val
                        if (val==True):
                            val='1'
                        elif(val==False):
                            val='0'
                        #FIXME
                    except IndexError:
                        #print "initial value isn't set"
                        val=''

                    f=x.addElement("field")
                    f.attributes={"type":ft, 'var':i,'label':fd}
                    f.addElement("value").addContent(val)
            except KeyError:
                pass
            return resp
        else:
            #FIXME error strnza
            pass
    def getXdata(self,x):
        #print("xdata")
        #print(x.toXml().encode("ascii","replace"))
        #x=elem.x
        ret={}
        if (x==None):
            #print "none"
            return ret
        #TODO check namespace
        for f in x.children:
            if (type(f)!=unicode and f.name=='field'):
                ret[f['var']]=f.value.children[0]
        #print "got ",ret
        return ret
    def onDiscoInfo(self,iq):
        v_id=pyvkt.jidToId(iq["to"])
        cmdList=self.makeCmdList(iq["from"],v_id)
        resp=xmlstream.toResponse(iq)
        resp["type"]="result"
        q=resp.addElement("query",'http://jabber.org/protocol/disco#info')
        q["node"]=iq.query["node"]
        cmdList={}
        #if (iq["to"]==self.trans.jid):
            #cmdList=self.transportCmdList
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
        #if (iq["to"]==self.trans.jid):
            #cmdList=self.transportCmdList
        v_id=pyvkt.jidToId(iq["to"])
        cmdList=self.makeCmdList(iq["from"],v_id)
        resp=xmlstream.toResponse(iq)
        resp["type"]="result"
        q=resp.addElement("query",'http://jabber.org/protocol/disco#items')
        q["node"]='http://jabber.org/protocol/commands'
        for i in cmdList:
            q.addElement("item").attributes={"jid":iq["to"], "node":i, "name":cmdList[i].name}
        return resp

class basicCommand:
    name="basic commnd"
    def __init__(self,trans):
        self.trans=trans
    def reprForm(self,form):
        ret=u"jabber:x:data\nfields:"
        try:
            ftype=form["type"]
        except:
            ftype='form'
        if (ftype=='form'):
            ret=u'[Аргументы]'
        for i in form["fields"]:
            try:
                ft=form['fields'][i][0]
            except IndexError:
                print "WARN: deprecated form description"
                ft='text-single'
            except TypeError:
                print "WARN: deprecated form description!"
                return ''
            try:
                fd=form['fields'][i][1]
            except IndexError:
                print "WARN: deprecated form description"
                fd=''
            try:
                val=form['fields'][i][2]
            except IndexError:
                print "initial value isn't set"
                val=''
            #fe=u'%s: %s - %s'%(i,ft,fd)
            fe=u"%s='%s': %s"%(i,val,fd)
            ret="%s\n%s"%(ret,fe)
        return ret
    def assignArgs(self,args):
        ret={}
        for i in self.args:
            try:
                ret[self.args[i]]=args[i]
            except IndexError:
                print("args error")
                return {}
        return ret
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
                return {"status":"executing","title":u"echo command","form":{"fields":{"text":("text-single",u"Текст")}}}
        return {"status":"completed","title":u"echo command",'message':'completed!'}

class setStatusCmd(basicCommand):
    name=u"Задать статус"
    args={0:"text"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        if (args.has_key("text")):
            #FIXME "too fast" safe!!!
            if (self.trans.hasUser(bjid)):
                self.trans.users[bjid].thread.setStatus(args["text"])
            else:
                #print ("done")
                return {"status":"completed","title":u"Установка статуса",'message':u'Не получилось.\nСкорее всего, вам надо подключиться (команда /login)'}
        else:
            return {"status":"executing","title":u"Установка статуса","form":{"fields":{"text":('text-single',u'Статус')}},'message':u'Введите статус'}
        self.trans.users[bjid].VkStatus = args["text"]
        return {"status":"completed","title":u"Установка статуса",'message':u'Похоже, статус установлен (%s)'%args["text"]}

class loginCmd(basicCommand):
    name=u"Подключиться"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        if (self.trans.isActive==0 and bjid!=self.trans.admin):
            return {"status":"completed","title":u"Подключение",'message':u"В настоящий момент транспорт неактивен, попробуйте подключиться позже"}
        self.trans.addResource(jid)
        print "resources: ",self.trans.users[bjid].resources
        return {"status":"completed","title":u"Подключение",'message':u'Производится подключение...'}

class logoutCmd(basicCommand):
    name=u"Отключиться"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        if(self.trans.hasUser(bjid)):
            self.trans.users[bjid].logout()
        return {"status":"completed","title":u"Отключение",'message':u'Производится отключение...'}

class getHistioryCmd(basicCommand):
    name=u"История переписки"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        if (to_id==0):
            print "where is id???"
            return {"status":"completed","title":self.name,'message':u'ПукЪ'}
        hist=self.trans.users[bjid].thread.getHistory(to_id)
        msg=u''
        for t,m in hist:
            msg=u'%s\n%s: %s'%(msg,t,m)
        return {"status":"completed","title":self.name,'message':msg}

class sendWallMessageCmd(basicCommand):
    name=u"Отправить сообщение на стену"
    args={0:"text"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        if (to_id==0):
            print "where is id???"
            return {"status":"completed","title":self.name,'message':u'ПукЪ'}
        print(args)
        if (args.has_key("text")):
            #print ("sending wall message...")
            #FIXME "too fast" safe!!!
            if (self.trans.hasUser(bjid)):
                #print ("sending wall message...")
                res=self.trans.users[bjid].thread.sendWallMessage(to_id,args["text"])
                if res==1:
                    return {"status":"completed","title":u"Отправка на стену",'message':u'Ошибка сети'}
                elif res==2:
                    return {"status":"completed","title":u"Отправка на стену",'message':u'Ошибка. Возможно запись на стену запрещена.'}
                elif res!=0:
                    return {"status":"completed","title":u"Отправка на стену",'message':u'Неизвестная ошибка.'}

                #print ("done")
            else:
                #print ("done")
                return {"status":"completed","title":u"Отправка на стену",'message':u'Не получилось.\nСкорее всего, вам надо подключиться (команда /login)'}
            #print ("done")
        else:
            return {"status":"executing","title":u"Отправка на стену","form":{"fields":{"text":('text-single',u'Сообщение','')}},'message':u'Введите текст сообщения для отправки на стену'}
        return {"status":"completed","title":u"Отправка на стену",'message':u'Похоже, сообщение отправлено'}
class setConfigCmd(basicCommand):
    name=u"Настройки транспорта"
    args={0:"test"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def assignArgs(self,args):
        if (len(args)!=2):
            return {}
        return {args[0]:args[1]}
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        #print(args)
        cf=pyvkt.userConfigFields
        try:
            user=self.trans.users[bjid]
        except KeyError:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}

        if (len(args)):
            #try:
            if (type(user.config)==bool):
                print "someone fucked our config"
                user.config={}
            for i in args:
                if cf.has_key(i):
                    if cf[i]["type"]=="boolean":
                        user.config[i]=args[i]=="1"
                    else:
                        user.config[i]=args[i]
            nc=str(user.config)
            #print nc
            self.trans.saveConfig(bjid)
            #except KeyError:
                #print "keyError"
                #nc="[void]"
            return {"status":"completed","title":self.name,'message':u'вот тут настройки должны были бы сохраниться\n%s'%nc}
            
        else:
            fl={}
            for i in cf:
                #print "field ",i
                val=user.getConfig(i)
                fl[i]=(cf[i]["type"],cf[i]["desc"],val)
            #print "fieldList: ",fl
            return {"status":"executing","title":self.name,"form":{"fields":fl},'message':u''}
class addDelFriendCmd(basicCommand):
    name=u"Добавить/удалить друга"
    args={0:"confirm"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=pyvkt.bareJid(jid)
        try:
            user=self.trans.users[bjid]
        except KeyError:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}
        isFriend=self.trans.users[bjid].thread.isFriend(to_id)
        #TODO run in pool?
        if (isFriend==-1):
            return {"status":"completed","title":self.name,'message':u'Внутренняя ошибка транспорта'}
            #TODO exceptions?
            #FIXME not 'completed'
        if (len(args)!=1):
            fl={"confirm":("boolean",u'Подтверждение',"0")}
            if(isFriend):
                return {"status":"executing","title":u'Удаление из списка друзей',"form":{"fields":fl},
                    'message':u'Пользователь будет УДАЛЕН из списка друзей на сайте, не в транспорте, а именно на сайте!'}
            else:
                return {"status":"executing","title":u'Добавление в список друзей',"form":{"fields":fl},
                    'message':u'Будет отправлено приглашене стать другом или подтверждено полученное приглашение'}
        if (args.has_key("confirm") and args["confirm"]=='1'):
            user.thread.addDeleteFriend(to_id,not isFriend)
            return {"status":"completed","title":self.name,'message':u'Вроде, готово.'}
            pass
        else:
            return {"status":"completed","title":self.name,'message':u'Операция отменена'}

