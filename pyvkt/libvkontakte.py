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
import urllib2
import urllib
from urllib import urlencode
import httplib
import pyvkt.general as gen
#from BaseHTTPServer import BaseHTTPRequestHandler as http
import demjson
import cookielib
from cookielib import Cookie
from htmlentitydefs import name2codepoint
from BeautifulSoup import BeautifulSoup,SoupStrainer
import xml.dom.minidom
import time
import hashlib
from os import environ
import re
import base64,copy
import ConfigParser,os,string
from traceback import print_stack, print_exc,format_exc
import logging
import pyvkt.config as conf
#import StringIO

#user-agent used to request web pages
#USERAGENT="Opera/9.60 (J2ME/MIDP; Opera Mini/4.2.13337/724; U; ru) Presto/2.2.0"
USERAGENT="ELinks (0.4pre5; Linux 2.4.27 i686; 80x25)"
#USERAGENT='User-Agent=Mozilla/5.0 (X11; U; Linux i686; ru; rv:1.9.1.4) Gecko/20091016 Firefox/3.5.4'
class tooFastError(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return '"too fast" error'
class authFormError(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'unexpected auth form'
class captchaError(Exception):
    sid=None
    def __init__(self,sid=None, bjid=None):
        self.sid=sid
        self.bjid=bjid
        pass
    def url(self):
        return 'http://vkontakte.ru/captcha.php?s=1&sid=%s'%self.sid
    def __str__(self):
        url='http://vkontakte.ru/captcha.php?s=1&sid=%s'%self.sid
        return 'got captcha request (jid = "%s", sid = "%s", url=%s )'%(repr(self.bjid),self.sid,url)
            
class authError(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'unexpected auth form'
class UserapiSidError(Exception):
    pass
class HTTPError(Exception):
    def __init__(self,err,url):
        self.err=err
        self.url=url
    def __str__(self):
        return '%s [%s]'%(self.err,self.url)
    pass
class RedirectHandler(urllib2.HTTPRedirectHandler):
    #def http_error_301(self, req, fp, code, msg, headers):
        #result = urllib2.HTTPRedirectHandler.http_error_301(
        #self, req, fp, code, msg, headers)
        #result.status = code
        #print 301
        #print headers.dict
        #return result

    def http_error_302(self, req, fp, code, msg, headers):
        result = urllib2.HTTPRedirectHandler.http_error_302(
        self, req, fp, code, msg, headers)
        result.status = code
        redirUrl=headers.dict['location']
        print redirUrl
        p=redirUrl.find('sid=')
        result.sid=redirUrl[p+4:]
        #print sid
        
        #print 302
        #print headers.dict
        return result
class client():
    oldFeed=""
    #onlineList={}
    loopDone=True
    #just counter for loops. use some big number in the beginning
    iterationsNumber = 999999
    # true if there is no loopInternal's in user queue
    tonline={}
    #opener=None
    def __init__(self,jid,email,passw,user,captcha_sid=None, captcha_key=None,ua=False,login=True):
        self.bytesIn = 0
        self.bjid=jid
        self.user=user
        self.dumpPath=conf.get("debug/dump_path")
        self.cachePath=conf.get('storage','cache')
        self.cookPath=conf.get('storage','cookies')
        self.keep_online=True
        self.resolve_links=True
        #FIXME delete 
        
    def readCookies(self):
        self.cjar=cookielib.MozillaCookieJar("%s/%s"%(self.cookPath,self.bjid))
        try:
            self.cjar.clear()
            self.cjar.load()
        except IOError,e :
            logging.warning("cant read cookie (%s)"%str(e))
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cjar))
    def saveCookies(self):
        if self.user.getConfig("save_cookies"):
            try:
                self.cjar.save()
            except:
                logging.exception('can\'t save cookies')
    def setCookies(self,cookieVal):
        cjar.clear()
        #TODO
    def setCookie(self, name, val, site='vkontakte.ru'):
        #FIXME arg names
        c=cookielib.Cookie(version=0, name=name, value=val, 
        port=None, port_specified=False, domain='.%s'%site, 
        domain_specified=True, domain_initial_dot=True, path='/', 
        path_specified=True, secure=False, expires=int(time.time()+1e7), 
        discard=False, comment=None, comment_url=None, rest={}, rfc2109=False)
        self.cjar.set_cookie(c)
    def getCookies(self):
        ret=[(i.domain[1:], i.name,i.value) for i in self.cjar]
        return ret
    def login(self,email,passw,captcha_sid=None, captcha_key=None):
        data={'op':'a_login_attempt'}
        if (captcha_key and captcha_sid):
            logging.warning('ligin with captha: %s/%s'%(captcha_sid, captcha_key))
            data['captcha_key']=captcha_key
            data['captcha_sid']=captcha_sid
        #hdrs={'Referer': 'http://vkontakte.ru/index.php', 'X-Requested-With':'XMLHttpRequest'}
        tpage=self.getHttpPage('http://vkontakte.ru/login.php',data)
        if (tpage[:20]=='{"ok":-2,"captcha_si'):
            sid=None
            try:
                cdata=demjson.decode(tpage)
                sid=cdata['captcha_sid']
            except Exception,e:
                logging.error('decode failed: %s'%e)
                raise
            raise captchaError(sid=sid, bjid=self.bjid)
            return
        authData={'vk':'1','email':email.encode('utf-8'), 'pass':passw.encode('utf-8')}
        tpage=self.getHttpPage("http://login.vk.com/?act=login",authData)
        #print tpage
        i=tpage.find("id='s' value='")
        i+=14
        p=tpage.find("'",i+1)
        s=tpage[i:p]
        self.getHttpPage("http://vkontakte.ru/login.php?op=slogin&redirect=1",{'s':s})
        
    def genCaptchaSid(self):
        ret=''
        for i in os.urandom(10):
            ret='%s%s'%(ret,ord(i)%100)
        return ret
    def userapiLogin(self,email,passw,captcha_sid=None, captcha_key=None):
        #TODO use cookies
        #d={'email':email,'pass':passw}
        d={'login':'force','site':'2','email':email,'pass':passw, 'id':0, 'fccode':0, 'fcsid':0}
        if (captcha_key and captcha_sid):
            d['fcsid']=captcha_sid
            d['fccode']=captcha_key
        print d
        dat=urllib.urlencode(d)
        op=urllib2.build_opener(RedirectHandler())
        url='http://login.userapi.com/auth?%s​'%dat
        req=urllib2.Request(url)
        print url
        f=op.open(req)
        try:
            self.sid=f.sid
        except:
            print f
            print f.read()
            print f.headers
        logging.warning('userapi login: got sid=%s'%self.sid)
        # -1 - wrong auth
        # -2 - wrong captcha
        # -3 - wrong auth, captcha request
        # -4 - wrong auth, no captcha
        if (self.sid in (-2,-3)):
            logging.warning('captcha request')
            csid=self.genCaptchaSid()
            url='http://userapi.com/data?act=captcha&csid=%s'%csid
            print url
            return 
        self.readCookies()
        print self.getHttpPage("http://vkontakte.ru/login.php?op=slogin&redirect=1",{'s':self.sid})

        #print f
    def getHttpPage(self,url,params=None,cjar=None, headers={}):
        """ get contents of web page
            returns u'' if some of errors took place
        """
        #if (type(params)==type({})):
            #for i in params:
                #if type(params[i]==unicode):
                    #params[i]=params[i].encode('utf-8')
        if (type(params)==type({})):
            params=urllib.urlencode(params)
        if params:
            req=urllib2.Request(url,params)
        else:
            req=urllib2.Request(url)
        req.addheaders = [('User-agent', USERAGENT)]
        for i in headers:
            req.addheaders.append((i,headers[i]))
        #print repr(req)
        try:
            res=self.opener.open(req)
            #print res.url
            page=res.read()
        except urllib2.HTTPError, err:
            raise HTTPError(err.code,req.get_full_url())
            #return ''
        except IOError, e:
            msg="IO Error"
            if hasattr(e, 'reason'):
                msg=msg+"\nReason: %s."%(e.reason)
            elif hasattr(e, 'code'):
                msg=msg+"\nCode: %s."%(e.code)
            raise HTTPError(msg,req.get_full_url())
        except httplib.BadStatusLine, err:
            raise HTTPError("HTTP bad status line error",req.get_full_url())
        except httplib.HTTPException, err:
            raise HTTPError("HTTP exception.",req.get_full_url())
        self.bytesIn += len(page)
        if (cjar):
            cjar.make_cookies(res,req)
        return page

    def checkPage(self,page):
        if (page.find(u'<div class="simpleHeader">Слишком быстро...</div>'.encode("cp1251"))!=-1):
            logging.warning ("%s: too fast"%self.bjid)
            raise tooFastError
        if (page.find('<form method="post" name="login" id="login" action="/login.php"')!=-1):
            logging.warning ("%s: got login form"%self.bjid)
            raise authFormError
        return 

    def logout(self):
        #self.client.usersOffline(self.bjid,self.onlineList)
        self.onlineList={}
        if not self.user.getConfig("save_cookies"):
            self.getHttpPage("http://vkontakte.ru/login.php","op=logout")
            try:
                os.unlink("%s/%s"%(self.cookPath,self.bjid))
            except:
                pass
        #print "%s: logout"%self.bjid
    def getFeed(self):
        s=self.getHttpPage("http://vkontakte.ru/feed2.php","mask=ufmepvnogq").decode("cp1251").strip()
        if not s or s[0]!=u'{':
            return {}
        s=s.replace(u':"',u':u"')
        try:
            return eval(s,{"null":None},{})
        except:
            logging.exception("JSON decode error")
            #print_exc()
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
                #print "empty list"
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
        except Exception, e:
            logging.warning('json decode error: %e',e)
            return {}
        ret={}
        for i in flist:
            ret[i[0]]={"last":i[1]['l'].decode("cp1251"),"first":i[1]['f'].decode("cp1251")}
            #print type(i[1]['l'])
        #print "--",ret
        return ret
    def getOnlineList2(self):
        fl=self.userapiRequest(act='friends_online',id=self.v_id)
        ret={}
        for i in fl:
            if (len(i)<3):
                logging.warning('onlinelist2: bad item')
                logging.warning(repr(i))
                continue
            fn=i[1].split()
            if i[2]!="images/question_a.gif" and  i[2]!="images/question_b.gif":
                ret[i[0]]={'last':fn[1],'first':fn[0],'avatar_url':i[2]}
            else:
                ret[i[0]]={'last':fn[1],'first':fn[0],'avatar_url':u""}
        return ret
            

    def getOnlineList(self):
        try:
            return self.getOnlineList2()
        except UserapiSidError:
            raise
        except:
            logging.warning(format_exc())
            #print "getOnlineList: userapi request failed"
            #print_exc()
        ret={}
        page=self.getHttpPage("http://vkontakte.ru/friend.php","act=online&nr=1")
        if not page:
            return {}
        return self.flParse(page)

    def dumpString(self,string,fn="",comm='parser error'):
        if (self.dumpPath==None or self.dumpPath==''):
            return
        fname="%s/%s-%s"%(self.dumpPath,fn,int(time.time()))
        fil=open(fname,"w")
        if (type(string)==unicode):
            string=strng.encode("utf-8")
        fil.write(string)
        fil.close()
        logging.warning("%s: page saved to %s"%(comm,fname))
    def getHistory(self,v_id):
        try:
            return self.getHistory2(v_id)
        except:
            print "userapi failed"
            print_exc()
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
    def getHistory2(self,v_id):
        dat=self.userapiRequest(act='message',id=v_id, to=15)
        ret=[]
        for i in dat['d']:
            if (i[3][0]==self.v_id):
                t=u'out'
            else:
                t=u'in'
            #print i[1],i[2][0]
            ret.append((t,i[2][0]))
        return ret
        #print dat
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
        if (v_id==0):
            v_id=self.v_id
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
    def cutPage(self,page):
        st=page.find('<div id="rightColumn">')
        end=page.find('<div id="wall" ')
        end2=page.find('<div id="education" class="flexOpen">')
        if (end2!=-1):
            end=end2
        
        #end=page.rfind('</div>',st,end)
        #end=page.rfind('</div>',st,end)
        #print st,end
        np=page[st:end]+'</div>'
        #print page.decode('cp1251').encode('utf-8')
        #print 'original length: %s'%len(page)
        #print 'new length: %s'%len(np)
        #print np.decode('cp1251').encode('utf-8')
        #print
        return np
    def getVcard_new(self,v_id, show_avatars=0,page=None):
        if (not page):
            opage = self.getHttpPage("http://vkontakte.ru/id%s"%v_id)
        else:
            opage=page
        time.sleep(0.5)
        if not opage:
            return {"FN":u""}
        result={}
        page=self.cutPage(opage)
        #print page
        #dom=xml.dom.minidom.parseString(page.decode('cp1251').encode('utf-8'))
        rc=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
        #FIXME closed pages
        #FIXME deleted pages
        profName=rc.find("div", {"class":"profileName"})
        if (profName==None):
            self.checkPage(opage)
            if (opage.find(u'<p>Для того, чтобы просматривать информацию о других, необходимо заполнить информацию о себе как минимум на <b>30%</b>.</p>'.encode('cp1251'))!=-1):
                result['Error']=u'Для того, чтобы просматривать информацию о других, необходимо заполнить информацию о себе как минимум на 30%'
            else:
                self.dumpString(page,'vcard-new','"deleted" page')
                self.dumpString(opage,'vcard-new-orig','"deleted" page')
                #result["NICKNAME"]='deleted'
                result['Error']=u'Внутренняя ошибка транспорта. Возможно, страница удалена.'
            return result
            
        result['FN']=unicode(profName.find(name="h2").string).encode("utf-8").strip()
        if (self.user.getConfig("resolve_nick")):
            #FIXME 
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
        else:
            result["NICKNAME"]=result["FN"]
            del result["FN"]
        #now parsing additional user data
        #there are several tables
        if (rc.find('div',{'class':'alertmsg'})):
            print 'hidden page'
            result['availability']=u'Страница скрыта владельцем'
            return result
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
        except Exception,e:
            logging.warning('getvcard: %s'%str(e).replace('\n','|'))
        return result
        
    def getVcard(self,v_id, show_avatars=0,fast=False):
        '''
        Parsing of profile page to get info suitable to show in vcard
        '''
        try:
            return self.getVcard_new(v_id)
        except Exception,e:
            logging.warning ('getvcard_new failed for id%s'%v_id)
            logging.warning(str(e))
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
            div=cont.find(name='div',style="overflow: hidden;")
            if div:
                result['FN']=div.string
            else:
                result['FN']=u""
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
        else:
            result["NICKNAME"]=result["FN"]
            del result["FN"]
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
        #FIXME avatars!!!
        #avatars are asked only if needed
        #if lc and show_avatars and self.user.getConfig("vcard_avatar"):
        #    photourl=lc.find(name="img")['src']
        #    #if user has no avatar we wont process it
        #    if photourl!="images/question_a.gif" and  photourl!="images/question_b.gif":
        #        result["PHOTO"] = photourl
                #    fpath=''
                #    photo=None
                #    if (self.cachePath):
                #        pos=photourl.find(".ru/u")
                #        #TODO don't save avatars from "search"
                #        if (pos!=-1):
                #            fname=photourl[pos+4:].replace("/","_")
                #            fpath="%s/avatar-%s"%(self.cachePath,fname)
                #            ifpath="%s/img-avatar-%s"%(self.cachePath,fname)
                #            try:
                #                cfile=open(fpath,"r")
                #                photo=cfile.read()
                #                cfile.close()
                #            except:
                #                pass
                #                #print "can't read cache: %s"%fname
                #    if not photo:
                #        photo = base64.encodestring(self.getHttpPage(photourl))
                #        if photo and self.cachePath and rc!=None:
                #            #FIXME check for old avatars
                #            fn="avatar-u%s"%v_id
                #            fn2="img-avatar-u%s"%v_id
                #            l=len(fn)
                #            l2=len(fn)
                #            fname=None
                #            for i in os.listdir(self.cachePath):
                #                if (i[:l]==fn or i[:l2]==fn2):
                #                    os.unlink("%s/%s"%(self.cachePath,i))
                #            cfile=open(fpath,'w')
                #            cfile.write(photo)
                #            cfile.close()
                #            #ifile=open(ifpath,'w')
                #            #ifile.write(imgdata)
                #            #ifile.close()
                #            #self.client.avatarChanged(v_id=v_id,user=self.bjid)
                #    if photo:
                #        result["PHOTO"]=photo
        return result
    def getVcard2(self,v_id, show_avatars=0):
        '''
        Parsing of profile page to get info suitable to show in vcard
        '''
        dat=self.userapiRequest(act='profile',id=v_id)
        print dat

    def getAvatar(self,photourl,v_id,gen_hash=0):
        """returns avatar and its hash if asked. Downloads photo if not in cache"""
        if photourl!="images/question_a.gif" and  photourl!="images/question_b.gif" and photourl[:7]=="http://":
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
                        if gen_hash:
                            hash=hashlib.sha1(base64.decodestring(photo)).hexdigest()
                    except:
                        pass
                        #print "can't read cache: %s"%fname
            if not photo:
                picture=self.getHttpPage(photourl)
                photo = base64.encodestring(picture)
                if gen_hash:
                    hash=hashlib.sha1(picture).hexdigest()
                if photo and self.cachePath:
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
            if gen_hash:
                return photo,hash
            else:
                return photo
        #print "getAvatar: No avatars (%s,%s)"%(photourl,v_id)
        return 
        
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
            print "SearchUsers: wrong page format"
            self.dumpString(page,"search_wrong_format")
            return None
        return result

    def addNote(self,text,title=u""):
        """ Posts a public note on vk.com site"""
        page = self.getHttpPage("http://pda.vkontakte.ru/newnote")
        if not page:
            return None
        dom=xml.dom.minidom.parseString(page)
        fields=dom.getElementsByTagName("form")
        url="http://pda.vkontakte.ru"+fields[0].attributes["action"].value.replace("&amp;","&")
        dat={'title':title.encode("utf-8"),'post':text.encode("utf-8")}
        res=unicode(self.getHttpPage(url,urlencode(dat)),"utf-8")
        if not res or not res.find(u"аметка добавлена"):
            return 1
        return 0
    def getStatus(self):
        dat=self.userapiRequest(act='activity',to=1,id=self.v_id)
        print dat['h']
        return (dat['h'],dat['d'][0][5])
        

    def setStatus(self,text,ts=None):
        """ Sets status (aka activity) on vk.com site"""
        #if (ts):
            #res=self.userapiRequest(act='set_activity', text=text,ts=ts)
            #print res
        #return
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
        #print page
        if not page:
            return {"text":"<internal error: can't get message http://vkontakte.ru/mail.php?act=show&id=%s >"%msgid,"from":"error","title":""}
        try:
            dom = xml.dom.minidom.parseString(page)
            form=dom.getElementsByTagName("form")[0]
        except:
            print_exc()
            self.dumpString(page,"msg-no-form")
            return {"text":"<internal error: can't get message. http://vkontakte.ru/mail.php?act=show&id=%s >"%msgid,"from":"error","title":""}

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
                #print k
                msg="%s%s"%(msg,k.toxml())
            k=k.nextSibling
        msg=msg.replace("<br/>","\n")[6:-6]
        ret["text"]=msg
        return ret
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
            print "SendMessage_legacy: unknown error.. saving page.."
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
        print page
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
        #print page
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
        #print data
        page=self.getHttpPage("http://pda.vkontakte.ru/mailsent?pda=1",urlencode(data))
        #print page
        if not page:
            print "Sending message: HTTP Error"
            return 1
        if (page.find('<div id="msg">Сообщение отправлено.</div>')!=-1):
            return 0
        elif (page.find('Вы попытались загрузить более одной однотипной страницы в секунду')!=-1):
            print "Sending message: too fast sending messages"
            return 2
        print "Sending message: unknown error"
        return -1
    def getFriendList2(self):
        fl=self.userapiRequest(act='friends',id=self.v_id)
        ret={}
        for i in fl:
            fn=i[1].split()
            try:
                ret[i[0]]={'last':fn[1],'first':fn[0]}
            except IndexError:
                ret[i[0]]={'first':fn[0]}
        return ret
    def getFriendList(self):
        try:
            return self.getFriendList2()
        except:
            logging.exception("getFriendList2 failed")
        page = self.getHttpPage("http://vkontakte.ru/friend.php?nr=1")
        if not page:
            return {}
        return self.flParse(page)

    def isFriend(self,v_id):
        """ check friendship status
        0 - friend
        1 - not friend
        2 - friendship requested
        -1 - error
        """
        try:
            dat=self.userapiRequest(act='profile',id=v_id)
        except:
            print_exc()
            return -1
        #print dat["isf"]
        if (dat["isf"]):
            return 0
        if (dat["isi"]):
            return 2
        return 1
        #print dat["isi"]
        page = self.getHttpPage("http://pda.vkontakte.ru/id%s"%v_id)
        #print page
        if not page: 
            return -1
        if (page.find('<div id="error">')!=-1):
            #hidden page
            return 1
        if (page.find('<a href="/addfriend%s"'%v_id)==-1):
            return 0
        if (page.find('<a href="/deletefriend%s"'%v_id)==-1):
            return 1
        return 2

    def addDeleteFriend(self,v_id,isAdd):
        if (isAdd):
            page = self.getHttpPage("http://pda.vkontakte.ru/addfriend%s"%v_id)
            if page:
                return 0
            return -1
        else:
            #print "%s: del friend %s"%(self.bjid,v_id)
            page = self.getHttpPage("http://pda.vkontakte.ru/deletefriend%s"%v_id)
            if page:
                return 0
            return -1

    def getSelfId(self):
        feed=self.getFeed()
        try:
            if feed['user']['id']:
                self.v_id=feed['user']['id']
            return feed['user']['id']
        except:
            pass
        return -1
        page=self.getHttpPage("http://vkontakte.ru/feed2.php")
        if (not page):
            return -1
        if (page=='{"user": {"id": -1}}' or page[0]!='{'):
            return 1
        return 0

    def dummyRequest(self):
        """ request that means nothing"""
        req=urllib2.Request("http://wap.vk.com/")
        try:
            res=self.opener.open(req)
            page=res.read()
        except urllib2.HTTPError, err:
            print "HTTP error %s.\nURL:%s"%(err.code,req.get_full_url())
            return -1
    def exit(self):
        self.logout()

    def getCalendar(self,month,year):
        #import string
        page=self.getHttpPage("http://vkontakte.ru/calendar_ajax.php?month=%s&year=%sp"%(month,year))
        bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
        #print bs.prettify()
        ret={}
        days=bs.findAll("td",attrs={'class':"dayCell"})
        for i in days:
            d=i.div
            if (d and d.nextSibling):
                
                n=int(i.div.string)
                #print n
                ret[n]=[]
                #print i.prettify()
                evs=i.findAll("div",attrs={"class":"calPic"})
                for k in evs:
                    #print k.a["href"]
                    ret[n].append(k.a["href"][1:])
        return ret
    def getNews(self):
        types={"http://vkontakte.ru/images/icons/person_icon.gif":"status"}
        page=self.getHttpPage("http://vkontakte.ru/news.php")
        bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
        #print bs
        mf=bs.find("div",attrs={'id':"mainFeed"})
        days=mf.findAll("div",attrs={'style':"padding:10px 10px 20px 10px;"})
        #print days[0]
        print bs.find("div",attrs={"id":'checkboxFeed'})
        for i in [days[0]]:
            events=i.findAll("table")
            #print i
            #print len(events)
            for j in events:
                ev={}
                tds=j.findAll("td")
                #print tds
                pic=tds[0].img["src"]
                #print pic
                try:
                    ev["type"]=types[pic]
                    print ev["type"]
                except:
                    pass
                else:
                    ev["id"]=tds[1].a["href"][3:]
                    if (ev["type"]=="status"):
                        print td[1]
                        return
    def getStatusList(self):
        try:
            return self.getStatusList2()
        except HTTPError,e:
            logging.warning('userapi: http error '+str(e).replace('\n',', '))
        except:
            logging.warning(format_exc())
            print "getStatusList: userapi request failed"
        ret={}
        #print "start"
        for n in [0,1,2]:
            page = self.getHttpPage("http://pda.vkontakte.ru/news?from=%s"%n)
            if not page:
                return {}
            try:
                dom = xml.dom.minidom.parseString(page)
            except Exception ,exc:
                page=''.join([c for c in page if c in string.printable])
                try:
                    dom = xml.dom.minidom.parseString(page)
                except Exception ,exc:
                    for i in ["&#11;"]:
                        page=page.replace(i,"")
                    try:
                        dom = xml.dom.minidom.parseString(page)
                    except:
                        print "cant parse news page (%s)"%exc.message
                        self.dumpString(page,"expat_err")
                        page=None
                    else:
                        print "fixed by filter (2)"
                else:    
                    print "fixed by filter (1)"
                
            if (page):
                for i in dom.getElementsByTagName("small"):
                    i.parentNode.removeChild(i)
                dom.normalize()
                cont=None
                for i in dom.getElementsByTagName("div"):
                    #print
                    if i.getAttribute("class")=="stRows":
                        cont=i
                        break
                if (not cont):
                    # empty page?
                    #print "cant parse news"
                    #self.dumpString(page,"news_notfound")
                    return {}
                for i in cont.getElementsByTagName("div"):
                    links=i.getElementsByTagName("a")
                    v_id=links[0].getAttribute("href")[3:]
                    fe=links[0].nextSibling
                    del links[0]
                    if (not len(links)):
                        if (not ret.has_key(v_id)):
                            ret[v_id]=gen.unescape(fe.data.encode("utf-8"))
        #print "end"
        return ret
    def getStatusList2(self):
        sl=self.userapiRequest(act='updates_activity',to='50')
        sl=sl['d']
        if (not sl):
            return {}
        sl.reverse()
        ret={}
        for i in sl:
            ret[i[1]]=i[5]
            #print ,i[4],i[5]
        return ret
        #print type(sl)
    def getWallMessages(self,v_id=0):
        #deprecated
        page = self.getHttpPage("http://vkontakte.ru/wall.php?id=%s"%v_id)
        bs=BeautifulSoup(page,convertEntities="html",smartQuotesTo="html",fromEncoding="cp-1251")
        wall=bs.find("div",id='wallpage')
        #print wall
        ret=[]
        
        targ=wall.findAll("div",recursive=False)[1]
        for i in targ.findAll("div",recursive=False,id=re.compile("wPost.*")):
            cont= i.div.table.tr.findAll("td",recursive=False)[1]
            cd=cont.findAll("div",recursive=False)
            v_id=cd[0].a['href'][3:]
            pinfo={"v_id":int(v_id),"from":cd[0].a.string,"date":cd[0].small.string}
            #print v_id
            try:
                ptype=cd[1].div["class"]
                if (ptype=="audioRowWall"):
                    ttds=cd[1].div.table.tr.findAll("td")
                    ld=eval(ttds[0].img["onclick"][18:-1],{},{})
                    tdata=ttds[1].findAll(text=True)
                    if (self.resolve_links):
                        pinfo["dlink"]="http://cs%s.vk.com/u%s/audio/%s.mp3"%(ld[1],ld[2],ld[3])
                    else:
                        pinfo["dlink"]='direct links are disabled'
                    pinfo["type"]='audio'
                    pinfo["desc"]="%s - %s (%s)"%(tdata[1],tdata[3],tdata[5])
                else:
                    pinfo["type"]='unknown'
                    pinfo["text"]=ptype
                    print ptype
            except:
                #print "simple message"
                try:
                    cl=cd[1].a["class"]
                    if (cl=="Graffiti"):
                        pinfo["type"]='graffity'
                        pinfo["link"]=cd[1].a.img["src"]
                    elif (cl=='iLink'):
                        icon=cd[1].img["src"]
                        links=cd[1].findAll("a")
                        pinfo['desc']=links[0].string
                        #print links
                        if (icon=='/images/icons/movie_icon.gif'):
                            print cd[1].findAll('img')[1]['src']
                            pinfo["type"]='video'
                        elif(icon=='/images/icons/pic_icon.gif'):
                            pinfo["type"]='photo'
                        else:
                            pinfo["type"]='unknown'
                        try:
                            pinfo["link"]="http://vkontakte.ru%s"%links[1]["href"]
                            pinfo["thumb"]=links[1].img["src"]
                        except:
                            print_exc()
                except:
                    #if (cd[1].div):
                        #links=sd[1].div.findAll("a")
                        #print links
                    pinfo["type"]='text'
                    pinfo["text"]=string.join(cd[1].findAll(text=True),'\n')
            
            #print pinfo
            ret.append((int(i["id"][14:]),pinfo))
        #print ret
        return ret
    def getWall(self,v_id=0):
        if (not v_id):
            v_id=self.v_id
        dat=self.userapiRequest(act='wall',id=v_id,to='20')
        types=['text','photo','graffiti','video','audio']
        ret=[]
        if not "d" in dat:
            return ret
        for i in dat['d']:
            try:
                t=types[i[2][1]]
            except IndexError:
                t='text'
            #print 'id',i[3][0]
            pinfo={'type':t,'v_id':i[3][0],'from':i[3][1].replace('\t',' '),'date':time.strftime("%d.%m.%Y %H:%MZ",time.gmtime(i[1]))}
            try:
                pinfo['desc']=i[2][2]
            except:
                pass
            if (t=='text'):
                try:
                    pinfo['text']=i[2][0]
                except:
                    pinfo['text']=""
                pass
                try:
                    pinfo['text']=pinfo['text'].encode('cp1251').decode('utf-8')
                except:
                    pass            
            elif (t=='audio'):
                #del pinfo['thumb']
                pinfo['dlink']=i[2][3]
            elif (t=='video'):
                pinfo['dlink']=i[2][4]
                pinfo['thumb']=i[2][3]
                pinfo['link']='http://vkontakte.ru/video%s_%s'%(i[2][5],i[2][6])
                #print pinfo
            elif (t=='graffiti'):
                pinfo['dlink']=i[2][4]
                pinfo['thumb']=i[2][3]
                pinfo['link']='http://vkontakte.ru/graffiti%s?from_id=%s'%(i[2][6],i[2][5])
            elif (t=='photo'):
                pinfo['dlink']=i[2][4]
                pinfo['thumb']=i[2][3]
                pinfo['link']='http://vkontakte.ru/photo%s_%s'%(i[2][5],i[2][6])
            if (not self.resolve_links):
                pinfo['dlink']=u'прямые ссылки отключены админом'
                    
            ret.append((i[3][0],pinfo))
        return ret
        #print ret
        #print dat

    def readWallMsg(self,msg):
        ret={'id':msg[0]}
        msgtime=msg[1]
        ret['text']=msg[2]
        ret['from']=(msg[3][0],msg[3][1])
        ret['to']=(msg[4][0],None)
        #print msg
        return ret
    def getWallState(self):
        dat=self.userapiRequest(act='wall',id=self.v_id,to=0)
        #print dat
        return dat['h']
    def getWallHistory(self,ts):
        ret=[]
        dat=self.userapiRequest(act='wall',id=self.v_id,ts=ts)
        #logging.warning(ts)
        #logging.warning(self.getWallState())
        #logging.warning(dat['h'])
        try:
            for i in dat['h']:
                act=i[1]
                #print 'ts: %s, act=%s' %(i[0],i[1])
                #print i
                if (act=='add'):
                    ret.append((i[0],'add',self.readWallMsg(i[2])))
                    #print self.readWallMsg(i[2])
                if (act=='del'):
                    ret.append((i[0],'del',None))
                    pass
            return ret
        except TypeError:
            #logging.warning("wallhistory: bad format\n"+repr(dat))
            return False
        #print dat
    def getWallFast(self,v_id,num=10):
        #h=63000002

        #TODO history 
        dat=self.userapiRequest(act='wall',id=v_id,to=num)
        
        msgs=dat['d']
        for i in msgs:
            msgid,stime,txt,snd,rcv=i
            try:
                print "id%s -> id%s: %s '%s'"%(snd[0],rcv[0],txt[0],txt[2])
            except:
                print "id%s -> id%s: '%s'"%(snd[0],rcv[0],txt[0])
    def userapiRequest(self,**kw):
        #import simplejson as json
        nkw=kw
        nkw['sid']=self.sid
        nkw['from']='0'
        if (not nkw.has_key('to')):
            nkw['to']='1000'
        url='http://userapi.com/data?'
        for k in nkw:
            url="%s%s=%s&"%(url,k,nkw[k])
        #print url
        try:
            page=self.getHttpPage(url)
        except HTTPError, e:
            raise HTTPError (e.err,'userapi: %s'%str(kw))
        #print page
        if (page=='{"ok": -2}'):
            raise captchaError
        try:
            page=page.decode('utf-8')
        except:
            try:
                page=page.decode('cp1251')
            except:
                logging.warning("strange userapi charset")
        #print page
        #ret=json.loads(page)
        try:
            ret= demjson.decode(page,strict=False)
        except:
            logging.warning("json error. trying to remofe 'fr.' blocks...")
            sr=re.search(',"fr":{.*?},"fro":{.*?},"frm":{.*?}',page)
            if (sr):
                page=page[:sr.start()]+page[sr.end():]
            try:
                ret= demjson.decode(page,strict=False)
            except Exception,e:
                logging.error("userapi failed\n'%s'\n%s"%(repr(page),str(e)))
                raise e
            #sr=re.search(',"fro":{.*?}',page)
            #page=page[:sr.start()]+page[sr.end():]
            #sr=re.search(',"frm":{.*?}',page)
            #page=page[:sr.start()]+page[sr.end():]
        try:
            if (ret['ok']==-2):
                raise captchaError
            elif (ret['ok']==-1):
                raise UserapiSidError()
                #logging.error('userapiRequest: GREPME userapi session error (%s)'%self.bjid)
        except (KeyError,TypeError):
            pass
        return ret
        
