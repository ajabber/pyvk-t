# -*- coding: utf-8 -*-

import urllib2
import urllib
import cookielib
import threading
import time
from htmlentitydefs import name2codepoint
from cookielib import Cookie
from urllib import urlencode
from BeautifulSoup import BeautifulSoup,SoupStrainer

import demjson
import re
import base64

#user-agent used to request web pages
USERAGENT="Opera/10.00 (X11; Linux x86_64 ; U; ru) Presto/2.2.0"

class vkonClient:
    def feedChanged(self,jid,feed):
        print feed
    def usersOffline(self,jid,users):
        print "offline",users
    def usersOnline(self,jid,users):
        print "online",users
    def threadError(self,jid,message=""):
        print "error: %s"%message
class tooFastError(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'we are banned'
class authFormError(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'unexpected auth form'
class vkonThread(threading.Thread):
    oldFeed=""
    onlineList=[]
    alive=1
    error=0
    def __init__(self,cli,jid,email,passw):
        threading.Thread.__init__(self,target=self.loop)
        global opener
        self.jid=jid
        cjar=cookielib.FileCookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cjar))
        cjar.clear()
        authData={'email':email, 'pass':passw}
        params=urllib.urlencode(authData)
        req=urllib2.Request("http://vkontakte.ru/login.php?%s"%params)
        req.addheaders = [('User-agent', USERAGENT)]

        try:
            res=self.opener.open(req)
        except:
            print "urllib2 exception, possible http error"
            self.error=1
            self.alive=0
            return
        #print cjar
        self.cookie=cjar.make_cookies(res,req)
        self.client=cli
        self.feedOnly=1
        f=self.getFeed()
        if (f["user"]["id"]==-1):
            self.error=1
            self.client.threadError(self.jid,"auth error (possible wrong email/pawssword)")
            self.alive=0
        else:
            self.error=0
        #print res.read()
        #print this.cookie
    def checkPage(self,page):
        if (page.find(u'<div class="simpleHeader">Слишком быстро...</div>'.encode("cp1251"))!=-1):
            print ("%s: banned"%self.jid)
            raise tooFastError
        if (page.find('<form method="post" name="login" id="login" action="login.php">')!=-1):
            print ("%s: logged out"%self.jid)
            raise authFormError
        
        return 
    def logout(self):
        req=urllib2.Request("http://vkontakte.ru/login.php?op=logout")
        req.addheaders = [('User-agent', USERAGENT)]
        res=self.opener.open(req)
        print "logout"
    def getFeed(self):
        #global opener
        req=urllib2.Request("http://vkontakte.ru/feed2.php?mask=ufmepvnoqg")
        try:
            res=self.opener.open(req)
        except:
            print "urllib2 exception, possible http error"
            return {"messages":{"count":0}}
        s=res.read().decode("cp1251")
        #print repr(s)
        try:
            return demjson.decode(s)
        except:
            log.msg("JSON decode error")
            self.dumpString("feed",s)
        return {}
    def flParse(self,page):
        res=re.search("<script>friendsInfo.*?</script>",page,re.DOTALL)
        if (res==None):
            print "wrong page format: can't fing <script>"
            self.dumpString(page,"script")
            return []
        tag=page[res.start():res.end()]
        res=re.search("\tlist:\[\[.*?\]\],\n\n",tag,re.DOTALL)
        if (res==None):
            if (tag.find("list:[],")!=-1):
                return []
            print "wrong page format: can't fing 'list:''"
            if (self.chechBan):
                print "we are banned"
                raise tooFastError
            self.dumpString(page,"script")
            self.dumpString(tag,"script_list")
            
            return []
        json=tag[res.start()+6:res.end()-3]
        #print json
        json=json.decode("cp1251")
        try:
            flist=demjson.decode(json)
        except:
            print "json decode error"
        ret=[]
        for i in flist:ret.append(i[0])
        return ret
    def getOnlineList(self):
        req=urllib2.Request("http://vkontakte.ru/friend.php?act=online&nr=1")
        ret=list()
        try:
            res=self.opener.open(req)
            page=res.read()
            
        except:
            print "urllib2 exception, possible http error"
            return list()
        return self.flParse(page)
    def dumpString(self,string,fn=""):
        fname="%s-%s"%(int(time.time()),fn)
        fil=open(fname,"w")
        fil.write(string)
        fil.close()
        print "buggy page saved to",fname
        
    def getInfo(self,v_id):
        prs=vcardPrs()
        req=urllib2.Request("http://pda.vkontakte.ru/id%s"%v_id)
        res=self.opener.open(req)
        page=res.read()
        prs.feed(page)
        return prs.vcard
    def getVcard(self,v_id, show_avatars=0):
        '''
        Parsing of profile page to get info suitable to show in vcard
        '''
        req=urllib2.Request("http://vkontakte.ru/id%s"%v_id)
        try:
            res=self.opener.open(req)
            page=res.read()
        except:
            print "urllib2 exception, possible http error"
            return {"FN":""}
        try:
            bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
            #bs=BeautifulSoup(page)
        except:
            print "parse error\ntrying to filter bad entities..."
            page2=re.sub("&#x.{1,5}?;","",page)
            m1=page2.find("<!-- End pageBody -->") 
            m2=page2.find("<!-- End bFooter -->") 
            if (m1 and m2):
                page2=page2[:m1]+page2[m2:] 
            try:
                bs=BeautifulSoup(page2,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
            except:
                print "vCard retrieve failed\ndumping page..."
                self.dumpString(page,"vcard_parse_error")
                return None
        result = {}
        try:
            prof=bs.find(name="div", id="userProfile")
            rc=prof.find(name="div", id="rightColumn")
            lc=prof.find(name="div", id="leftColumn")
            profName=rc.find("div", {"class":"profileName"})
            result['FN']=unicode(profName.find(name="h2").string).encode("utf-8").strip()
            list=re.split("^(\S+?) (.*) (\S+?)$",result['FN'])
            if len(list)==5:
                result['GIVEN']=list[1].strip()
                result['NICKNAME']=list[2].strip()
                result['FAMILY']=list[3].strip()
            elif len(list)==4:
                result['GIVEN']=list[1].strip()
                result['FAMILY']=list[2].strip()
        except:
            checkPage()
            try:
                wr=bs.find(name="div",id="wrapH1")
                result['FN']=wr.div.h1.string
                print "'deleted' page parsed"
            except:
                print "wrong page format"
                self.dumpString(page,"vcard_wrong_format")
                return None
        #now parsing additional user data
        #there are several tables
        try:
            profTables = rc.findAll(name="table",attrs={"class":"profileTable"})
            for profTable in profTables:
                #parse each line of table
                ptr=profTable.findAll("tr")
                for i in ptr:
                    label=i.find("td",{"class":"label"})
                    dat=i.find("div",{"class":"dataWrap"})
                    #if there is some data
                    if (label and label.string and dat): 
                        y=BeautifulSoup(str(dat).replace("\n",""))
                        for cc in y.findAll(name="br"): cc.replaceWith("\n")
                        string=unicode(''.join(y.findAll(text=True))).encode("utf-8").strip()
                        if string: 
                            result[unicode(label.string)] = string
        except:
            print "cannot parse user data"
        #avatars are asked only if needed
        if show_avatars:
            try:
                photourl=lc.find(name="img")['src']
                req=urllib2.Request(photourl)
                res=self.opener.open(req)
                photo=base64.encodestring(res.read())
                result["PHOTO"]=photo
            except:
                print 'cannot load avatar'

        if not result.has_key(u"Веб-сайт:"):
            result[u"Веб-сайт:"] = "http://vkontakte.ru/id%s"%v_id
                        
        return result

    def getMessage_old(self,msgid):
        prs=msgPrs()
        
        req=urllib2.Request("http://pda.vkontakte.ru/letter%s"%msgid)
        res=self.opener.open(req)
        page=res.read()
        prs.feed(page)
        t=prs.msg
        if(prs.msg["text"][-5:]=="\n\n\t\t\t"):
            prs.msg["text"]=prs.msg["text"][:-5]
        #t['text']=t['text']
        return prs.msg
    def getMessage(self,msgid):
        req=urllib2.Request("http://pda.vkontakte.ru/letter%s"%msgid)
        try:
            res=self.opener.open(req)
            page=res.read()
        except:
            print "urllib2 exception, possible http error"
            return {"text":"error: html exception","from":"error","title":""}
        bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html")
        trgForm=bs.find(name="form", action="/mailsent?pda=1")
        fromField=trgForm.find(name="input",attrs={"name":"to_id"})
        from_id=fromField["value"]
        #print "from",repr(fromField)
        strings=trgForm.findAll(text=lambda (x):x!=u'\n'and x!=' ',recursive=False)
        title=strings[1]
        body=""
        for i in range(2,len(strings)):
            body=body+"\n"+strings[i]
        
        body=body[5:]
        #print body
        return {"text":body,"from":from_id,"title":title}
        #print strings
    def sendMessage(self,to_id,body,title="[null]"):
        """
        Sends message through website
        
        Return value:
        0   - success

        1   - http error
        2   - too fast sending
        -1  - unknown error
        """
        #prs=chasGetter()
        req=urllib2.Request("http://pda.vkontakte.ru/?act=write&to=%s"%to_id)
        try:
            res=self.opener.open(req)
            page=res.read()
        except:
            print "urllib2 exception, possible http error"
            return 1
            
        try:
            bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html")
            chas=bs.find(name="input",attrs={"name":"chas"})["value"]
        except:
            print "unknown error.. saving page.."
            self.dumpString(page,"send_chas")
            
        #print "chas",chas
        #prs.feed(page)
        if (type(body)==unicode):
            tbody=body.encode("utf-8")
        else:
            tbody=body
        if (type(title)==unicode):
            ttitle=title.encode("utf-8")
        else:
            ttitle=title

        data={"to_id":to_id,"title":ttitle,"message":tbody,"chas":chas,"to_reply":0}
        
        #print "data: ",urlencode(data)
        req=urllib2.Request("http://pda.vkontakte.ru/mailsent?pda=1",urlencode(data))
        try:
            res=self.opener.open(req)
        except urllib2.HTTPError:
            return 1
        page=res.read()
        if (page.find('<div id="msg">Сообщение отправлено.</div>')!=-1):
            print "message delivered"
            return 0
        elif (page.find('Вы попытались загрузить более одной однотипной страницы в секунду')!=-1):
            print "too fast sending messages"
            return 2
        return -1
        #try:
            #if (res.info()["Location"]=='/inbox?sent=1'):
                #print "message delivered"
                #return 1
            #else:
                #print "not delivered: '%s'"%res.info()["Location"]
                #return 0
        #except KeyError:
            #print "can't find 'Location' header", res.info()
            #self.dumpString(res.read(),"msg_sent")
            
            #return 0
        #print res.read()

    def getFriendList(self):
        req=urllib2.Request("http://vkontakte.ru/friend.php?nr=1")
        ret=list()
        
        try:
            res=self.opener.open(req)
            page=res.read()
        except:
            print "urllib2 exception, possible http error"
            return ret
        return self.flParse(page)
    def loop(self):
        while(self.alive):
            tfeed=self.getFeed()
            if (tfeed!=self.oldFeed):
                self.oldFeed=tfeed
                self.client.feedChanged(self.jid,tfeed)
            if (self.feedOnly):
                tonline=[]
            else:
                try:
                    tonline=self.getOnlineList()
                except tooFastError:
                    self.client.threadError(self.jid,"banned")
                    time.sleep(100)
                except loginFormError:
                    self.client.threadError(self.jid,"auth")
                    self.client.usersOffline(self.onlineList)
                    return
                    
            #print tonline,self.onlineList
            if (tonline!=self.onlineList):
                self.client.usersOnline(self.jid,filter(lambda x:self.onlineList.count(x)-1,tonline))
                self.client.usersOffline(self.jid,filter(lambda x:tonline.count(x)-1,self.onlineList))
                self.onlineList=tonline
            time.sleep(10)
    def exit(self):
        self.client.usersOffline(self.jid,self.onlineList)
        self.logout()
        self.alive=0
        #threading.Thread.exit(self)
    def __del__(self):
        self.logout()
        threading.Thread.exit(self)
