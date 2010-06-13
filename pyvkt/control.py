#! /usr/bin/python
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
import socket as s
import threading,os
import logging as l
import pyvkt.config as conf
try:
    import hook
except:
    pass
class ControlSocketListener (threading.Thread):
    alive=True
    def __init__(self,trans):
        threading.Thread.__init__(self,target=self.loop,name="Control Socket Listener")
        self.daemon=True
        self.trans=trans
        self.sock=s.socket(s.AF_UNIX, s.SOCK_STREAM)
        sn=conf.get("general","control_socket")
        l.warning('socket name: %s'%sn)
        try:
            os.unlink(sn)
        except:
            pass
        self.sock.bind(sn)
        self.sock.listen(1)
    def loop(self):
        l.warning ('starting CSL loop')
        while self.alive:
            c,a=self.sock.accept()
            try:
                cmd=c.recv(1024)
                l.warning('CSL: got %s'%cmd)
                resp='error'
                if (cmd[0]=='#'):
                    if (cmd[-1]=='\n'):
                        cmd=cmd[:-1]
                    resp=self.trans.adminCmd(cmd[1:])
                    if (type(resp)==unicode):
                        resp=resp.encode('utf-8')
                    resp=str(resp)
                try:
                    resp=hook.socketCmd(self.trans,cmd)
                except:
                    pass
                #l.warning ('response: %s'%repr(resp))
                c.send(resp)
            except:
                l.exception('')
            try:
                c.close()
            except:
                l.exception('')


