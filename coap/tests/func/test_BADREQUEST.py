import logging
import testUtils as utils

import time
import threading

import os

import pytest

import binascii

from conftest import IPADDRESS1, \
                     RESOURCE, \
                     DUMMYVAL, \
                     OSCOREDUMMYMASTERSECRETCONTEXT
from coap     import coapDefines as d, \
                     coapException as e, \
                     coapOption as o, \
                     coapObjectSecurity as oscore

#============================ logging =========================================

log = logging.getLogger(utils.getMyLoggerName())
log.addHandler(utils.NullHandler())

#============================ logging =========================================

#============================ tests ===========================================

def test_BADREQUEST(logFixture, snoopyDispatcher, twoEndPoints, confirmableFixture):
    (coap1, coap2, securityEnabled) = twoEndPoints

    options = []
    if securityEnabled:
        # have coap2 do a get with the right IDs but wrong master secret
        clientContext = oscore.SecurityContext(OSCOREDUMMYMASTERSECRETCONTEXT)

        clientOptions = [o.ObjectSecurity(context=clientContext)]

        with pytest.raises(e.coapRcBadRequest):
            reply = coap2.GET(
                uri='coap://[{0}]:{1}/{2}/'.format(IPADDRESS1, d.DEFAULT_UDP_PORT, RESOURCE),
                confirmable=confirmableFixture,
                options=clientOptions
            )
    else:
        pass