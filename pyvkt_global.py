# -*- coding: utf-8 -*-
def bareJid(jid):
    n=jid.find("/")
    if (n==-1):
        return jid
    return jid[:n]