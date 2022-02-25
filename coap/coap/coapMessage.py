import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('coapMessage')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

from . import coapOption         as o
from . import coapUtils          as u
from . import coapException      as e
from . import coapDefines        as d
from . import coapObjectSecurity as oscore

def sortOptions(options):
    # TODO implement sorting when more options are implemented
    return options

'''
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |Ver| T |  TKL  |      Code     |          Message ID           |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |   Token (if any, TKL bytes) ...
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |   Options (if any) ...
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |1 1 1 1 1 1 1 1|    Payload (if any) ...
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
'''

def buildMessage(msgtype,token,code,messageId,options=[],payload=[],securityContext=None,partialIV=None):
    assert msgtype in d.TYPE_ALL
    assert code in d.METHOD_ALL+d.COAP_RC_ALL
    
    message   = []

    TKL = 0
    if token is not None:
        # determine token length
        for tokenLen in range(1,8+1):
            if token < (1<<(8*tokenLen)):
                TKL = tokenLen
                break
        if not TKL:
            raise ValueError('token {0} too long'.format(token))

    if securityContext:
        # invoke oscore to protect the message
        (protectedCode, outerOptions, newPayload) = oscore.protectMessage(context=securityContext,
                                                                          version = d.COAP_VERSION,
                                                                          code = code,
                                                                          options = options,
                                                                          payload = payload,
                                                                          partialIV=partialIV)
    else:
        (protectedCode, outerOptions, newPayload) = (code, options, payload)

    # header
    message += [d.COAP_VERSION<<6 | msgtype<<4 | TKL]
    message += [protectedCode]
    message += u.int2buf(messageId,2)
    message += u.int2buf(token,TKL)

    # options
    options  = sortOptions(options)

    # add encoded options
    message += encodeOptions(outerOptions)

    # add payload
    message += encodePayload(newPayload)
    
    return bytes(message)

def parseMessage(message):
    
    returnVal = {}
    
    # header
    if len(message)<4:
        raise e.messageFormatError('message too short, {0} bytes: no space for header'.format(len(message)))
    returnVal['version']     = (message[0]>>6)&0x03
    if returnVal['version']!=d.COAP_VERSION:
        raise e.messageFormatError('invalid CoAP version {0}'.format(returnVal['version']))
    returnVal['type']        = (message[0]>>4)&0x03
    if returnVal['type'] not in d.TYPE_ALL:
        raise e.messageFormatError('invalid message type {0}'.format(returnVal['type']))
    TKL  = message[0]&0x0f
    if TKL>8:
        raise e.messageFormatError('TKL too large {0}'.format(TKL))
    returnVal['code']        = message[1]
    returnVal['messageId']   = u.buf2int(message[2:4])
    message = message[4:]
    
    # token
    if len(message)<TKL:
        raise e.messageFormatError('message too short, {0} bytes: no space for token'.format(len(message)))
    if TKL:
        returnVal['token']       = u.buf2int(message[:TKL])
        message = message[TKL:]
    else:
        returnVal['token'] = None
    
    # outer options and payload/ciphertext
    (returnVal['options'], payload) = decodeOptionsAndPayload(message)

    # if object security option is present decode the value in order to be able to decrypt the message
    objectSecurity = oscore.objectSecurityOptionLookUp(returnVal['options'])
    if objectSecurity:
        oscoreDict = oscore.parseObjectSecurity(objectSecurity.getPayloadBytes(), payload)
        objectSecurity.setKid(oscoreDict['kid'])
        objectSecurity.setKidContext(oscoreDict['kidContext'])
        returnVal.update(oscoreDict)
    else:
        returnVal['payload'] = payload

    
    log.debug('parsed message: {0}'.format(returnVal))
    
    return returnVal

def encodeOptions(options, lastOptionNum=0):
    encoded = []
    for option in options:
        assert option.optionNumber>=lastOptionNum
        encoded += option.toBytes(lastOptionNum)
        lastOptionNum = option.optionNumber
    return encoded

def decodeOptionsAndPayload(rawbytes, currentOptionNumber = 0):
    options = []
    while True:
        (option,rawbytes)     = o.parseOption(rawbytes, currentOptionNumber)
        if not option:
            break
        options += [option]
        currentOptionNumber  = option.optionNumber

    return (options, rawbytes)

def encodePayload(payload):
    encoded = []
    if payload:
        encoded += [d.COAP_PAYLOAD_MARKER]
        encoded += payload
    return encoded