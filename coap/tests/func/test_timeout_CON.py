import logging
import testUtils as utils

import time
import threading

import pytest

from conftest import IPADDRESS1, \
                     RESOURCE, \
                     DUMMYVAL, \
                     OSCORECLIENTCONTEXT
from coap     import coapDefines as d, \
                     coapException as e, \
                     coapOption as o, \
                     coapObjectSecurity as oscore

#============================ logging =========================================

log = logging.getLogger(utils.getMyLoggerName())
log.addHandler(utils.NullHandler())

#============================ define ==========================================

IPADDRESS_INVALID = 'bbbb::1'
    
#============================ tests ===========================================

def test_GET(logFixture,snoopyDispatcher,twoEndPoints):
    
    (coap1,coap2,securityEnabled) = twoEndPoints
    
    # adjust timeouts so test is faster
    coap2.ackTimeout    = 2
    coap2.respTimeout   = 2

    options = []
    if securityEnabled:
        context = oscore.SecurityContext(OSCORECLIENTCONTEXT)

        options = [o.ObjectSecurity(context=context)]
    
    # have coap2 do a get
    with pytest.raises(e.coapTimeout):
        reply = coap2.GET(
            uri         = 'coap://[{0}]:{1}/{2}/'.format(IPADDRESS_INVALID,d.DEFAULT_UDP_PORT,RESOURCE),
            confirmable = True,
            options=options,
        )
    
