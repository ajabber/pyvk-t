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
import general as gen
#from BaseHTTPServer import BaseHTTPRequestHandler as http
import demjson
from BeautifulSoup import BeautifulSoup,SoupStrainer
import xml.dom.minidom
import time
import hashlib
import re
import base64
import os, string
from traceback import print_exc,format_exc
import logging, pycurl
import config as conf
import weakref
from pprint import pprint
try:
    import json
except:
    pass
import StringIO

http_traffic=0
http_requests=0
#user-agent used to request web pages
USERAGENT="Opera/9.60 (J2ME/MIDP; Opera Mini/4.2.13337/724; U; ru) Presto/2.2.0"
API_PERMS=2+4+8+1024+4096+8192
#USERAGENT="ELinks (0.4pre5; Linux 2.4.27 i686; 80x25)"
#USERAGENT='User-Agent=Mozilla/5.0 (X11; U; Linux i686; ru; rv:1.9.1.4) Gecko/20091016 Firefox/3.5.4'
def readForms(page):
    "reads input's with default values"
    imatches = re.findall(
        '<input.*name=[\'"](?P<name>\w+)[\'"] .*value=[\'"](?P<value>\w+)[\'"]', 
                      page)
    args = {}
    for name, val in imatches:
        args[name]=val
    return args
def deleteTags(s):
    replaceList={'<br>':'\n'}
    for i in replaceList:
        s=s.replace(i, replaceList[i])
    return s
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
class UserapiCaptchaError (captchaError):
    bjid=None
    sid=None
    def __init__ (self,sid, fcsid):
        self.sid=sid
        self.fcsid=fcsid
    pass
class authError(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'unexpected auth form'
class UserapiSidError(Exception):
    pass
class PrivacyError(Exception):
    def __str__(self):
        return 'privacy error'
class HTTPError(Exception):
    def __init__(self,err,url):
        self.err=err
        self.url=url
    def __str__(self):
        return '%s [%s]'%(self.err,self.url)
    pass
class ApiError(Exception):
    pass
class AppAuthError(ApiError):
    def __init__(self,err,url):
        self.err=err
        self.url=url

class ApiAuthError(ApiError):
    pass

class AppPermsError(ApiAuthError):
    pass

class ApiPermissionMissing(ApiError):
    pass
class UserapiJsonError(Exception):
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
class client(object):
    __slots__=['tonline', 'captchaRequestData', 'bjid', 'user', 'dumpPath',
               'cachePath', 'c','sid','v_id', 'api', 'api_sid', 'api_secret', 
               'api_active']
    #onlineList={}
    #just counter for loops. use some big number in the beginning
    iterationsNumber = 999999

    def __init__(self,jid,user):
        # true if there is no loopInternal's in user queue
        self.tonline={}
        # Данные запроса, вызвавшего капчу юзерапи
        self.captchaRequestData={}
        self.bjid=jid
        self.api_secret=''
        self.api_sid=''
        self.api_active=False
        if (user):
            self.user=weakref.ref(user)
        else:
            self.user=None
        self.dumpPath=conf.get("debug/dump_path")
        self.cachePath=conf.get('storage','cache')
        self.c=pycurl.Curl()
        self.c.setopt(pycurl.NOSIGNAL,1)
        self.c.setopt(pycurl.TIMEOUT,10)
        self.c.setopt(pycurl.FOLLOWLOCATION, 0)
        self.c.setopt(pycurl.COOKIELIST,str('ALL'))
        self.c.setopt(pycurl.COOKIELIST,str('Set-Cookie: test=0; domain=eqx.su'))
        #c.setopt(pycurl.MAXREDIRS, 5)
        #FIXME delete 
        
    def initCookies(self):
        self.c.setopt(pycurl.COOKIELIST,str('ALL'))
        self.c.setopt(pycurl.COOKIE, '')
    def setCookie(self, name, val, site='vkontakte.ru'):
        #FIXME arg names
        self.c.setopt(pycurl.COOKIELIST,str('Set-Cookie: %s=%s; domain=.%s'%(name,val,site)))
        #self.cookieStr='%s %s=%s;'%(self.cookieStr,name,val)
    def getCookies(self):
        if True:
            return self.getCookies_curl()
    def login(self,email,passw,captcha_sid=None, captcha_key=None):
        data={'op':'a_login_attempt'}
        if (captcha_key and captcha_sid):
            logging.warning('login with captha: %s/%s'%(captcha_sid, captcha_key))
            data['captcha_key']=captcha_key
            data['captcha_sid']=captcha_sid
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
        authData={'email':email.encode('cp1251'), 'pass':passw.encode('cp1251')}
        # expire='' vk=''
        tpage=self.getHttpPage("http://login.vk.com/?act=login",authData)
        i=tpage.find("name='s' value='")
        i+=16
        p=tpage.find("'",i+1)
        s=tpage[i:p]
        self.getHttpPage("http://vkontakte.ru/login.php?op=slogin&redirect=1&to=&request_method=post",{'s':s})
        
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
        op=urllib2.build_opener(RedirectHandler(),urllib2.ProxyHandler())
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
    
    def getCookies_curl(self):
        cl=self.c.getinfo(pycurl.INFO_COOKIELIST)
        ret=[]
        for i in cl:
            vl=i.split('\t')
            if (vl[0]!='unknown'):
                ret.append((vl[0][1:],vl[5],vl[6]))
        return ret
        
    def getHttpPage(self,url,params=None, referer=None,files=None, hdrFunction=None):
        c=self.c
        #print '\n\n-----------------------\n\n'
        #print url
        #print params
        c.setopt(pycurl.URL,str(url))
        
        c.setopt(pycurl.POST,0)
        if (files):
            #we expect each file in form (fieldName,fileName)
            c.setopt(c.POST,1)
            kv=[(i,str(params[i])) for i in params]
            for file in files:
                kv.append((file[0],(pycurl.FORM_FILE,file[1])))
            #print kv
            c.setopt(c.HTTPPOST,kv)

            params=None
        if (type(params)==type({})):
            params=urllib.urlencode(params)
            #c.setopt(pycurl.POST,1)
            #kv=[(i,str(params[i])) for i in params]
            #c.setopt(pycurl.HTTPPOST,kv)
            #params=None
            #FIXME
        if (params):
            c.setopt(pycurl.POST,1)
            c.setopt(pycurl.POSTFIELDS, params)
        if (referer):
            c.setopt(pycurl.REFERER,referer)
        #c.setopt(pycurl.USERAGENT,USERAGENT)
        #c.setopt(pycurl.VERBOSE,255)
        b = StringIO.StringIO()
        c.setopt(pycurl.WRITEFUNCTION, b.write)
        if (hdrFunction):
            c.setopt(pycurl.HEADERFUNCTION, hdrFunction)
        else:
            def hdrHandler(buf):
                if 'Location' in buf:
                    loc_url=':'.join(buf.split(':')[1:])
                    logging.warn("got Location header '%s' [%s] "%
                                 (loc_url.strip(), url))
            c.setopt(pycurl.HEADERFUNCTION, hdrHandler)            
        try:
            c.perform()
        except pycurl.error,e:
            raise HTTPError(str(e),url)
        ret=b.getvalue()
        global http_requests,http_traffic
        http_requests+=1
        http_traffic+=len(ret)
        #print ret.decode('cp1251')
        #print '----'
        return ret

    def checkPage(self,page):
        if (page.find(u'<div class="simpleHeader">Слишком быстро...</div>'.encode("cp1251"))!=-1):
            logging.warning ("%s: too fast"%self.bjid)
            raise tooFastError
        if (page.find('<form method="post" name="login" id="login" action="/login.php"')!=-1):
            logging.warning ("%s: got login form"%self.bjid)
            raise authFormError
        return 

    def logout(self):
        pass
    
    def getFeed(self):
        s=self.getHttpPage("http://vkontakte.ru/feed2.php","mask=ufmpvnoq").decode("cp1251").strip()
        if not s or s[0]!=u'{':
            return {}
        s=s.replace(u':"',u':u"')
        try:
            return eval(s,{"null":None},{})
        except:
            logging.exception("JSON decode error")
            #print_exc()
        return {}
    def apiRequest(self, method, raw=False, **kwargs):
        req_vars = kwargs
        req_vars['method'] = method
        #print req_vars
        req_vars['api_id'] = conf.get('api', 'application_id')
        req_vars['v'] = '3.0'
        req_vars['format'] = 'JSON'
        sig = str(self.v_id)
        url = 'http://api.vkontakte.ru/api.php?'
        for key in sorted(req_vars.keys()):
            val=req_vars[key]
            try:
                val=val.encode('utf-8')
            except: pass
            sig += '%s=%s' % (key, val)
            if type(val) == unicode:
                val=val.encode('utf-8')
            url += '%s=%s&' % (key, urllib2.quote(str(val)))
        if type(sig)==str:
            sig = sig.decode("utf-8")
        sig += self.api_secret
        #print sig
        m = hashlib.md5()
        m.update(sig.encode("utf-8"))
        sig = m.hexdigest()
        url += 'sid=%s&sig=%s' % (self.api_sid, sig)
        #print url

        f = self.getHttpPage(url)
        f=f.replace('<br>', '\\n')
        f=f.replace('&quot;', '\\"')
        res = demjson.decode(f)
        if 'error' in res:
            err = res['error']
            errCode = err['error_code']
            if errCode==4:
                logging.warn("api error: auth error, method: %s"%method)                
                raise ApiAuthError()
            elif errCode == 7:
                logging.warn("api error: missing permission, method: %s"%method)
                raise ApiPermissionMissing()
            logging.warn("api method failed: %s (%s)"%(method, str(kwargs)))
            raise Exception("api error: "+res['error']['error_msg'])
        if not raw:
            return res['response']
        return res
    def apiCheck(self):
        t=self.apiRequest("isAppUser")
        if int(t)!=1:
                raise AppAuthError('', self.apiLoginUrl())
        t=self.apiRequest('getUserSettings')
        if (int(t)&API_PERMS)!=API_PERMS:
                raise AppPermsError('', self.apiLoginUrl())            
        self.api_active=True
    
    def apiLoginUrl(self):
        return 'http://vkontakte.ru/login.php?app=%s&layout=touch&type=browser&settings=%s'%(
                                                conf.get('api', 'application_id'), API_PERMS)
    
    def isApiActive(self):
        return self.api_active
            
    def apiLogin(self):
        #perms = 2+4+8
        #print self.api_secret
        #login_url = 
        #print login_url
        def parseUrl(url):
            data = re.search("(?P<data>[{].*[}])", url)
            if not data:
                logging.error("location parse error: "+url)
                if 'security' in url:
                    fullUrl='http://vkontakte.ru'+url
                    logging.warn("trying to open "+fullUrl)
                    self.dumpString(self.getHttpPage(fullUrl),fn="security")
                return
            data = (eval(data.group("data"), {}, {}))
            self.api_secret = data['secret']
            self.api_sid = data['sid']

        def getLocation(buf):
            #print repr(buf)
            if 'Location' in buf:
                loc=buf.split()[1]
                parseUrl(urllib.unquote(loc))
                try:
                    self.apiCheck()
                except:
                    pass

        #proxy=None
        lform = self.getHttpPage(self.apiLoginUrl(), hdrFunction=getLocation)
        if self.isApiActive():
            return
        #print lform[:-1000]
        #print 'lform: ', lform
        args = readForms(lform)

            
        #args["email"] = email[:2]
        #args["pass"] = pw

        login_url = 'http://login.vk.com/'
        #pprint(args)
        l1 = self.getHttpPage(login_url,urllib.urlencode(args))
        #print l1
        if ('onCaptcha' in l1):
            data = re.search("\"([0-9]+)\"", l1)
            raise Exception("captcha: sid = %s" % data.group(1))
        # capcha_{key, sid}
        l2_url = 'http://vkontakte.ru/login.php'
        l1_data = readForms(l1)
        
        #for i in [2,4,8]:
        #    l1_data['app_settings_%s'%i]='on'
        print self.getCookies()
        pprint (l1_data)
        
        if not l1_data:
            raise ApiAuthError()

        l2=self.getHttpPage(l2_url, l1_data, hdrFunction=getLocation)

        parseUrl(l2)
    def addApplication(self, perms=[2,4,8]):
        sett_url = 'http://vkontakte.ru/apps.php?act=a_save_response'
        args={'addMember':1}
        for i in perms:
            args['app_settings_%s'%i]=i
        pprint(args)
        self.getHttpPage(sett_url, args)
        print 'result:', self.apiRequest("isAppUser")
            
    def flParse(self,page):
        startString="var friendsData = "
        endString=";\n var diff;"
        varStart=page.find(startString)
        if(varStart==-1):
            raise HTTPError()
        varStart+=len(startString)
        varEnd=page.find(endString, varStart)
        jsonString=page[varStart:varEnd].decode("cp1251")
        fl=demjson.decode(jsonString)
        #print fl['friends'][0]
        ret={}
      
        for item in fl['friends']:
            try:
                first, last=item[1].rsplit(' ', 1)
            except ValueError:
                first=item[1]
                last=''
            ret[item[0]]={"last":last, "first": first, "avatar_url":item[2]}
        return ret
    
    def getOnlineList2(self, v_id=None):
        if not v_id:
            v_id=self.v_id
        fl=self.userapiRequest(act='friends_online',id=self.v_id)
        #print fl
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
            
    def getOnlineList(self, v_id=None):
        try:
            return self.getFriends_api(v_id, online=True)
        except ApiAuthError:
            logging.warning("api auth error[gOL]")
        except ApiPermissionMissing:
            pass
        except:
            logging.exception('')
        try:
            return self.getOnlineList2(v_id)
        except (UserapiSidError,HTTPError):
            raise
        except:
            logging.warning(format_exc())
            #print "getOnlineList: userapi request failed"
            #print_exc()
        page=self.getHttpPage("http://vkontakte.ru/friends.php?filter=online&id=%s"%self.v_id)
        if not page:
            return {}
        return self.flParse(page)

    def dumpString(self,data,fn="",comm='parser error'):
        if (self.dumpPath==None or self.dumpPath==''):
            return
        fname="%s/%s-%s"%(self.dumpPath,fn,int(time.time()))
        with open(fname,"w") as fil:
            if (type(data)==unicode):
                data=data.encode("utf-8")
            fil.write(data)
        logging.warning("%s: page saved to %s"%(comm,fname))

    def getHistory(self,v_id,length=15):
        try:
            return self.getHistory2(v_id,length)
        except:
            logging.exception('')
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
    
    def getHistory2(self,v_id,length=15):
        dat=self.userapiRequest(act='message',id=v_id, to=length)
        ret=[]
        repl=(('<br>','\n'),
          ('&quot;','"'),
          ('&lt;',  '<'),
          ('&gt;',  '>'),
          ('&#39;', '\''),
          ('&amp;', '&'),
          )
        for i in dat['d']:
            if (i[3][0]==self.v_id):
                t=u'out'
            else:
                t=u'in'
            msg=i[2][0]
            for k,v in repl:
                msg=msg.replace(k,v)
            ret.append((t,msg))
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
        try:
            return self.sendMessage(v_id,text,wall=True)
        except Exception,e:
            logging.warning ('userapi request failed: %s'%e)
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
        
    def getVcard_api(self,v_id, show_avatars=0,page=None):
        profileInfo = self.apiRequest('getProfiles', uids=str(v_id), 
                                     fields='photo_medium')[0]
        ret={}
        ret['FN']=profileInfo['first_name']+' '+profileInfo['last_name']
        return ret
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
        #print rc
        profName=rc.find("div", {"id":"profile_name"})
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
        resolve_nick=False
        try:
            self.user().getConfig("resolve_nick")
        except:
            pass
        if (resolve_nick):
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
        #if self.isApiActive():
        return self.getVcard_api(v_id)
        return self.getVcard_new(v_id)
        #except Exception,e:
        #    logging.warning ('getvcard_new failed for id%s'%v_id)
        #    logging.warning(str(e))
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
        if (self.user().getConfig("resolve_nick")):
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
                        with open(fpath,"r") as cfile:
                            photo=cfile.read()
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
                    with open(fpath,'w') as cfile:
                        cfile.write(photo)
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
        
    def setStatus_api(self, text=None, ts=None):
        """Sets status (aka activity) through userapi request"""
        if not text:
            dat=self.userapiRequest(act='clear_activity',ts=ts)
        else:
            dat=self.userapiRequest(act='set_activity',text=text.encode("utf-8"),ts=ts)
        try:
            return dat['ok']
        except (KeyError,TypeError):
            return 0

    def setStatus(self,text,ts=None):
        """ Sets status (aka activity) on vk.com site"""
        #if (ts):
        res=self.setStatus_api(text,ts)
        if res:
            return res
        if (text):
            r=self.userapiRequest(act='set_activity', text=text)
        else:
            r=self.userapiRequest(act='clear_activity')
        if (r['ok']==1):
            return 1
        else:
            return 0
    def getInboxMessages(self,ts=None, num=10, v_id=None):
        ret={}
        if (v_id):
            rd={'act':'message', 'id':v_id, 'to':num}
            #d=self.userapiRequest(act='message', id=v_id, to=num)
        else:
            rd={'act':'inbox'}
            if (ts):
                rd['ts']=ts
            else:
                rd['to']=num
        d=self.userapiRequest(**rd)
        ret['ts']=d['h']
        ret['messages']=[]
        for i in d['d']:
            m={}
            m['id']=int(i[0])
            m['text']=i[2][0].replace('<br>','\n')
            m['from']=i[3][0]
            m['to']=i[4][0]
            m['time']=int(i[1])
            ret['messages'].append(m)
        return ret
    
    def sendMessage_api(self, uid, body, title=''):
        r=self.apiRequest("messages.send", uid=uid, message=body, title=title)
        logging.warn("message sent, mid = "+str(r))
        return r
    
    def sendMessage(self,to_id,body,title='', wall=False,forceMsgCheck=False):
        if (wall):
            a='wall'
            d=self.userapiRequest(act=a, to=0, id=to_id)
            ts=d['h']
        else:
            a='message'
            try:
                return self.sendMessage_api(to_id, body, title )
            except:
                logging.exception("")
        try:
            d=self.userapiRequest(act=a, to=0 )
            ts=d['h']
            #print d
            res=self.userapiRequest(act='add_%s'%a, id=to_id, message=body.encode('utf-8'), ts=ts)
        except HTTPError:
            return 1
        except UserapiJsonError:
            if not wall:
                h=self.getHistory(to_id,3)
                if (('out',body) in h):
                    logging.warning('msgCheck: success!')
                    return 0
                else:
                    logging.warning('GREPME msg doesn\'t match\n%s\n%s'%(repr(body),repr(h[0][1])))
                    return -1
        r=res.get('ok',0)
        if (r==1):
            #logging.warning('outgoing message (%s) sent'%a)
            return 0
        if r==-2:
            raise captchaError()
        if (r==-3):
            raise PrivacyError()
        if r==-1:
            raise UserapiSidError()
        logging.warning('unknown userapi error code: %s'%r)
        return -1
    def convertFriendList(self, data):
        ret={}
        for i in data:
            ret[i['uid']]={'first':i['first_name'], 
                            'last':i['last_name'],
                            'avatar_url':i['photo_medium'].replace('\\/','/')}
        return ret
    def getFriends_api(self, v_id=0, online=False):
        kw={}
        if v_id:
            kw={'uid': v_id}
        fields='first_name,last_name,photo_medium'
        data=self.apiRequest("friends.get", fields=fields, **kw)
        if online:
            filt=lambda i: i['online']==1
            data = filter(filt, data)
        return self.convertFriendList(data)
   
    def getFriendList(self, v_id=0):
        return self.getFriends_api(v_id)
        if (v_id==0):
            v_id=self.v_id
        return self.flParse(self.getHttpPage("http://vkontakte.ru/friends.php?filter=all&id=%s"%v_id))
        fl=self.userapiRequest(act='friends',id=v_id)
        ret={}
        for i in fl:
            fn=i[1].split()
            try:
                ret[i[0]]={'last':fn[1],'first':fn[0]}
            except IndexError:
                ret[i[0]]={'first':fn[0]}
        return ret
    def getFriendList_legacy(self):
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
        
        print dat
        if (dat["isf"]):
            return 0
        if (dat["isi"]):
            return 2
        return 1
    def addDeleteFriend(self,v_id,isAdd):
        if (isAdd):
            act='add_friend'
        else:
            act='del_friend'
        res=self.userapiRequest(act=act,id=v_id)
        return res['ok']
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
                        print tds[1]
                        return
    def getStatusList_legacy(self):
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
    def getStatusList(self):
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
                    pinfo["dlink"]="http://cs%s.vk.com/u%s/audio/%s.mp3"%(ld[1],ld[2],ld[3])
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
            #if (not self.resolve_links):
                #pinfo['dlink']=u'прямые ссылки отключены админом'
                    
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
        dat=self.userapiRequest(act='wall',id=self.v_id,ts=ts,to=300)
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
    def enterUserapiCaptcha(self, ck):
        self.userapiRequest(fccode=ck,**self.captchaRequestData)
    def userapiEnterCaptcha (self,fccode):
        logging.warning('trying to enter captcha code')
        rd=self.captchaRequestData
        rd['fccode']=fccode
        return self.userapiRequest(**rd)
    def userapiRequest(self,url='http://userapi.com/data?',**kw):
        #import simplejson as json
        nkw=kw
        nkw['sid']=self.sid
        nkw['from']='0'
        if (not nkw.has_key('to')):
            nkw['to']='1000'
        #if (nkw.has_key('v_id')):
            #nkw['id']=nkv['v_id']
            #del nkv['v_id']
        d=''
        for k in nkw:
            try:
                v=str(nkw[k])
            except UnicodeEncodeError:
                v=nkw[k].encode('utf-8')
            d="%s%s=%s&"%(d,k,urllib.quote(v))
        #url+=d
        dat=urlencode(nkw)
        try:
            page=self.getHttpPage(url,dat)
        except HTTPError, e:
            raise HTTPError (e.err,'userapi: %s'%str(kw))
        #print page
        #if (page=='{"ok": -2}'):
            #cs=self.genCaptchaSid()
            #self.captchaRequestData=nkw
            #self.captchaRequestData['fcsid']=cs
            #logging.warning('got captcha')
            #raise UserapiCaptchaError(nkw,cs)
        try:
            page=page.decode('utf-8')
        except:
            try:
                page=page.decode('cp1251')
                #logging.warning('legacy charset (act=%s).'%kw.get('act'))
            except:
                logging.warning("strange userapi charset")
        if (len(page)==0):
            if (kw.get('act')!='add_message'):
                # error silently handled by sendMessage()
                logging.error("empty response (act=%s)."%kw.get('act'))
            raise UserapiJsonError
        try:
            page=page.replace('<br>', '\\n')
            page=page.replace('&quot;', '\\"')
            ret=json.loads(page)
            #FIXME
        except Exception,e:
            logging.warning ('json failed: %s'%str(e))
            try:
                ret= demjson.decode(page,strict=False)
            except Exception,e:
                logging.warning("json error (%s). trying to remofe 'fr.' blocks..."%e)
                sr=re.search(',"fr":{.*?},"fro":{.*?},"frm":{.*?}',page)
                if (sr):
                    page=page[:sr.start()]+page[sr.end():]
                try:
                    ret= demjson.decode(page,strict=False)
                except Exception,e:
                    logging.error("userapi failed. act='%s'\t'%s'\n%s"%(kw.get('act'),repr(page),str(e)))
                    raise UserapiJsonError
        try:
            if (ret['ok']==-2):
                #raise captchaError
                cs=self.genCaptchaSid()
                self.captchaRequestData=nkw
                self.captchaRequestData['fcsid']=cs
                logging.warning('got captcha')
                raise UserapiCaptchaError(nkw,cs)
            elif (ret['ok']==-1):
                raise UserapiSidError()
                #logging.error('userapiRequest: GREPME userapi session error (%s)'%self.bjid)
        except (KeyError,TypeError):
            pass
        return ret
    def desktopApiRequest(self):
#api_id	8
#fields	photo_rec,contacts
#format	JSON
#method	getProfiles
#sid	3e7c7f9f464a6e125a3c561c6777005d39f4af8332fecb02e3c4c914d6
#sig	28d22a5043b919f1b6150752dd7b6972
#uids	10189909,14070,193251,2579063,2626314,26884806,39755,460082,4770607,481836,51020738,5506400,6612601,83061,939351
#v	3
        reqParams={}
        reqParams["api_id"]=8
        reqParams["fields"]="photo_rec,contacts"
        reqParams["method"]="getProfiles"
        reqParams["sid"]="3e7c7f9f464a6e125a3c561c6777005d39f4af8332fecb02e3c4c914d6"
        reqParams["uids"]="10189909,14070,193251,2579063,2626314,26884806,39755,460082,4770607,481836,51020738,5506400,6612601,83061,939351"
        reqParams["v"]=3
        hashStr="".join(("%s=%s"%(i,reqParams[i]) for i in sorted(reqParams.keys()) if i!="sid"))
        import md5
        sig=md5.new(hashStr).hexdigest()
        print hashStr
        print sig
if __name__=='__main__':
    execfile ('test.py')
