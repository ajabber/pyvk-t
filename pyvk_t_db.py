# -*- coding: utf-8 -*-
class pyvk_t_db:
    ulist={}
    def __init__(self):
        uf=open("users.lst","r")
        try:
            self.ulist=eval(uf.read())
        except:
            self.ulist={}
        print "db opened"
    def users(self):
        return self.ulist
    def addUser(self,jid,user,pw):
        self.ulist[jid]={"email":user,"password":pw}
    def modUser(self,jid,data):
        self.ulist[jid]=data
    def delUser(self,jid):
        if (self.ulist.has_key(jid)):
            del ulist[jid]
    def userData(self,jid):
        if (self.ulist.has_key(jid)):
            return self.ulist[jid]
        return None
    def sync(self):
        uf=open("users.lst","w")
        uf.write(repr(self.ulist)+"\n")
        uf.close()
    def __del__(self):
        self.sync()

#db=pyvk_t_db()
#print db.userData("test")
#db.addUser("eqx@eqx.su","login","pass")


