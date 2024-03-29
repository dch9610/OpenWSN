import logging
import testUtils as utils

import time
import threading

from conftest import IPADDRESS1, \
                     RESOURCE, \
                     DUMMYVAL,\
                     OSCORECLIENTCONTEXT
from coap     import coapDefines as d, \
                     coapOption as o, \
                     coapObjectSecurity as oscore

#============================ logging ===============================

log = logging.getLogger(utils.getMyLoggerName())
log.addHandler(utils.NullHandler())
    
#============================ tests ===========================================

def test_GET(logFixture,snoopyDispatcher,twoEndPoints):
    
    (coap1,coap2,securityEnabled) = twoEndPoints

    options = []
    if securityEnabled:
        context = oscore.SecurityContext(OSCORECLIENTCONTEXT)

        options = [o.ObjectSecurity(context=context)]
    
    # have coap2 do a get
    for _ in range(20):
        reply = coap2.GET(
            uri         = 'coap://[{0}]:{1}/{2}/'.format(IPADDRESS1,d.DEFAULT_UDP_PORT,RESOURCE),
            confirmable = True,
            options=options
        )
        assert reply==DUMMYVAL

