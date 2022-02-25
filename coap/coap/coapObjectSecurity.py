import hashlib
import logging

import cbor
import hkdf
import json
import sys
import binascii
import threading
from Crypto.Cipher import AES

from . import coapDefines as d
from . import coapException as e
# from . import coapMessage as m
from . import coapOption as o
from . import coapUtils as u


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


log = logging.getLogger('coapObjectSecurity')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())


def protectMessage(context, version, code, options=[], payload=[], partialIV=None):
    """
    A function which protects the outgoing CoAP message using OSCORE according to rfc8613
    :param context security context to use to protect the outgoing message.
    :param version CoAP version field of the outgoing message.
    :param code CoAP code field of the outgoing message.
    :param options A list of options to be included in the outgoing CoAP message.
    :param payload Payload of the outgoing CoAP message.
    :param partialIV Partial IV either to be used to protect the request or the one received as part of the
    corresponding request to protect the response. Expected string of length given by the context algorithm.

    :return A tuple with the following elements:
        - element 0 is the list of outer (integrity-protected and unprotected) CoAP options.
        - element 1 is the protected payload.
    """

    # split the options to class E (encrypted and integrity protected), I (integrity protected) and U (unprotected)
    (optionsClassE, optionsClassI, optionsClassU) = _splitOptions(options)

    objectSecurityOption = objectSecurityOptionLookUp(options)

    # construct plaintext
    plaintext = []
    plaintext += [code]
    plaintext += m.encodeOptions(optionsClassE)
    plaintext += m.encodePayload(payload)
    plaintext = bytes(plaintext)  # convert to bytes

    # construct aad

    requestSeq = partialIV.lstrip(b'\x00')

    requestKid = context.senderID if _isRequest(code) else context.recipientID

    # construct nonce
    nonce = _constructAeadNonce(context.aeadAlgorithm, partialIV, requestKid, context.commonIV)

    aad = _constructAAD(version,
                        context.aeadAlgorithm.value,
                        requestKid,
                        requestSeq,
                        bytes(m.encodeOptions(optionsClassI)),
                        )

    ciphertext = context.aeadAlgorithm.authenticateAndEncrypt(
        aad=aad,
        plaintext=plaintext,
        key=context.senderKey,
        nonce=nonce)

    if not _isRequest(code):  # response
        # do not encode sequence number, kid  or kid context in the OSCORE option value
        objectSecurityOption.setValue(_encodeCompressedCOSE(None, None, None))
        # code is always 2.04 Changed
        protectedCode = d.COAP_RC_2_04_CHANGED
    else: # request
        # encode sequence number, kid and kid context
        objectSecurityOption.setValue(_encodeCompressedCOSE(requestSeq, requestKid, context.idContext))
        # code is always POST
        protectedCode = d.METHOD_POST

    return (protectedCode, optionsClassI + optionsClassU, ciphertext)

def unprotectMessage(context, version, code, options=[], ciphertext=[], partialIV=None):
    """
    A function which verifies and decrypts the incoming CoAP message using OSCORE according to
    rfc8613.

    :param context security context to use to verify+decrypt the outgoing message.
    :param version CoAP version field of the incoming message.
    :param code CoAP code field of the incoming message.
    :param options A list of 'outer' options that are not encrypted.
    :param ciphertext Ciphertext of the incoming CoAP message.
    :param partialIV In case of request, partialIV corresponds to the one parsed from the message. In case
     of response, it corresponds to the appropriate partialIV used in request. Expected string of length given
     by the context algorithm.

    :return A tuple with the following elements:
        - element 0 is the list of inner (encrypted) CoAP options.
        - element 1 is the decrypted payload.
    """
    assert objectSecurityOptionLookUp(options)

    (optionsClassE, optionsClassI, optionsClassU) = _splitOptions(options)

    if optionsClassE:
        raise e.messageFormatError('invalid oscore message. E-class option present in the outer message')

    if _isRequest(code):
        requestKid = context.recipientID
        if not context.replayWindowLookup(u.buf2int(partialIV)):
            raise e.oscoreError('Replay protection failed')
    else:
        requestKid = context.senderID

    requestSeq = partialIV.lstrip(b'\x00')

    aad = _constructAAD(version,
                        context.aeadAlgorithm.value,
                        requestKid,
                        requestSeq,
                        bytes(m.encodeOptions(optionsClassI)),)

    nonce = _constructAeadNonce(context.aeadAlgorithm, partialIV, requestKid, context.commonIV)

    try:
        plaintext = context.aeadAlgorithm.authenticateAndDecrypt(
            aad=aad,
            ciphertext=ciphertext,
            key=context.recipientKey,
            nonce=nonce)

        decryptedCode = plaintext[0]
        plaintext = plaintext[1:]
    except e.oscoreError:
        raise

    if _isRequest(code):
        context.replayWindowUpdate(u.buf2int(partialIV))

    (innerOptions, payload) = m.decodeOptionsAndPayload(plaintext)
    # returns a tuple (decryptedCode, innerOptions, payload)
    return (decryptedCode, innerOptions, payload)

def parseObjectSecurity(optionValue, payload):

    returnVal = {}

    if len(optionValue) == 0:
        optionValue = [0]

    # decode first byte
    n = (optionValue[0] >> 0) & 0x07
    k = (optionValue[0] >> 3) & 0x01
    h = (optionValue[0] >> 4) & 0x01
    reserved = (optionValue[0] >> 5) & 0x07

    if reserved:
        raise e.messageFormatError('invalid oscore message. reserved bits set.')

    optionValue = optionValue[1:]

    returnVal['partialIV'] = []
    if n:
        returnVal['partialIV'] = optionValue[:n]
        optionValue = optionValue[n:]

    returnVal['kidContext'] = None
    if h:
        kidContextLen = optionValue[0]
        optionValue = optionValue[1:]
        returnVal['kidContext'] = optionValue[:kidContextLen]
        optionValue = optionValue[kidContextLen:]

    returnVal['kid'] = []
    if k:
        returnVal['kid'] = optionValue

    returnVal['ciphertext'] = payload

    return returnVal


def getRequestSecurityParams(objectSecurityOption):
    if objectSecurityOption:
        context = objectSecurityOption.context
        newSequenceNumber = objectSecurityOption.context.getSequenceNumber()
        # convert sequence number to string that is the length of the IV
        newSequenceNumber = bytes(u.int2buf(newSequenceNumber, context.aeadAlgorithm.ivLength))
        return (context, newSequenceNumber)
    else:
        return (None, None)


def objectSecurityOptionLookUp(options):
    for option in options:
        if isinstance(option, o.ObjectSecurity):
            return option
    return None


'''
          0 1 2 3 4 5 6 7 <------------- n bytes -------------->
         +-+-+-+-+-+-+-+-+--------------------------------------
         |0 0 0|h|k|  n  |       Partial IV (if any) ...
         +-+-+-+-+-+-+-+-+--------------------------------------

          <- 1 byte -> <----- s bytes ------>
         +------------+----------------------+------------------+
         | s (if any) | kid context (if any) | kid (if any) ... |
         +------------+----------------------+------------------+


'''
def _encodeCompressedCOSE(partialIV, kid, kidContext):
    buffer = []

    h = 1 if kidContext is not None else 0

    kidFlag = 1 if kid is not None else 0

    partialIVLen = 0 if partialIV is None else len(partialIV)

    buffer += [h << 4 | kidFlag << 3 | partialIVLen]  # flag byte

    if partialIVLen:
        buffer += partialIV
    if h:
        buffer += [len(kidContext)]
        buffer += kidContext
    if kidFlag:
        buffer += kid

    if buffer == [0]:
        return []
    return buffer

'''
              <- nonce length minus 6 B -> <-- 5 bytes -->
         +---+-------------------+--------+---------+-----+
         | S |      padding      | ID_PIV | padding | PIV |----+
         +---+-------------------+--------+---------+-----+    |
                                                               |
          <---------------- nonce length ---------------->     |
         +------------------------------------------------+    |
         |                   Common IV                    |->(XOR)
         +------------------------------------------------+    |
                                                               |
          <---------------- nonce length ---------------->     |
         +------------------------------------------------+    |
         |                     Nonce                      |<---+
         +------------------------------------------------+
'''
def _constructAeadNonce(aeadAlgorithm, piv, idPiv, commonIV):

    nonceLen = aeadAlgorithm.ivLength

    pivBuf = piv.lstrip(b'\x00')

    pivPadded = b'\x00' * (5 - len(pivBuf)) + pivBuf
    idPivPadded = b'\x00' * (nonceLen - 6 - len(idPiv)) + idPiv

    buf = bytes([len(idPiv)]) + idPivPadded + pivPadded

    assert len(buf) == nonceLen

    ret = u.xorBytes(commonIV, buf)

    return ret

def _constructAAD(version, aeadAlgorithm, requestKid, requestSeq, optionsSerialized):
    externalAad = cbor.dumps([
        version,
        [aeadAlgorithm],
        requestKid,
        requestSeq,
        optionsSerialized
    ])

    # from https://tools.ietf.org/html/draft-ietf-cose-msg-24#section-5.3
    encStructure = [
        str('Encrypt0'),
        bytes(),  # an empty byte string
        externalAad
    ]

    return cbor.dumps(encStructure)


def _splitOptions(options):
    classE = []
    classI = []
    classU = []

    for option in options:
        if option.oscoreClass == d.OSCORE_CLASS_E:
            classE += [option]
        if option.oscoreClass == d.OSCORE_CLASS_I:
            classI += [option]
        if option.oscoreClass == d.OSCORE_CLASS_U:
            classU += [option]
    return (classE, classI, classU)


def _isRequest(code):
    if code in d.METHOD_ALL:  # request
        return True
    elif code in d.COAP_RC_ALL:
        return False
    else:
        raise NotImplementedError()

class CCMAlgorithm(object):
    @property
    def value(self):
        raise NotImplementedError

    @property
    def keyLength(self):
        raise NotImplementedError

    @property
    def ivLength(self):
        raise NotImplementedError

    @property
    def tagLength(self):
        raise NotImplementedError

    @property
    def maxSequenceNumber(self):
        raise NotImplementedError

    @property
    def maxIdLen(self):
        raise NotImplementedError

    # ======================== public ==========================================

    def authenticateAndEncrypt(self, aad, plaintext, key, nonce):
        if self.keyLength != len(key):
            raise e.oscoreError('Key length mismatch.')

        if self.ivLength != len(nonce):
            raise e.oscoreError('IV length mismatch.')

        cipher = AES.new(key, AES.MODE_CCM, nonce, mac_len=self.tagLength)
        if aad:
            cipher.update(aad)
        ciphertext = cipher.encrypt(plaintext)
        digest = cipher.digest()
        ciphertext = ciphertext + digest
        return ciphertext

    def authenticateAndDecrypt(self, aad, ciphertext, key, nonce):
        digest = ciphertext[-self.tagLength:]
        ciphertext = ciphertext[:-self.tagLength]
        cipher = AES.new(key, AES.MODE_CCM, nonce, mac_len=self.tagLength)
        if aad:
            cipher.update(aad)
        try:
            plaintext = cipher.decrypt(ciphertext)
            cipher.verify(digest)
            return plaintext
        except ValueError:
            raise e.oscoreError('Invalid tag verification.')


class AES_CCM_64_64_128(CCMAlgorithm):
    value = d.COSE_AES_CCM_64_64_128
    keyLength = 16  # 128 bits
    ivLength = 7
    tagLength = 8
    maxSequenceNumber = 2 ** (min(ivLength * 8, 56) - 1) - 1
    maxIdLen = ivLength - 6

class AES_CCM_16_64_128(CCMAlgorithm):
    value = d.COSE_AES_CCM_16_64_128
    keyLength = 16
    ivLength = 13
    tagLength = 8
    maxSequenceNumber = 2 ** (min(ivLength * 8, 56) - 1) - 1
    maxIdLen = ivLength - 6

class SecurityContext:
    REPLAY_WINDOW_SIZE = 64

    #def __init__(self, masterSecret, senderID, recipientID, idContext=None, aeadAlgorithm=AES_CCM_16_64_128(), masterSalt='',
    #             hashFunction=hashlib.sha256):
    def __init__(self, securityContextFilePath):

        self.securityContextFilePath = securityContextFilePath
        self.lock     = threading.RLock()

        with open(self.securityContextFilePath, "r") as contextFile:

            self.securityContext = json.load(contextFile)

            # Instantiate AEAD algorithm
            aeadAlgorithmClassName = self.securityContext['aeadAlgorithm']
            aeadAlgorithmClass = getattr(sys.modules[__name__], aeadAlgorithmClassName)
            self.aeadAlgorithm = aeadAlgorithmClass()

            # Instantiate the hash function
            hashFunctionClassName = self.securityContext['hashFunction']
            self.hashFunction = getattr(hashlib, hashFunctionClassName)

            # mandatory parameters
            self.masterSecret = binascii.unhexlify(self.securityContext['masterSecret'])
            self.senderID = binascii.unhexlify(self.securityContext['senderID'])
            self.recipientID = binascii.unhexlify(self.securityContext['recipientID'])

            # optional parameters
            if 'masterSalt' in self.securityContext:
                self.masterSalt = binascii.unhexlify(self.securityContext['masterSalt'])
            else:
                self.masterSalt = bytes()

            if 'idContext' in self.securityContext:
                self.idContext = binascii.unhexlify(self.securityContext['idContext'])
            else:
                self.idContext = None

            if len(self.senderID) > self.aeadAlgorithm.maxIdLen or len(self.recipientID) > self.aeadAlgorithm.maxIdLen:
                raise e.oscoreError('Max ID length for AEAD algorithm {0} is {1}.'.format(self.aeadAlgorithm.value, self.aeadAlgorithm.maxIdLen))

        # Derived parameters
        self.commonIV = self._hkdfDeriveParameter(self.hashFunction,
                                                  self.masterSecret,
                                                  self.masterSalt,
                                                  bytes(),
                                                  self.idContext,
                                                  self.aeadAlgorithm.value,
                                                  'IV',
                                                  self.aeadAlgorithm.ivLength
                                                  )

        self.senderKey = self._hkdfDeriveParameter(self.hashFunction,
                                                   self.masterSecret,
                                                   self.masterSalt,
                                                   self.senderID,
                                                   self.idContext,
                                                   self.aeadAlgorithm.value,
                                                   'Key',
                                                   self.aeadAlgorithm.keyLength
                                                   )

        self.recipientKey = self._hkdfDeriveParameter(self.hashFunction,
                                                      self.masterSecret,
                                                      self.masterSalt,
                                                      self.recipientID,
                                                      self.idContext,
                                                      self.aeadAlgorithm.value,
                                                      'Key',
                                                      self.aeadAlgorithm.keyLength
                                                      )


    # ======================== public ==========================================

    def getIVLength(self):
        return self.aeadAlgorithm.ivLength

    def replayWindowLookup(self, sequenceNumber):
        if sequenceNumber in self.securityContext['replayWindow']:
            return False

        if sequenceNumber < min(self.securityContext['replayWindow']):
            return False

        return True

    def replayWindowUpdate(self, sequenceNumber, reset=False):
        assert sequenceNumber > min(self.securityContext['replayWindow'])
        assert sequenceNumber not in self.securityContext['replayWindow']

        with self.lock:
            if len(self.securityContext['replayWindow']) == self.REPLAY_WINDOW_SIZE:
                self.securityContext['replayWindow'].remove(min(self.securityContext['replayWindow']))

            if reset is False:
                self.securityContext['replayWindow'] += [sequenceNumber]
            else:
                self.securityContext['replayWindow'] = [sequenceNumber]

            with open(self.securityContextFilePath, "w") as contextFile:
                json.dump(self.securityContext, contextFile, indent=4, sort_keys=True)
        return

    def getSequenceNumber(self):
        with self.lock:
            self.securityContext['sequenceNumber'] += 1

            if self.securityContext['sequenceNumber'] > self.aeadAlgorithm.maxSequenceNumber:
                raise e.oscoreError('Reached maximum sequence number.')

            with open(self.securityContextFilePath, "w") as contextFile:
                json.dump(self.securityContext, contextFile, indent=4, sort_keys=True)
        return self.securityContext['sequenceNumber']

    # ======================== private ==========================================

    def _hkdfDeriveParameter(self, hashFunction, masterSecret, masterSalt, id, idContext, algorithm, type, length):

        info = cbor.dumps([
            id,
            idContext,
            algorithm,
            str(type),  # encode as text string
            length
        ])

        extract = hkdf.hkdf_extract(salt=masterSalt, input_key_material=masterSecret, hash=hashFunction)
        expand = hkdf.hkdf_expand(pseudo_random_key=extract, info=info, length=length, hash=hashFunction)

        return expand
