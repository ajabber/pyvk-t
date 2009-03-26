# -*- coding: utf-8 -*-
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
userConfigFields={
    "sync_status":{"type":"boolean", "default":False, "desc":u"Синхронизация статуса"}
    ,"vcard_avatar":{"type":"boolean", "default":False, "desc":u"Аватары в vCard"}
    ,"resolve_nick":{"type":"boolean", "default":False, "desc":u"Пытаться выделить ник"}
    ,"feed_notify":{"type":"boolean", "default":False, "desc":u"Уведомлять о новых встречах и группах сообщением"}
#TODO    ,"default_title":{"type":unicode, "default":"sent by xmpp transport", "desc":"Тема сообщения по умолчанию"}
}
feedInfo = {
    "groups":{"message":u"групп","url":u"http://vkontakte.ru/club%s"}
    ,"events":{"message":u"встреч","url":u"http://vkontakte.ru/event%s"}
    ,"friends":{"message":u"друзей","url":u"http://vkontakte.ru/id%s"}
    ,"photos":{"message":u"фотографий","url":u"http://vkontakte.ru/photos.php?act=show&id=%s&added=1"}
    ,"videos":{"message":u"видеозаписей","url":u"http://vkontakte.ru/video%s?added=1"}
    ,"gifts":{"message":u"подарков","url":u""}
    ,"notes":{"message":u"комментаириев к заметкам","url":u""}
}
