import hmac
import json
import logging
import random
import time
import urllib
import zlib
from base64 import b64decode, b64encode
from hashlib import sha256

import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
from phpserialize3 import dumps as phpdump
from phpserialize3 import loads as phpload
from requests.adapters import HTTPAdapter

from config_all import *

urllib3.disable_warnings()

User_Agent = 'Android 10 API-29'
pf_type = '3'


def decryptdata(key, data: bytes):
    cipher = AES.new(key, AES.MODE_CBC)
    return cipher.decrypt(data)[16:]  # iv prefixed


def decryptolgsession(session):  # cookie中的session对应reponse的密钥
    data = b64decode(session)
    data = json.loads(data)
    value = b64decode(data['value'])
    iv = b64decode(data['iv'])
    res = unpad(decryptdata(ApiKey, iv + value), 16).decode()
    return phpload(res)


def decryptreponsedata(sessionid, sessiondata):
    aeskey = hmac.new(ApiKey, sessionid.encode(), digestmod=sha256).digest()
    data = decryptdata(aeskey, sessiondata)
    return zlib.decompress(data, 15 + 32)  # gzip


class Session(requests.Session):
    def request(self, method, url, **kwargs):
        if '?' in url:
            url += '&v=' + str(random.getrandbits(24))
        else:
            url += '?v=' + str(random.getrandbits(24))
        logging.debug(url)
        return super().request(method, url, proxies=proxies, timeout=30, **kwargs, verify=False)


class irismysteria_base:
    def __init__(self, user_id=None):
        self.Setisencrypt(isencryptrequest, isencryptreponse)
        self.req = Session()
        self.req.mount('http://', HTTPAdapter(max_retries=10))
        self.req.mount('https://', HTTPAdapter(max_retries=10))
        self.iserrraise = True
        self.cryptedLSessionId = ''
        self.sessionId = ''
        self.adduniquesession = False
        self.nextRequestUniqueId = ''
        self.waittime = 0
        self.AdditionalApiRequestHeader = {
            'app-version': appversion,
            'pf-type': pf_type,
            'User-Agent': User_Agent,
            'Accept-Encoding': 'gzip, deflate, br',
        }
        self.baseurl = f'https://{connecthost}/'
        if user_id is None:
            sessionurl = 'game_type'
        else:
            sessionurl = f'game_type?user_id={user_id}'
        self.req.headers = self.AdditionalApiRequestHeader
        self.typedata = self.apirequest(sessionurl)
        typedataver = self.typedata['versions']
        self.AdditionalApiRequestHeader.update({
            'asset-version': typedataver['assetversion'],
            'X-OLG-DEVICE': 'Android',
            'server-version': typedataver['server']
        })
        versionurl = 'version'
        self.AdditionalApiRequestHeader.update({
            'X-OLG-SESSION': self.cryptedLSessionId,
            'X-OLG-SESSION-NAME': 'olg_session'
        })

    def Setisencrypt(self, encryptreq, encryrep):
        self.encryptreq = encryptreq
        self.encryptrep = encryrep

    def setglobalwaittime(self, time):
        self.waittime = time

    def Decrypt(self, data):
        return decryptreponsedata(self.sessionId, data)

    def Encrypt(self, data):
        aeskey = hmac.new(ApiKey, self.sessionId.encode(),
                          digestmod=sha256).digest()
        iv = get_random_bytes(16)
        cipher = AES.new(aeskey, AES.MODE_CBC, iv)
        w = zlib.compressobj(level=1, wbits=16 + 9)
        datatoenc = b''
        v = 0
        for i in data:  # gzip压缩方法不详,login的data最终pad完是240字节(后来验证正常gzip服务器也接收)
            v += 1
            datatoenc += w.compress(i.encode())
            if v == 8:
                datatoenc += w.flush(zlib.Z_BLOCK)
                v = 0
        datatoenc += w.flush()
        data = iv + cipher.encrypt(pad(datatoenc, block_size=16))
        return data

    @staticmethod
    def genuniquesession(data):
        iv = get_random_bytes(16)
        cipher = AES.new(ApiKey, AES.MODE_CBC, iv)
        data = b64encode(cipher.encrypt(pad(data.encode(), 16)))
        b64iv = b64encode(iv)
        mac = hmac.new(ApiKey, (b64iv + data), digestmod=sha256).hexdigest()
        session = json.dumps(
            {'iv': b64iv.decode(), 'value': data.decode(), 'mac': mac}).encode()
        return b64encode(session)

    def apirequest(self, url, params=None, forcepost=False, reqtype='normal'):
        time.sleep(self.waittime)  # global wait time
        if self.adduniquesession:
            self.AdditionalApiRequestHeader['UNIQUE-SESSION'] = self.genuniquesession(
                phpdump(self.sessionId))
        if self.cryptedLSessionId:
            try:
                # 不del掉post后再设置无效，原因未知
                del self.AdditionalApiRequestHeader['X-Olg-Session']
            except KeyError:
                pass
            self.AdditionalApiRequestHeader['X-Olg-Session'] = self.cryptedLSessionId
        if not params or forcepost:
            reqdata = self.req.get(self.baseurl + url)

        else:
            if self.encryptreq:
                reqdata = self.Encrypt(json.dumps(params))
                self.AdditionalApiRequestHeader['Content-Type'] = 'application/octet-stream'
                reqdata = self.req.post(self.baseurl + url, data=reqdata)
                del self.AdditionalApiRequestHeader['Content-Type']
        return self.apireponse(reqdata)

    def apireponse(self, reponseobject):
        try:
            encryptedsession = urllib.parse.unquote(
                reponseobject.cookies['olg_session'])
            self.cryptedLSessionId = reponseobject.headers['X-Olg-Session']
            self.sessionId = decryptolgsession(encryptedsession)
            self.req.cookies.clear()
            if self.encryptrep:
                try:
                    return json.loads(self.Decrypt(reponseobject.content))
                except ValueError:
                    if self.iserrraise:
                        raise
                    return reponseobject.content
                except zlib.error:
                    if self.iserrraise:
                        raise
                    return
            else:
                try:
                    reponseobject = json.loads(reponseobject.content)
                    if reponseobject['status'] != 'OK':
                        if self.iserrraise:
                            raise ValueError
                    return reponseobject
                except json.JSONDecodeError:
                    if self.iserrraise:
                        raise
                    return reponseobject
        except KeyError:  # 任何请求错误都不会返回新的session
            print(reponseobject.content)
            if self.iserrraise:
                raise
            try:
                return json.loads(reponseobject.content)
            except json.JSONDecodeError:
                return reponseobject.content
