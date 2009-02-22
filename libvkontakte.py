# -*- coding: utf-8 -*-
import urllib2
import urllib
import cookielib
import threading
import time
from htmlentitydefs import name2codepoint
from cookielib import Cookie
from urllib import urlencode
from BeautifulSoup import BeautifulSoup
import demjson
import re

class vkonClient:
    def feedChanged(self,jid,feed):
        print feed
    def usersOffline(self,jid,users):
        print "offline",users
    def usersOnline(self,jid,users):
        print "online",users
    def threadError(self,jid,message=""):
        print "error: %s"%message

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
        req.addheaders = [('User-agent', 'Mozilla/5.0')]

        res=self.opener.open(req)
        #print cjar
        self.cookie=cjar.make_cookies(res,req)
        self.client=cli
        self.feedOnly=1
        f=self.getFeed()
        if (f["user"]["id"]==-1):
            self.error=1
            self.client.threadError(self.jid,"auth error (possible wrong email/pawssword)")
        else:
            self.error=0
        
        #print res.read()
        #print this.cookie
    
    def logout(self):
        req=urllib2.Request("http://vkontakte.ru/login.php?op=logout")
        req.addheaders = [('User-agent', 'Mozilla/5.0')]
        res=self.opener.open(req)
        print "logout"
    def getFeed(self):
        #global opener
        req=urllib2.Request("http://vkontakte.ru/feed2.php?mask=ufmepvnoq")
        res=self.opener.open(req)
        s=res.read().decode("cp1251")
        #print repr(s)
        ret=demjson.decode(s)
        return ret

    def getOnlineList(self):
        req=urllib2.Request("http://vkontakte.ru/friend.php?act=online&nr=1")
        res=self.opener.open(req)
        page=res.read()
        ret=list()
        try:
            bs=BeautifulSoup(page)
        except Exception,ex:
            print "parse error. trying to delete bad <script> tag..."
            m=re.search("<script>\tfriendPatterns.*?</script>",page,re.DOTALL)
            page=m.string[:m.start()]+m.string[m.end():]
            try:
                bs=BeautifulSoup(page)
            except:
                print "failed"
                fil=open("pagedump.html","w")
                fil.write(page)
                fil.close()
                print "buggy page saved to pagedump.html"
                return ret
            print "success!"
            trgDiv=bs.find(name="div",id="searchResults")
            if (trgDiv==None):
                return list()
            trgScr=trgDiv.findAll(name="script")[0].string[14:]
        else:
            trgDiv=bs.find(name="div",id="searchResults")
            if (trgDiv==None):
                return list()
            trgScr=trgDiv.findAll(name="script")[1].string[14:]
        try:
            a=demjson.decode(trgScr)
            for t in a["list"]:
                ret.append(t[0])
        except:
            print "can't parse JSON: '%s'"%trgStr
        return ret
    def dumpString(self,string,fn=""):
        fname="%s-%s.html"%(int(time.time()),fn)
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
    def getVcard(self,v_id):
        req=urllib2.Request("http://vkontakte.ru/id%s"%v_id)
        res=self.opener.open(req)
        page=res.read()
        try:
            bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
            #bs=BeautifulSoup(page)
        except:
            print "parse error\ntrying to filter bad entities..."
            page2=re.sub("&#x.{1,5}?;","",page)
            try:
                bs=BeautifulSoup(page2,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
            except:
                print "vCard retrieve failed\ndumping page..."
                self.dumpString(page,"vcard_parse_error")
                return None
        try:
            prof=bs.find(name="div", id="userProfile")
            rc=prof.find(name="div", id="rightColumn")
            fn=rc.find(name="h2").string.encode("utf-8")
        except:
            print "wrong page format"
            self.dumpString(page,"vcard_wrong_format")
            return None
        return {"fn":fn}
        
        print "name",fn
        ptr=rc.find(name="table", attrs= {"class":"profileTable"}).findAll("tr")
        for i in ptr:
            title=i.td.string
            dat=i.contents[3].div
            #print title
            #print dat
            if (title==u"День рождения:"):
                cnt=dat.findAll("a")
                #print cnt
                #if (len(cnt)==2):
                    #h=cnt[0]["href"][15:]
                    #print h
                    #day=
                    #print cnt[1].string
                #print dat
                #yr=dat.
        #print pt
        
        #TODO name parse
        return {"fn":fn}
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
        res=self.opener.open(req)
        page=res.read()
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
        #prs=chasGetter()
        req=urllib2.Request("http://pda.vkontakte.ru/?act=write&to=%s"%to_id)
        res=self.opener.open(req)
        page=res.read()
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
            return 1
        except urllib2.HTTPError:
            return 0
        #print res.read()
    def getFriendList(self):
        req=urllib2.Request("http://vkontakte.ru/friend.php?nr=1")
        res=self.opener.open(req)
        page=res.read()
        ret=list()
        
        try:
            bs=BeautifulSoup(page)
        except Exception,ex:
            print "parse error. trying to delete bad <script> tag..."
            m=re.search("<script>\tfriendPatterns.*?</script>",page,re.DOTALL)
            page=m.string[:m.start()]+m.string[m.end():]
            try:
                bs=BeautifulSoup(page)
            except:
                print "friendlistv retrieve failed\ndumping page..."
                self.dumpString(page,"friendlist")
                return ret
            print "success!"
            trgDiv=bs.find(name="div",id="searchResults")
            if (trgDiv==None):
                return list()
            trgScr=trgDiv.findAll(name="script")[0].string[14:]
        else:
            trgDiv=bs.find(name="div",id="searchResults")
            if (trgDiv==None):
                return list()
            trgScr=trgDiv.findAll(name="script")[1].string[14:]
        try:
            a=demjson.decode(trgScr)
            for t in a["list"]:
                ret.append(t[0])
        except:
            print "can't parse JSON: '%s'"%trgStr
            print "dumping page..."
            self.dumpString(page,"json")
            
        return ret
    def loop(self):
        while(self.alive):
            tfeed=self.getFeed()
            if (tfeed!=self.oldFeed):
                self.oldFeed=tfeed
                self.client.feedChanged(self.jid,tfeed)
            if (self.feedOnly):
                tonline=[]
            else:
                tonline=self.getOnlineList()
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
