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
