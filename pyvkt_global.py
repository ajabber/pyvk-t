# -*- coding: utf-8 -*-
import re, htmlentitydefs

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
    "sync_status":{"type":"boolean", "default":False, "desc":u"Синхронизация статуса"}
    ,"vcard_avatar":{"type":"boolean", "default":False, "desc":u"Аватары в vCard"}
    ,"resolve_nick":{"type":"boolean", "default":False, "desc":u"Пытаться выделить ник"}
    ,"keep_online":{"type":"boolean", "default":False, "desc":u'Поддерживать статус "в сети" (экспериментально)'}
    ,"show_onlines":{"type":"boolean", "default":True, "desc":u"Показывать кто в сети ('online' на сайте)"}
    ,"jid_in_subject":{"type":"boolean","default":True, "desc":u"JID в теме сообещний, если не указана"}
    ,"feed_notify":{"type":"boolean", "default":False, "desc":u"Уведомлять о новых встречах и группах сообщением"}
    ,"start_feed_notify":{"type":"boolean", "default":False, "desc":u"Уведомлять о новых встречах и группах при входе"}
    ,"save_cookies":{"type":"boolean", "default":True, "desc":u"Сохранять cookies на серверею Поможет уберечься от капчи"}
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
