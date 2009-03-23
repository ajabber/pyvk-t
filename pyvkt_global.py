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
#TODO    ,"default_title":{"type":unicode, "default":"sent by xmpp transport", "desc":"Тема сообщения по умолчанию"}
}