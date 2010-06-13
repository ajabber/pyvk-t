# -*- coding: utf-8 -*-
import ConfigParser,logging
#fields = {section: {option: (type, default, required), ...}, ...}
fields={
    "features":
        {
            'sync_status':(bool,False,False),
            'avatars':(bool,False,False),
            'status':(unicode,'',False)
        },
    "storage":
        {
            'datadir':(unicode,None,False),
            'cookies':(unicode,None,False),
            'cache':(unicode,None,False)
        },
    "general":
        {
            'service_name':(unicode,u'Вконтакте.ру транспорт',False),
            'jid':(unicode,None,True),
            'server':(unicode,None,True),
            'port':(int,None,True),
            'secret':(unicode,None,True),
            'admin':(unicode,None,False),
            'control_socket':(unicode,None,False)
        },
    "debug":
        {
            'dump_path':(unicode,None,False)
        },
    "workarounds":
        {
            'fix_namespaces':(bool,False,False)
        }
    }
conf={}
cp=None
def read(filename):
    cp=ConfigParser.ConfigParser()
    cp.read(filename)
    for s in fields.keys():
        conf[s]={}
        for o in fields[s].keys():
            t,d,r=fields[s][o]
            try:
                if (t==bool):
                    conf[s][o]=cp.getboolean(s,o)
                elif (t==int):
                    conf[s][o]=cp.getint(s,o)
                elif (t==unicode):
                    conf[s][o]=cp.get(s,o).decode('utf-8')
            except (ConfigParser.NoSectionError,ConfigParser.NoOptionError):
                if r:
                    logging.critical("can't get required field '%s/%s'. Check your config file ('%s')."%(s,o,filename))
                    raise Exception
                conf[s][o]=d
    #print conf
def get(sect,opt=None):
    if (not opt):
        sect,opt=sect.split('/')
    return conf[sect][opt]

    
__all__=['read','conf']
    
