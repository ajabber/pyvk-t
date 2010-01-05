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
from traceback import print_stack, print_exc
import pyvkt.general as gen
import time,string,logging
from comstream import createElement,addChild,createReply
from lxml.etree import tostring


class cmdManager:
    def __init__(self,trans):
        self.trans=trans
        self.globalCmdList={"echo":echoCmd(trans),'list':listCommands(trans)}
        self.transportCmdList={"echo":echoCmd(trans),
                'setstatus':setStatusCmd(trans),
                "login":loginCmd(trans),
                "logout":logoutCmd(trans),
                "config":setConfigCmd(trans),
                "addnote":addNoteCmd(trans),
                "bdays":checkBdays(trans),
                "wall":sendWallMessageCmd(trans),
                "getwall":getWall(trans),
                "getroster": GetRoster(trans)}
        self.contactCmdList={"history":getHistioryCmd(trans),
                "wall":sendWallMessageCmd(trans),
                #"friend":addDelFriendCmd(trans),
                #FIXME 'friend' command
                "getwall":getWall(trans)}
        self.adminCmdList={}
        self.admin=trans.admin
    def makeCmdList(self,s_jid,v_id):
        ret={}
        bjid=gen.bareJid(s_jid)
        #print bjid,v_id
        for i in self.globalCmdList:
            ret[i]=self.globalCmdList[i]

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
    def parseTextArgs(self,txt):
        if (txt.find('=')==-1):
            return {'default':txt}
        else:
            ret={}
            opList=txt.split('/')
            for i in opList:
                kv=[a.strip() for a in i.split('=')]
                if (len(kv)!=2):
                    return None
                    #TODO syntax error
                else:
                    ret[kv[0]]=kv[1]
            return ret
    def onMsg(self,jid,text,v_id=0):
        logging.info("text command '%s' from %s"%(text,jid))
        cmdList=self.makeCmdList(jid,v_id)
        cl=text.find(" ")
        if (cl==-1):
            #args=[]
            argText=None
            node=text
        else:
            #args=text[cl+1:].split(",")
            argText=text[cl+1:]
            node=text[:cl]
        #ret="command: '%s', args: %s"%(node,repr(args))
        if (cmdList.has_key(node)):
            cmd=cmdList[node]
            #ar=cmd.assignArgs(args)
            if (argText):
                argv=self.parseTextArgs(argText)
                if (argv==None):
                    return u'Синтаксическая ошибка в команде'
                try:
                    defname=cmd.args[0]
                    argv[defname]=argv['default']
                except KeyError:
                    pass
                except:
                    logging.exception('textcmd error')
            else:
                argv={}
            #print jid
            #print "command: '%s', args: %s"%(node,repr(ar))
            
            res=cmd.run(jid,argv,to_id=v_id)
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
            return u"Неопознанная команда: '%s'\nЕсли вы хотите просто отправить сообщение, начинающееся с точки, вставьте перед ней пробел ;)"%node
        return ret
        pass
    def onIqSet(self,iq):
        URI='http://jabber.org/protocol/commands'
        iqcmd=iq.find('{http://jabber.org/protocol/commands}command')
        node=iqcmd.get("node")[4:]
        v_id=gen.jidToId(iq.get("to"))
        cmdList=self.makeCmdList(iq.get("from"),v_id)
        if (cmdList.has_key(node)):
            #FIXME different actions
            act=iqcmd.get('action')
            
            if act=="cancel":
                ans=createReply(iq,'result')
                q=addChild(ans,'command',URI,{'status':'cancelled','node':node})
                sid=iqcmd.get('sessionid',None)
                if sid:
                    q.set("sessionid",sid)
                return ans
            x=iqcmd.find('{jabber:x:data}x')
            if (x!=None):
                args=self.getXdata(x)
            else:
                args={}
            cmd=cmdList[node]
            res=cmd.run(iq.get("from"),args,to_id=v_id)
            resp=createReply(iq,'result')
            c=addChild(resp,'command',URI,{'node':'cmd:%s'%node,'status':res['status'],'sessionid':'0'})
            x=addChild(c,'x','jabber:x:data')
            if (res.has_key("form")):
                act=addChild(c,'actions',attrs={'execute':'next'})
                addChild(act,'next')
                x.set('type','form')
            else:
                x.set('type','result')
            try:
                addChild(x,'title').text=res["title"]
            except KeyError:
                addChild(x,'title','result')
            try:
                addChild(x,'instructions').text=res["message"]
            except KeyError:
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
                    fn=addChild(x,'field',attrs={"type":ft, 'var':i,'label':fd})
                    if(val):
                        addChild(fn,'value').text=val

                    #f=x.addElement("field")
                    ##f.attributes={"type":ft, 'var':i,'label':fd}
                    #f.addElement("value").addContent(val)
            except KeyError:
                pass
            return resp
        else:
            err=createReply(iq,'error')
            addChild(err,'{urn:ietf:params:xml:ns:xmpp-stanzas}item-not-found')
            logging.warning('cant find command %s'%node)
            return err
            #FIXME error strnza
            pass
        
    def getXdata(self,x):
        ret={}
        #TODO check namespace
        #logging.error(tostring(x))
        #logging.error(x.findall('{jabber:x:data}field'))
        for i in x.findall('{jabber:x:data}field'):
            #logging.warning(tostring(i))
            vals=i.findall('{jabber:x:data}value')
            #logging.warning(v)
            val=''
            for v in vals:
                if (val):
                    val='%s\n%s'%(val,v.text)
                else:
                    val=v.text
            ret[i.get('var')]=val
        #logging.warning('xdata: '+str(ret))
        return ret
    def onDiscoInfo(self,iq):
        v_id=gen.jidToId(iq.get("to"))
        cmdList=self.makeCmdList(iq.get("to"),v_id)
        resp=createReply(iq)
        resp.set("type","result")
        q=addChild(resp,"query",'http://jabber.org/protocol/disco#info')
        node=iq.find('{http://jabber.org/protocol/disco#info}query').get("node")
        q.set('node',node)
        if (node=='http://jabber.org/protocol/commands'):
            # FIXME
            name=u"Команды [ad-hoc]"
            
            #addChild(q,'identity',attrs={"name":u"Команды [ad-hoc]","category":"automation","type":"command-node"})
                #q.addElement("identity").attributes={"name":"pyvk-t commands","category":"automation","type":"command-node"}
            #else:
                #addChild(q,'identity',attrs={"name":"pyvk-t commands","category":"automation","type":"command-node"})
                #q.addElement("identity").attributes={"category":"automation","type":"command-node"}
                
        else:
            try:
                cmd=cmdList[node[4:]]
                name=cmd.name
            except KeyError:
                #FIXME error stranza?
                name="unknown"
        addChild(q,'identity',attrs={"name":name,"category":"automation","type":"command-node"})
        addChild(q,"feature",attrs={'var':'http://jabber.org/protocol/commands'})
        addChild(q,"feature",attrs={'var':'jabber:x:data'})
        return resp
    def onDiscoItems(self,iq):
        cmdList={}
        #if (iq["to"]==self.trans.jid):
            #cmdList=self.transportCmdList
        v_id=gen.jidToId(iq.get("to"))
        cmdList=self.makeCmdList(iq.get("from"),v_id)
        #resp=xmlstream.toResponse(iq)
        resp=createReply(iq)
        resp.set("type",'result')
        q=addChild(resp,"query",'http://jabber.org/protocol/disco#items',attrs={'node':'http://jabber.org/protocol/commands'})
        #q["node"]='http://jabber.org/protocol/commands'
        for i in cmdList:
            addChild(q,'item',attrs={"jid":iq.get("to"), "node":"cmd:%s"%i, "name":cmdList[i].name})
            #q.addElement("item").attributes=
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
            try:
                if (self.args[0]==i):
                    i='(*) %s'%i
            except:
                logging.exception('')
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
                #print("args error")
                return {}
        return ret
    def onMsg(self,jid,text):
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
        bjid=gen.bareJid(jid)
        if (args.has_key("text")):
            #FIXME "too fast" safe!!!
            if (self.trans.hasUser(bjid)):
                self.trans.users[bjid].vclient.setStatus(args["text"])
            else:
                #print ("done")
                return {"status":"completed","title":u"Установка статуса",'message':u'Не получилось.\nСкорее всего, вам надо подключиться (команда .login)'}
        else:
            return {"status":"executing","title":u"Установка статуса","form":{"fields":{"text":('text-single',u'Статус')}},'message':u'Введите статус'}
        self.trans.users[bjid].VkStatus = args["text"]
        return {"status":"completed","title":u"Установка статуса",'message':u'Похоже, статус установлен (%s)'%args["text"]}

class loginCmd(basicCommand):
    name=u"Подключиться"
    args={0:'key'}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        #print "login"
        #print args
        #return 'test'
        bjid=gen.bareJid(jid)
        if (self.trans.isActive==0 and bjid!=self.trans.admin):
            return {"status":"completed","title":u"Подключение",'message':u"В настоящий момент транспорт неактивен, попробуйте подключиться позже"}
        if (self.trans.hasUser(bjid)):
            return {"status":"completed","title":u"Подключение",'message':u'Вы уже подключены'}
        captcha_key=None
        msg=u'Производится подключение...'
        try:
            #print args['key']
            captcha_key=args['key']
            msg=u'Производится подключение [капча "%s"]...'%captcha_key
        except KeyError:
            pass
        self.trans.addResource(jid,captcha_key=captcha_key)
        #print "resources: ",self.trans.users[bjid].resources
        return {"status":"completed","title":u"Подключение",'message':msg}

class logoutCmd(basicCommand):
    name=u"Отключиться"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=gen.bareJid(jid)
        if(self.trans.hasUser(bjid)):
            self.trans.users[bjid].logout()
        return {"status":"completed","title":u"Отключение",'message':u'Производится отключение...'}

class getHistioryCmd(basicCommand):
    name=u"История переписки"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=gen.bareJid(jid)
        if (to_id==0):
            print "where is id???"
            return {"status":"completed","title":self.name,'message':u'ПукЪ'}
        hist=self.trans.users[bjid].vclient.getHistory(to_id)
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
        bjid=gen.bareJid(jid)
        #if (to_id==0):
            #print "where is id???"
            #return {"status":"completed","title":self.name,'message':u'ПукЪ'}
        print(args)
        if (args.has_key("text")):
            #print ("sending wall message...")
            #FIXME "too fast" safe!!!
            if (self.trans.hasUser(bjid)):
                #print ("sending wall message...")
                res=self.trans.users[bjid].vclient.sendWallMessage(to_id,args["text"])
                if res==1:
                    return {"status":"completed","title":u"Отправка на стену",'message':u'Ошибка сети'}
                elif res==2:
                    return {"status":"completed","title":u"Отправка на стену",'message':u'Ошибка. Возможно запись на стену запрещена.'}
                elif res!=0:
                    return {"status":"completed","title":u"Отправка на стену",'message':u'Неизвестная ошибка.'}

                #print ("done")
            else:
                #print ("done")
                return {"status":"completed","title":u"Отправка на стену",'message':u'Не получилось.\nСкорее всего, вам надо подключиться (команда .login)'}
            #print ("done")
        else:
            return {"status":"executing","title":u"Отправка на стену","form":{"fields":{"text":('text-single',u'Сообщение','')}},'message':u'Введите текст сообщения для отправки на стену'}
        return {"status":"completed","title":u"Отправка на стену",'message':u'Похоже, сообщение отправлено'}

class addNoteCmd(basicCommand):
    name=u"Оставить новую заметку"
    args={0:"text",1:"title"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=gen.bareJid(jid)
        print(args)
        if (args.has_key("text")):
            #FIXME "too fast" safe!!!
            if (self.trans.hasUser(bjid)):
                res=self.trans.users[bjid].vclient.addNote(args["text"],args["title"])
                if res!=0:
                    return {"status":"completed","title":u"Отправка заметки",'message':u'Ошибка.'}
            else:
                return {"status":"completed","title":u"Отправка заметки",'message':u'Не получилось.\nСкорее всего, вам надо подключиться (команда .login)'}
        else:
            return {"status":"executing","title":u"Отправка заметки","form":{"fields":{"title":('text-single',u'Заголовок',''),"text":('text-multi',u'Текст','')}},'message':u'Введите текст заметки и название'}
        return {"status":"completed","title":u"Отправка на стену",'message':u'Похоже, заметка отправлена'}

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
        bjid=gen.bareJid(jid)
        #print(args)
        cf=gen.userConfigFields
        try:
            user=self.trans.users[bjid]
        except KeyError:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}

        if (len(args)):
            show_onlines_old = user.getConfig("show_onlines")
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
                else:
                    print "WTF!"
            print user.config
            nc=str(user.config)
            show_onlines = user.getConfig("show_onlines")
            #if show_onlines flag changed hide or show online contacts
            if show_onlines_old and not show_onlines:
                user.contactsOffline(user.onlineList,force=1)
            if not show_onlines_old and show_onlines:
                user.contactsOnline(user.onlineList)
            user.saveData()
            #self.trans.saveConfig(bjid)
            #except KeyError:
                #print "keyError"
                #nc="[void]"
            return {"status":"completed","title":self.name,'message':u'Настройки сохранены'}
            
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
    args={0:"operation"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=gen.bareJid(jid)
        try:
            user=self.trans.users[bjid]
        except KeyError:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}
        
        if (len(args)!=1):
            isFriend=self.trans.users[bjid].vclient.isFriend(to_id)
            fl={"operation":("text-single",u'Операция',"")}
            if (isFriend==0):
                st=u"друг"
                opt=u"del - удалить"
            elif (isFriend==1):
                st=u"не друг"
                opt=u"add - отправить заявку"
            elif (isFriend==2):
                st=u"не друг (сделал заявку)"
                opt=u"add - принять заявку, del - отклонить"
            elif (isFriend==-1):
                st=u"<внутренняя ошибка транспорта>"
                opt=u"<внутренняя ошибка транспорта>"
            return {"status":"executing","title":self.name,"form":{"fields":fl},
                    'message':u'Сейчас пользователь - %s\nДоступные операции: %s'%(st,opt)}
        #TODO run in pool?
        if (args.has_key("operation")):
            if args["operation"]=='add':
                user.vclient.addDeleteFriend(to_id,1)
            elif args["operation"]=='del':
                user.vclient.addDeleteFriend(to_id,0)
            else:
                return {"status":"completed","title":self.name,'message':u'Неизвестная операция: %s'%args["operation"]}
            return {"status":"completed","title":self.name,'message':u'Вроде, готово.'}    
        print args
        return {"status":"completed","title":self.name,'message':u'Ошибка'}

class checkBdays(basicCommand):
    name=u"Проверить дни рождения"
    args={}
    #args={0:"confirm"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        y=time.gmtime().tm_year
        m=time.gmtime().tm_mon
        d=time.gmtime().tm_mday
        delta=5
        
        bjid=gen.bareJid(jid)
        if self.trans.hasUser(bjid):
            user=self.trans.users[bjid]
            cal=user.vclient.getCalendar(month=m,year=y)
            for i in cal:
                if (i>d and i<d+delta):
                    for j in cal[i]:
                        if (j[:2]=="id"):
                            t=time.strptime("%s.%s.%s"%(i,m,y),"%d.%m.%Y")
                            self.trans.sendMessage(
                                src="%s@%s"%(j[2:],self.trans.jid),
                                dest=jid,
                                body=u"Скоро день рождения пользователя: %s"%time.strftime("%a, %d %b",t),
                                title=u"pyvk-t")
            #FIXME работа в конце месяца!!
            return {"status":"completed","title":self.name,'message':u'Уведомления высланы от имени соответствующих пользователей'}
        else:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}
class listCommands(basicCommand):
    name=u"Список доступных команд"
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        cl=self.trans.commands.makeCmdList(jid,to_id)
        msg=u''
        print "list cmd"
        for i in sorted(cl.keys()):
            msg=u"%s'.%s' - %s\n"%(msg,i,cl[i].name)
        return {"status":"completed","title":self.name,'message':msg}

class getWall(basicCommand):
    name=u"Просмотр стены"
    args={}
    #args={0:"v_id"}
    def __init__(self,trans):
        basicCommand.__init__(self,trans)
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=gen.bareJid(jid)
        if self.trans.hasUser(bjid):
            user=self.trans.users[bjid]
            wm=user.vclient.getWall(to_id)
            msg=u'Стена:'
            temp={}
            temp['text']=string.Template("$from ($v_id@$tjid) $date:\n$text")
            temp['audio']=string.Template("$from ($v_id@$tjid) $date:\n$desc\n( $dlink )")
            temp['graffiti']=string.Template(u"$from ($v_id@$tjid) $date:\nГраффити ( $dlink )")
            temp['video']=string.Template(u"$from ($v_id@$tjid) $date:\nВидео:'$desc'\n( $link )\nМиниатюра: $thumb\nСкачать: $dlink")
            temp['photo']=string.Template(u"$from ($v_id@$tjid) $date:\nФотография:'$desc'\n( $link )\nМиниатюра: $thumb")
            temp['unknown']=string.Template("$from ($v_id@$tjid) $date:\n[error: cant parse]")
            for i,m in wm:
                try:
                    msg="%s\n\n- %s"%(msg,temp[m['type']].safe_substitute(m,tjid=self.trans.jid))
                except KeyError:
                    msg="%s\n\n- %s"%(msg,temp['unknown'].substitute(m,tjid=self.trans.jid))
            msg=gen.unescape(msg.replace('<br>','\n')).strip()
            return {"status":"completed","title":self.name,'message':msg}
                    
            
        else:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}
class GetRoster(basicCommand):
    name=u'Получение списка друзей'
    args={}
    def __init__(self,trans):
        basicCommand.__init__(self,trans) 
    def run(self,jid,args,sessid="0",to_id=0):
        bjid=gen.bareJid(jid)
        if self.trans.hasUser(bjid):
            user=self.trans.users[bjid]
            fl=user.vclient.getFriendList()
            user.sendFriendList(fl)
            msg=u'Отправлены запросы авторизации (всего друзей: %s)'%len(fl)
            return {"status":"completed","title":self.name,'message':msg}
        else:
            return {"status":"completed","title":self.name,'message':u'Сначала надо подключиться'}        
