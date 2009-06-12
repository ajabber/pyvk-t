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
import re, htmlentitydefs,ConfigParser
class noVclientError(AttributeError):
    def __init__(self,bjid=""):
        AttributeError(self,"user instance without vclient")
        self.bjid=bjid
        pass
    def __str__(self):
        return 'user without vclient (%s)'%bjid
class config:
    fields={'genegal':{1:1}}
    def __init__(cfile='pyvk-t_new.conf'):
        print "reading config..."
        config = ConfigParser.ConfigParser()
        #for i in 
    def __getitem__(self,key):
        pass
        

        

        

def bareJid(jid):
    n=jid.find("/")
    if (n==-1):
        return jid.lower()
    return jid[:n].lower()

def jidToId(jid):
    dogpos=jid.find("@")
    if (dogpos==-1):
        return 0
    try:
        v_id=int(jid[:dogpos])
        return v_id
    except:
        return -1


##
# Removes HTML or XML character references and entities from a text string.
#
# @param text The HTML (or XML) source text.
# @return The plain text, as a Unicode string, if necessary.
# from Fredrik Lundh
#   http://effbot.org/zone/re-sub.htm#unescape-html
# 
def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

userConfigFields={
    "sync_status":{"type":"boolean", "default":False, "desc":u"Синхронизировать статус с сайтом"}
    ,"vcard_avatar":{"type":"boolean", "default":False, "desc":u"Аватары в vCard"}
    ,"resolve_nick":{"type":"boolean", "default":False, "desc":u"Пытаться выделить ник"}
    ,"keep_online":{"type":"boolean", "default":False, "desc":u'Поддерживать статус "в сети" (экспериментально)'}
    ,"show_onlines":{"type":"boolean", "default":True, "desc":u"Показывать, кто в сети ('online' на сайте)"}
    ,"jid_in_subject":{"type":"boolean","default":True, "desc":u"JID в теме сообщений, если не указана"}
    ,"feed_notify":{"type":"boolean", "default":False, "desc":u"Уведомлять о новых встречах и группах сообщением"}
    ,"start_feed_notify":{"type":"boolean", "default":False, "desc":u"Уведомлять о новых встречах и группах при входе"}
    ,"save_cookies":{"type":"boolean", "default":True, "desc":u"Сохранять cookies на сервере. Поможет уберечься от капчи"}
    ,"signature":{"type":"text-single", "default":"", "desc":u"Подпись в сообщении"}
#TODO    ,"default_title":{"type":unicode, "default":"sent by xmpp transport", "desc":"Тема сообщения по умолчанию"}
}
feedInfo = {
    "groups":{"message":u"групп","url":u"http://vkontakte.ru/club%s"}
    ,"events":{"message":u"встреч","url":u"http://vkontakte.ru/event%s"}
    ,"friends":{"message":u"друзей","url":u"http://vkontakte.ru/id%s"}
    ,"photos":{"message":u"фотографий","url":u"http://vkontakte.ru/photos.php?act=show&id=%s&added=1"}
    ,"videos":{"message":u"видеозаписей","url":u"http://vkontakte.ru/video%s?added=1"}
    ,"gifts":{"message":u"подарков","url":u""}
    ,"opinions":{"message":u"мнений","url":u""}
    ,"offers":{"message":u"отзывов на предложения","url":u""}
    ,"questions":{"message":u"ответов на вопросы","url":u""}
    ,"notes":{"message":u"комментаириев к заметкам","url":u""}
}
