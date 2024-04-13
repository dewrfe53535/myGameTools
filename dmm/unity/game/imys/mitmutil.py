from collections import namedtuple
import sqlite3
import time
from typing import Dict, Union
import zlib
import hmac
import json
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
from base64 import b64decode, b64encode
from hashlib import sha256
from phpserialize3 import dumps as phpdump
from phpserialize3 import loads as phpload

database_name = 'imysmitm'


def decryptdata(key, data: bytes):
    iv = data[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.decrypt(data[16:])


def genuniquesession(data):
    iv = get_random_bytes(16)
    cipher = AES.new(ConnectionKey, AES.MODE_CBC, iv)
    data = b64encode(cipher.encrypt(pad(data.encode(), 16)))
    b64iv = b64encode(iv)
    mac = hmac.new(ConnectionKey, (b64iv + data), digestmod=sha256).hexdigest()
    session = json.dumps(
        {'iv': b64iv.decode(), 'value': data.decode(), 'mac': mac}).encode()
    return b64encode(session)


apiConfig = namedtuple('apiConfig', ['isOverwrite', 'isHaveField', 'funcReq', 'funcResp'], defaults=[False, False, False, False])


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


def saveApiData(urlpath, data: str, isOverwrite=False, datatable='apiinfo'):
    conn = sqlite3.connect(f"{database_name}.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT apiData FROM {datatable} WHERE apiPath = ?", (urlpath,))
    existing_url = cursor.fetchone()

    if existing_url:
        if isOverwrite:
            cursor.execute(f"UPDATE {datatable} SET apiData = ? WHERE apiPath = ?", (data, urlpath))
    else:
        cursor.execute(f"INSERT INTO {datatable} (apiPath, apiData) VALUES (?, ?)", (urlpath, data))

    conn.commit()
    conn.close()


def getApiData(urlpath, datatable='apiinfo') -> Union[Dict, str]:
    conn = sqlite3.connect(f"{database_name}.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT apiData FROM {datatable} WHERE apiPath = ?", (urlpath,))
    apidata = cursor.fetchone()[0]
    try:
        return json.loads(apidata)
    except json.JSONDecodeError:
        return apidata


defaultresponseData = json.dumps({
    'timestamp': int(time.time()) + 60 * 60 * 24 * 15,  # 确保时间相关的解锁
    'contents': {},
    'errors': {},
    "versions": {
        "server": "44",
        "resource": "2844129179",
        "appversion": "3.2.60",
        "assetversion": "20240411_1",
        "cacheclearversion": "2.6.0",
        "diffthroughmaster": "365",
        "master": "365",
        "minstoragesize": "400",
        "trackingmodaldate": "2021-01-22_12:00"
    },
    'status': 'OK'
})

defaultresponseHeader = {
    'Content-Type': 'application/json; charset="UTF-8"',
    'X-Olg-Response': '12',
    'X-Olg-Session': genuniquesession(phpdump('A')),
    'Access-Control-Allow-Origin': '*'
}
