
from twisted.application import service

from twisted.words.protocols.jabber import component
import ConfigParser,os
import pyvkt_new
from sys import argv

config = ConfigParser.ConfigParser()
confName="pyvk-t_new.cfg"
if(os.environ.has_key("PYVKT_CONFIG")):
    confName=os.environ["PYVKT_CONFIG"]
config.read(confName)

application = service.Application("pyvk-t")

# set up Jabber Component
srvAddr="tcp:%s:%s"%(config.get("general","server"),config.getint("general","port"))
sm = component.buildServiceManager(
    config.get("general","transport_jid"), 
    config.get("general","secret"),
    (srvAddr)
)


# Turn on verbose mode
logger = pyvkt_new.LogService()
logger.setServiceParent(sm)

# set up our example Service
s = pyvkt_new.pyvk_t()
s.logger = logger
s.setServiceParent(sm)

sm.setServiceParent(application)

