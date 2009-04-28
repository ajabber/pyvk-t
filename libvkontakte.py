# -*- coding: utf-8 -*-

import urllib2
import urllib
import httplib
import cookielib
import threading
import time
from htmlentitydefs import name2codepoint
from cookielib import Cookie
from urllib import urlencode
from BeautifulSoup import BeautifulSoup,SoupStrainer
from os import environ
import re
import base64
import ConfigParser,os
#from BaseHTTPServer import BaseHTTPRequestHandler as http
import xml.dom.minidom
#import twisted.web.microdom
#import simplejson
from traceback import print_stack, print_exc
#from lxml import etree
#user-agent used to request web pages
#USERAGENT="Opera/9.60 (J2ME/MIDP; Opera Mini/4.2.13337/724; U; ru) Presto/2.2.0"
USERAGENT="ELinks (0.4pre5; Linux 2.4.27 i686; 80x25)"

class vkonClient:
    def updateFeed(self,jid,feed):
        print feed
    def usersOffline(self,jid,users):
        print "offline",users
    def usersOnline(self,jid,users):
        print "online",users
    def threadError(self,jid,message=""):
        print "error: %s"%message
    def avatarChanged(self,v_id):
        print "avatar changed for id%s"%v_id


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
class vkonThread():
    oldFeed=""
    onlineList={}
    alive=1
    error=0
    loopDone=True
    #just counter for loops. use some big number in the beginning
    iterationsNumber = 999999
    # true if there is no loopInternal's in user queue
    tonline={}
    def __init__(self,cli,jid,email,passw,user):
        #threading.Thread.__init__(self,target=self.loop)
        #self.daemon=True
        self.alive=0
        self.user=user
        self.client=cli
        self.feedOnly=1
        config = ConfigParser.ConfigParser()
        confName="pyvk-t_new.cfg"
        if(os.environ.has_key("PYVKT_CONFIG")):
            confName=os.environ["PYVKT_CONFIG"]
        config.read(confName)
        self.config=config
        global opener
        self.jid=jid
        #deprecated self.jid
        self.bjid=jid
        try:
            self.dumpPath=config.get("debug","dump_path")
        except (ConfigParser.NoOptionError,ConfigParser.NoSectionError):
            print "debug/dump_path isn't set. disabling dumps"
            self.dumpPath=None
        try:
            self.cachePath=config.get("features","cache_path")
        except (ConfigParser.NoOptionError,ConfigParser.NoSectionError):
            print "features/cache_path isn't set. disabling cache"
            self.cachePath=None
        try:
            self.keep_online=config.get("features","keep_online")
        except (ConfigParser.NoOptionError,ConfigParser.NoSectionError):
            print "features/keep_online isn't set."
            self.keep_online=None
        try:
            cookdir=config.get("features","cookies_path")
            cjar=cookielib.MozillaCookieJar("%s/%s"%(cookdir,self.bjid))
        except (ConfigParser.NoOptionError,ConfigParser.NoSectionError):
            print "features/cookies_path isn't set. disabling cookie cache"
            cjar=cookielib.MozillaCookieJar()
            cookdir=None
        try:
            cjar.clear()
            cjar.load()
        except IOError:
            print "cant read cookie"
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cjar))
        #cjar.clear()
        if (self.checkLoginError()!=0):
            #print "bad cookie..."
            cjar.clear()
            authData={'op':'a_login_attempt','email':email, 'pass':passw}
            params=urllib.urlencode(authData)
            req=urllib2.Request("http://vkontakte.ru/login.php?%s"%params)
            req.addheaders = [('User-agent', USERAGENT)]
            try:
                res=self.opener.open(req)
            except urllib2.HTTPError, err:
                print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
                self.error=1
                self.alive=0
                return 
            tpage=res.read()
            #print tpage
            if (tpage[:20]=='{"ok":-2,"captcha_si'):
                print "ERR: got captcha request"
                self.error=1
                self.client.threadError(self.jid,"auth error: got captha request")
                self.alive=0
                return
            # {"ok":-2,"captcha_sid":"962043805179","text":"Enter code"} - captcha
            # good<your_id> - success
            self.cookie=cjar.make_cookies(res,req)
            if (self.checkLoginError()!=0):
                self.error=1
                self.client.threadError(self.jid,"auth error (possible wrong email/pawssword)")
                self.alive=0
            else:
                #print "login successful."
                if self.user.getConfig("save_cookies"):
                    try:
                        #print "saving cookie.."
                        cjar.save()
                        #print "done"
                    except:
                        print "ERR: can't save cookie"
                        print_exc()
                self.error=0
                self.alive=1
        else:
            print "cookie accepted!"
            self.alive=1
            self.error=0
        #f=self.getFeed()
        #if (f["user"]["id"]==-1):

    def getHttpPage(self,url,params=None):
        """ get contents of web page
            returns u'' if some of errors took place
        """
        if params:
            req=urllib2.Request(url,params)
        else:
            req=urllib2.Request(url)
        req.addheaders = [('User-agent', USERAGENT)]
        try:
            res=self.opener.open(req)
            page=res.read()
        except urllib2.HTTPError, err:
            print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
            return ''
        except IOError, e:
            print "IO Error"
            if hasattr(e, 'reason'):
                print "Reason: %s.\nURL:%s"%(e.reason,req.get_full_url())
            elif hasattr(e, 'code'):
                print "Code: %s.\nURL:%s"%(e.code,req.get_full_url())
            return ''
        except httplib.BadStatusLine, err:
            print "HTTP bad status line error.\nURL:%s"%(req.get_full_url())
            return ''
        except httplib.HTTPException, err:
            print "HTTP exception.\n URL: %s"%(req.get_full_url())
            return ''
        return page

    def checkPage(self,page):
        if (page.find(u'<div class="simpleHeader">Слишком быстро...</div>'.encode("cp1251"))!=-1):
            print ("%s: banned"%self.jid)
            raise tooFastError
        if (page.find('<form method="post" name="login" id="login" action="/login.php"')!=-1):
            print ("%s: logged out"%self.jid)
            raise authFormError
        return 

    def logout(self):
        self.alive=0
        self.client.usersOffline(self.jid,self.onlineList)
        self.onlineList={}
        if not self.user.getConfig("save_cookies"):
            self.getHttpPage("http://vkontakte.ru/login.php","op=logout")
        #print "%s: logout"%self.bjid
    def getFeed(self):
        s=self.getHttpPage("http://vkontakte.ru/feed2.php","mask=ufmepvnogq").decode("cp1251").strip()
        if not s or s[0]!=u'{':
            return {}
        s=s.replace(u':"',u':u"')
        try:
            return eval(s,{"null":"null"},{})
        except:
            print("JSON decode error")
            print_exc()
        return {}

    def flParse(self,page):
        res=re.search("<script>friendsInfo.*?</script>",page,re.DOTALL)
        if (res==None):
            print "wrong page format: can't fing <script>"
            self.checkPage(page)
            self.dumpString(page,"script")
            return {}
        tag=page[res.start():res.end()]
        res=re.search("\tlist:\[\[.*?\]\],\n\n",tag,re.DOTALL)
        if (res==None):
            if (tag.find("list:[],")!=-1):
                return {}
            print "wrong page format: can't fing 'list:''"
            self.checkPage(page)
            self.dumpString(page,"script")
            self.dumpString(tag,"script_list")        
            return {}
        #print 
        json=tag[res.start()+6:res.end()-3]
        #print json
        
        #json=json
        #.decode("cp1251")
        #.encode("utf-8")
        gl={}
        for i in ["f","l","p","uy","uf","to","r","f","u","ds","fg"]:
            gl[i]=i
        try:
            flist=eval(json,gl,{})
            #print flist
            #flist=demjson.decode(json)
        except:

            print_exc()
            print "json decode error"
            return {}
        ret={}
        for i in flist:
            ret[i[0]]={"last":i[1]['l'].decode("cp1251"),"first":i[1]['f'].decode("cp1251")}
            #print type(i[1]['l'])
        #print "--",ret
        return ret

    def getOnlineList(self):
        ret={}
        page=self.getHttpPage("http://vkontakte.ru/friend.php","act=online&nr=1")
        if not page:
            return {}
        return self.flParse(page)

    def dumpString(self,string,fn=""):
        if (self.dumpPath==None or self.dumpPath==''):
            return
        fname="%s/%s-%s"%(self.dumpPath,int(time.time()),fn)
        fil=open(fname,"w")
        if (type(string)==unicode):
            string=strng.encode("utf-8")
        fil.write(string)
        fil.close()
        print "buggy page saved to",fname
        
    def getInfo(self,v_id):
        prs=vcardPrs()
        page=self.getHttpPage("http://pda.vkontakte.ru/id%s"%v_id)
        prs.feed(page)
        return prs.vcard

    def getHistory(self,v_id):
        page=self.getHttpPage("http://vkontakte.ru/mail.php","act=history&mid=%s"%v_id)
        if not page:
            return []
        bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
        msgs=bs.findAll("tr",attrs={"class":"message_shown"})
        ret=[]
        for i in msgs:
            #print i["id"]
            if (i["id"][:16]=="message_outgoing"):
                t=u'out'
            else:
                t=u'in'
            m=u''
            for j in i.div.contents:
                m=m+unicode(j)
            ret.append((t,m.replace('<br />','\n')))
        #ret=ret.replace('<br />','\n')
        return ret

    def sendWallMessage(self,v_id,text):
        """ 
        Send a message to user's wall
        Returns:
        0   - success
        1   - http|urllib error
        2   - could not get form
        3   - no data
        -1  - unknown error
        """
        if not text:
            return 3
        page=self.getHttpPage("http://pda.vkontakte.ru/id%s"%v_id)
        if not page:
            return 1
        bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="utf-8")
        form=bs.find(name="form")
        if not form or not form.has_key("action"):
            return 2
        formurl=form["action"]
        if not formurl:
            return 2
        if not type(text)==type(u""):
            text=unicode(text,"utf-8")
        params=urllib.urlencode({"message":text.encode("utf-8")})
        page=self.getHttpPage("http://pda.vkontakte.ru%s&%s"%(formurl,params))
        if page:
            return 0
        return 1

    def sendWallMessage2(self,v_id,text):
        """ 
        Send a message to user's wall
        Returns:
        0   - success
        1   - http|urllib error
        2   - could not get form
        3   - no data
        -1  - unknown error
        """
        if not text:
            return 3
        page=self.getHttpPage("http://wap.vkontakte.ru/id%s"%v_id)
        if not page:
            return 1
        dom=xml.dom.minidom.parseString(page)
        gos=dom.getElementsByTagName("go")
        go=filter(lambda x: x.getAttribute("method")=='POST',gos)
        if (len(go)!=1):
            return -1
        go=go[0]
        url=go.getAttribute("href")
        if (url==""):
            return -1
        params=urllib.urlencode({"message":text.encode("utf-8")})
        page=self.getHttpPage("http://pda.vkontakte.ru%s&%s"%(formurl,params))
        if page:
            return 0
        return 1

    def getVcard(self,v_id, show_avatars=0):
        '''
        Parsing of profile page to get info suitable to show in vcard
        '''
        page = self.getHttpPage("http://vkontakte.ru/id%s"%v_id)
        if not page:
            return {"FN":u""}
        try:
            bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
            #bs=BeautifulSoup(page)
        except:
            #FIXME exception type
            #print "parse error\ntrying to filter bad entities..."
            page2=re.sub("&#x.{1,5}?;","",page)
            m1=page2.find("<!-- End pageBody -->") 
            m2=page2.find("<!-- End bFooter -->") 
            if (m1 and m2):
                page2=page2[:m1]+page2[m2:] 
            try:
                bs=BeautifulSoup(page2,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
            except:
                #FIXME exception type
                print "vCard retrieve failed\ndumping page..."
                self.dumpString(page,"vcard_parse_error")
                return None
        result = {}
        prof=bs.find(name="div", id="userProfile")
        if (prof==None):
            # search page
            self.checkPage(page)
            cont=bs.find(name="div",id="content")
            if(cont==None):
                self.checkPage(page)
                self.dumpString(page, "vcard_no_cont")
            result['FN']=cont.find(name='div',style="overflow: hidden;").string
            #FIXME 
            lc=cont
            rc=None
        else:
            rc=prof.find(name="div", id="rightColumn")
            if (rc!=None):
                lc=prof.find(name="div", id="leftColumn")
                profName=rc.find("div", {"class":"profileName"})
                result['FN']=unicode(profName.find(name="h2").string).encode("utf-8").strip()
            else:
                # deleted page
                pt=bs.head.title.string
                del_pos=pt.find(" | ")
                lc=None
                result['FN']=pt[del_pos+3:]
                result[u"О себе:"]=u"[страница удалена ее владельцем]"
        if (self.user.getConfig("resolve_nick")):
            list=re.split("^(\S+?) (.*) (\S+?) \((\S+?)\)$",result['FN'])
            if len(list)==6:
                result['GIVEN']=list[1].strip()
                result['NICKNAME']=list[2].strip()
                result['FAMILY']=list[3].strip()
            else:
                list=re.split("^(\S+?) (.*) (\S+?)$",result['FN'])
                if len(list)==5:
                    result['GIVEN']=list[1].strip()
                    result['NICKNAME']=list[2].strip()
                    result['FAMILY']=list[3].strip()
        #now parsing additional user data
        #there are several tables
        try:
            #FIXME font use try/except
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
        if lc and show_avatars and self.user.getConfig("vcard_avatar"):
            photourl=lc.find(name="img")['src']
            #if user has no avatar we wont process it
            if photourl!="images/question_a.gif" and  photourl!="images/question_b.gif":
                fpath=''
                photo=None
                if (self.cachePath):
                    pos=photourl.find(".ru/u")
                    #TODO don't save avatars from "search"
                    if (pos!=-1):
                        fname=photourl[pos+4:].replace("/","_")
                        fpath="%s/avatar-%s"%(self.cachePath,fname)
                        ifpath="%s/img-avatar-%s"%(self.cachePath,fname)
                        try:
                            cfile=open(fpath,"r")
                            photo=cfile.read()
                            cfile.close()
                        except:
                            print "can't read cache: %s"%fname
                if not photo:
                    photo = base64.encodestring(self.getHttpPage(photourl))
                    if photo and self.cachePath and rc!=None:
                        #FIXME check for old avatars
                        fn="avatar-u%s"%v_id
                        fn2="img-avatar-u%s"%v_id
                        l=len(fn)
                        l2=len(fn)
                        fname=None
                        for i in os.listdir(self.cachePath):
                            if (i[:l]==fn or i[:l2]==fn2):
                                os.unlink("%s/%s"%(self.cachePath,i))
                        cfile=open(fpath,'w')
                        cfile.write(photo)
                        cfile.close()
                        #ifile=open(ifpath,'w')
                        #ifile.write(imgdata)
                        #ifile.close()
                        self.client.avatarChanged(v_id=v_id,user=self.bjid)
                if photo:
                    result["PHOTO"]=photo
        return result

    def searchUsers(self, text):
        '''
        Searches 10 users using simplesearch template
        '''
        if type(text)!=type(u''):
            text=text.decode("utf-8")
        text=text.encode("cp1251")

        data={'act':"quick", 'n':"0","q":text}
        params=urllib.urlencode(data)

        page = self.getHttpPage("http://vkontakte.ru/search.php",params)
        if not page:
            return None
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
                print "search page parse error"
                self.dumpString(page,"search_parse_error")
                return None
        result = {}
        try:
            content=bs.find(name="div", id="content")
            for i in content.findAll(name="div",attrs={'class':'info'}):
                id = i['id'][4:]
                if id:
                    name=i.find(name='div')
                    if not id in result:
                        result[id]={}
                    result[i['id'][4:]]["name"]=u''.join(name.findAll(text=True)).strip()
                    matches = i.find(name="dd",attrs={"class":"matches"}) 
                    if matches:
                        result[i['id'][4:]]["matches"]=u''.join(matches.findAll(text=True)).strip()
                    else:
                        result[i['id'][4:]]["matches"]=u''
        except:
            print "wrong page format"
            self.dumpString(page,"search_wrong_format")
            return None
        return result

    def setStatus(self,text):
        """ Sets status (aka activity) on vkontakte.ru site"""
        page = self.getHttpPage("http://pda.vkontakte.ru/status")
        if not page:
            return None
        dom=xml.dom.minidom.parseString(page)
        fields=dom.getElementsByTagName("input")
        fields=filter(lambda x:x.getAttribute("name")=='activityhash',fields)
        if (len(fields)==0):
            print "setstatus: cant find fields\nFIXME need page check"
            return 0
        hashfield=filter(lambda x:x.getAttribute("name")=='activityhash',fields)[0]
        ahash=hashfield.getAttribute("value")
        #if (hashfield==None):
            #return
        if text:
            dat={'activityhash':ahash,'setactivity':text.encode("utf-8")}
            res=self.getHttpPage("http://pda.vkontakte.ru/setstatus?pda=1",urlencode(dat))
        else:
            dat={'activityhash':ahash,'clearactivity':"1"}
            res=self.getHttpPage("http://vkontakte.ru/profile.php?",urlencode(dat))
        if not res:
            return 1

    def getMessage(self,msgid):
        """
        retrieves message from the server
        """
        #print "getmessage %s started"%msgid
        page =self.getHttpPage("http://pda.vkontakte.ru/letter%s?"%msgid)
        if not page:
            return {"text":"error: html exception","from":"error","title":""}
        dom = xml.dom.minidom.parseString(page)
        form=dom.getElementsByTagName("form")[0]
        ret={}
        #print form.toxml()
        links=form.getElementsByTagName("span")
        ret["from"]=form.getElementsByTagName("a")[0].getAttribute("href")[2:]
        tspan=form.getElementsByTagName("span")[3]
        k=tspan.nextSibling
        ret["title"]=k.data
        msg=""
        k=k.nextSibling

        while(k.nodeName!="span"):
            if (k.nodeType==xml.dom.Node.TEXT_NODE):
                msg="%s%s"%(msg,k.data)
            else:
                print k
                msg="%s%s"%(msg,k.toxml())
            k=k.nextSibling
        msg=msg.replace("<br/>","\n")[6:-6]
        ret["text"]=msg
        return ret
        #p=dom.getElementsByTagName("p")[0]
        #p.normalize()

        #anchors=p.getElementsByTagName("anchor")
        
        #from_id=anchors[1].getElementsByTagName('go')[0].getAttribute("href")[2:]
        #i_s=p.getElementsByTagName("i")
        #date=i_s[2].nextSibling.data
        ##ERR ^^^ index out of range
        #title=i_s[3].nextSibling.data
        #msg=""
        #t=i_s[3].nextSibling
        #while(1):
            #t=t.nextSibling
            #try:
                #if (t.nodeName=="i"):
                    #break
            #except AttributeError:
                #pass
            ##print t.toxml()
            #msg="%s%s"%(msg,t.toxml())
        #msg=msg.replace("<br/>","\n")[4:-4]
        ##print msg
        ##print "getmessage %s finished"%msgid
        #return {"from":from_id,"date":date,"title":title,"text":msg}
    def sendMessage_legacy(self,to_id,body,title="[null]"):
        """
        Sends message through website
        
        Return value:
        0   - success

        1   - http error
        2   - too fast sending
        -1  - unknown error
        """
        #prs=chasGetter()
        page = self.getHttpPage("http://pda.vkontakte.ru/","act=write&to=%s"%to_id)
        if not page:
            return 1
        try:
            bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html")
            chas=bs.find(name="input",attrs={"name":"chas"})["value"]
        except:
            print "unknown error.. saving page.."
            self.dumpString(page,"send_chas")
        if (type(body)==unicode):
            tbody=body.encode("utf-8")
        else:
            tbody=body
        if (type(title)==unicode):
            ttitle=title.encode("utf-8")
        else:
            ttitle=title
        data={"to_id":to_id,"title":ttitle,"message":tbody,"chas":chas,"to_reply":0}
        page=self.getHttpPage("http://pda.vkontakte.ru/mailsent?pda=1",urlencode(data))
        if not page:
            return 1
        if (page.find('<div id="msg">Сообщение отправлено.</div>')!=-1):
            return 0
        elif (page.find('Вы попытались загрузить более одной однотипной страницы в секунду')!=-1):
            print "too fast sending messages"
            return 2
        print "unknown error"
        return -1

    def sendMessage(self,to_id,body,title="[null]"):
        """
        Sends message through website
        
        Return value:
        0   - success
        1   - http error
        2   - too fast sending
        -1  - unknown error
        """
        page = self.getHttpPage("http://pda.vkontakte.ru/?act=write&to=%s"%to_id)
        if not page:
            return 1
        dom = xml.dom.minidom.parseString(page)
        #print dom.toxml()
        inputs=dom.getElementsByTagName("input")
        c_input=filter(lambda x:x.getAttribute("name")=='chas',inputs)[0]
        chas=c_input.getAttribute("value")
        
        #inputs=dom.getElementsByTagName("postfield")
        #c_input=filter(lambda x:x.getAttribute("name")=='chas',inputs)[0]
        #chas=c_input.getAttribute("value")
        if (type(body)==unicode):
            tbody=body.encode("utf-8")
        else:
            tbody=body
        if (type(title)==unicode):
            ttitle=title.encode("utf-8")
        else:
            ttitle=title

        data={"to_id":to_id,"title":ttitle,"message":tbody,"chas":chas,"to_reply":0}
        print data
        page=self.getHttpPage("http://pda.vkontakte.ru/mailsent?pda=1",urlencode(data))
        if not page:
            return 1
        if (page.find('<div id="msg">Сообщение отправлено.</div>')!=-1):
            return 0
        elif (page.find('Вы попытались загрузить более одной однотипной страницы в секунду')!=-1):
            print "too fast sending messages"
            return 2
        print "unknown error"
        return -1
        #return
        #if not page:
            #return 1
        #if (page.find('<i id="msg">Сообщение отправлено.')!=-1):
            ##print "message delivered"
            #return 0
        #elif (page.find('Вы попытались загрузить более одной однотипной страницы в секунду')!=-1):
            ##FIXME adapt to wap version
            #print "too fast sending messages"
            #return 2
        #print "unknown error"
        #print page
        #return -1

    def getFriendList(self):
        page = self.getHttpPage("http://vkontakte.ru/friend.php?nr=1")
        if not page:
            return {}
        return self.flParse(page)

    def isFriend(self,v_id):
        page = self.getHttpPage("http://wap.vkontakte.ru/id%s"%v_id)
        if not page: 
            return -1
        if (page.find('<go href="/addfriend%s"'%v_id)==-1):
            return 1
        return 0

    def addDeleteFriend(self,v_id,isAdd):
        if (isAdd):
            page = self.getHttpPage("http://wap.vkontakte.ru/addfriend%s"%v_id)
            if page:
                return 0
            return -1
        else:
            #print "%s: del friend %s"%(self.bjid,v_id)
            page = self.getHttpPage("http://wap.vkontakte.ru/deletefriend%s"%v_id)
            if page:
                return 0
            return -1

    def checkLoginError(self):
        page=self.getHttpPage("http://vkontakte.ru/feed2.php")
        if (not page):
            return 1
        if (page=='{"user": {"id": -1}}' or page[0]!='{'):
            return 1
        return 0

    def dummyRequest(self):
        """ request that means nothing"""
        req=urllib2.Request("http://wap.vkontakte.ru/")
        try:
            res=self.opener.open(req)
            page=res.read()
        except urllib2.HTTPError, err:
            print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
            return -1
            
    def loop(self):
        return
        self.tonline={}
        j=80
        while(self.alive):
            j=j+1
            tfeed=self.getFeed()
            #tfeed is epty only on some error. Just ignore it
            if tfeed:
                self.client.updateFeed(self.jid,tfeed)
            if (self.feedOnly):
                self.tonline={}
            else:
                try:
                    self.onlineList=self.getOnlineList()
                except tooFastError:
                    self.client.threadError(self.jid,"banned")
                    #FIXME
                    time.sleep(100)
                except authFormError:
                    if (self.alive):
                        self.client.threadError(self.jid,"auth")
                    self.client.usersOffline(self.jid,self.onlineList)
                    return
            if (self.tonline.keys()!=self.onlineList.keys()):
                if self.alive: self.client.usersOffline(self.jid,filter(lambda x:self.onlineList.keys().count(x)-1,self.tonline.keys()))
                if self.alive: self.client.usersOnline(self.jid,filter(lambda x:self.tonline.keys().count(x)-1,self.onlineList.keys()))
                if self.alive: self.tonline=self.onlineList
            time.sleep(1)
            if self.alive and j>80 and self.keep_online and self.user.getConfig("keep_online"):
                #FIXME online status
                self.getHttpPage("http://wap.vkontakte.ru/id1")
                j=0
            elif j>81:
                j=75
            for i in range(1,10):
                if not self.alive: return
                time.sleep(1)
    def loopIntern(self):
        #print "start loop"
        tfeed=self.getFeed()
        #tfeed is epty only on some error. Just ignore it
        if tfeed:
            self.client.updateFeed(self.jid,tfeed)
        self.onlineList=self.getOnlineList()
        if (self.tonline.keys()!=self.onlineList.keys()):
            if self.alive: self.client.usersOffline(self.jid,filter(lambda x:self.onlineList.keys().count(x)-1,self.tonline.keys()))
            if self.alive: self.client.usersOnline(self.jid,filter(lambda x:self.tonline.keys().count(x)-1,self.onlineList.keys()))
            if self.alive: self.tonline=self.onlineList
        #FIXME online status
        self.iterationsNumber = self.iterationsNumber + 15 #we sleep 15 in  pollManager
        if self.alive and self.iterationsNumber>13*60 and self.keep_online and self.user.getConfig("keep_online"):
            self.getHttpPage("http://pda.vkontakte.ru/id1")
            self.iterationsNumber = 0
        #print "end loop"
        self.loopDone=True
        return 1
            

    def exit(self):
        self.client.usersOffline(self.jid,self.onlineList.keys())
        self.logout()
        self.alive=0
        #threading.Thread.exit(self)
    def __del__(self):
        self.logout()
        #threading.Thread.exit(self)
    def getSmallAvatar(self,v_id):
        #FIXME
        req=urllib2.Request("http://wap.vkontakte.ru/id%s"%v_id)
        try:
            res=self.opener.open(req)
            page=res.read()
        except urllib2.HTTPError, err:
            print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
            return -1
        dom = xml.dom.minidom.parseString(page)
        imgs=filter(lambda x: x.getAttribute("class")=='pphoto',dom.getElementsByTagName('img'))
        if (len(imgs)):
            url=imgs[0].getAttribute("src")
            req=urllib2.Request(url)
            try:
                res=self.opener.open(req)
                return res.read()
            except urllib2.HTTPError, err:
                print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
                return -1

            print url
        return 0
    def test(self):
        page=self.getHttpPage("http://vkontakte.ru/")
        page2=re.sub("&#x.{1,5}?;","",page)
        m1=page2.find("<!-- End pageBody -->") 
        m2=page2.find("<!-- End bFooter -->") 
        if (m1 and m2):
            page2=page2[:m1]+page2[m2:] 
        print page2
        dom = xml.dom.minidom.parseString(page2)
        print dom.toxml()

#        req=urllib2.Request(url)
#        try:
#            res=self.opener.open(req)
#            page=res.read()
#        except urllib2.HTTPError, err:
#            print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
#            return
#        if (fn):
#            f=open(fn,'w')
#            w.write(page)
#
#        else:
#            #print page.decode("cp1251")
#            page=page[page.find("</div></div>")+12:].decode("cp1251")
#            from lxml import etree
#            import StringIO
#            parser = etree.XMLParser(recover=True)
#            tree   = etree.parse(StringIO.StringIO(page), parser)
#            msgs=tree.xpath('/div/table/tr')
#            print len(msgs)
#            for i in msgs:
#                mt=i.xpath('td/div')
#                #print etree.tostring(i)
#                print "-----------"
#                print etree.tostring(mt[0])
#                print mt[0].findtext(".")
#                #for j in mt[0].getchildren():
#                    #print j
#            #print etree.tostring(tree.getroot())
    def getVcard2(self,v_id, show_avatars=0):
        '''
        Parsing of profile page to get info suitable to show in vcard
        '''
        page = self.getHttpPage("http://vkontakte.ru/id%s"%v_id)
        if not page:
            return {"FN":""}
        parser = etree.XMLParser(recover=True)
        nsd={'x': 'http://www.w3.org/1999/xhtml'}
        tree=etree.parse(res,parser)
        prof=tree.xpath('//*/x:div[@id="userProfile"]',namespaces=nsd)
        if (len(prof)==0):
            print "FIXME search page"
            return None
        prof=prof[0]
        rc=prof.xpath('x:div[@id="rigthColumn"]',namespaces=nsd)
        if (len(rc)==0):
            print "FIXME deleted pages"
            return None
        rc=rc[0]
        pn=rc.xpath('//*/x:div[@class="profileName"]',namespaces=nsd)
        #result["FN"]=pg.
        if (self.user.getConfig("resolve_nick")):
            print "FIXME nick resolve"


