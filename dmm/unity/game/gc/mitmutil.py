import base64
import time
import zlib
import hmac
import json
import hashlib
from base64 import b64decode, b64encode
from hashlib import sha256
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
from urllib.parse import quote
from phpserialize3 import dumps as phpdump
from phpserialize3 import loads as phpload


def decryptdata(key, data: bytes):
    iv = data[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.decrypt(data[16:])


def decryptapidata(sessionid, sessiondata):
    aeskey = hmac.new(ConnectionKey, sessionid.encode(),
                      digestmod=sha256).digest()
    data = decryptdata(aeskey, sessiondata)
    return (zlib.decompress(data, 15 + 32))


def decryptolgsession(session):  # cookie中的session对应reponse的密钥
    data = b64decode(session)
    data = json.loads(data)
    value = b64decode(data['value'])
    iv = b64decode(data['iv'])
    res = unpad(decryptdata(ConnectionKey, iv + value), 16).decode()
    return phpload(res)


def Decrypt(sessionid, data):
    return decryptapidata(sessionid, data)


def Encrypt(session, data: bytes):
    aeskey = hmac.new(ConnectionKey, session.encode(),
                      digestmod=sha256).digest()
    iv = get_random_bytes(16)
    cipher = AES.new(aeskey, AES.MODE_CBC, iv)
    w = zlib.compressobj(level=1, wbits=16 + 9)
    datatoenc = w.compress(data) + w.flush()
    data = iv + cipher.encrypt(pad(datatoenc, block_size=16))
    return data


def setmitmRealDataProp():  # 检测realData是否修改
    @property
    def realData(self):
        return self._realData

    @realData.setter
    def realData(self, value):
        if hasattr(self, 'realData'):
            self.realDataIsModified = True
        else:
            self.realDataIsModified = False
        self._realData = value
    return realData


def genuniquesession(data):
    iv = get_random_bytes(16)
    cipher = AES.new(ConnectionKey, AES.MODE_CBC, iv)
    data = b64encode(cipher.encrypt(pad(data.encode(), 16)))
    b64iv = b64encode(iv)
    mac = hmac.new(ConnectionKey, (b64iv + data), digestmod=sha256).hexdigest()
    session = json.dumps(
        {'iv': b64iv.decode(), 'value': data.decode(), 'mac': mac}).encode()
    return b64encode(session)


defaultresponseData = json.dumps({
    'timestamp': int(time.time()),
    'cdn_timestamp': int(time.time()),
    '_token1': '',
    'request_token': ''
})

defaultresponseHeader = {
    'Content-Type': 'application/json; charset="UTF-8"',
    'X-Olg-Response': '12',
    'X-Olg-Session': genuniquesession(phpdump('A'))
}


def getsign(urlbody, ts: int = None):
    if ts is None:
        ts = int(time.time()) + 3600 # expire time?
    md5 = hashlib.md5()
    md5.update(bytes(ConnectionKey.decode() + quote(urlbody) + str(ts), encoding='utf-8'))
    s = base64.urlsafe_b64encode(md5.digest()).decode()
    return s[:-2], ts
