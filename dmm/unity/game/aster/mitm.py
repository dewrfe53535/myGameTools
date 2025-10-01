from mitmcommon import *
from mitmmisc import *
from gameCrypt import AESCryptoHandler
import asyncio
import json
from loguru import logger
from mitmproxy import http, options, ctx
from mitmproxy.tools import dump
from colorama import init, Fore, Back, Style
setattr(http.Request, 'noQueryPath', setmitmNoQueryPath())

class LoadOptions:
    def load(self, loader):
        allowHosts =  apiHost + cdnHost 
        allowHosts.append(dmmReciboApiHost)
        allowHosts.append(dmmOsapiHost)
        ctx.options.update(
            upstream_cert=False,
            connection_strategy='lazy',
            http2=False,
            allow_hosts=allowHosts
        )

class Cryptor:
    def __init__(self):
        self.authAes :AESCryptoHandler|None = None
        self.apiAes :AESCryptoHandler|None = None
        
    def request(self, flow: http.HTTPFlow):
        if flow.request.pretty_host in apiHost:
            match flow.request.noQueryPath:
                case '/api/auth/login-player':
                    data = flow.request.json()['Payload']
                    self.authAes,authData = AESCryptoHandler.decryptAndCreate(data,1001)
                    flow.metadata['decryptedRequest'] = authData
                    flow.comment += f"request:\n{authData}"
                case _:
                    if not flow.request.noQueryPath.startswith('/api/web'):
                        if flow.request.method == 'POST' and flow.request.content:
                            if self.apiAes:
                                data = self.apiAes.decrypt(flow.request.content)
                                flow.metadata['decryptedRequest'] = data
                                flow.comment += f"request:\n{data}"
                            else:
                                logger.warning(f"apiAes not init, can't decrypt request {flow.request.noQueryPath}")
    
    def response(self, flow: http.HTTPFlow):
        if flow.request.pretty_host in apiHost:
            match flow.request.noQueryPath:
                case '/api/auth/login-player':
                    data  = self.authAes.decrypt(flow.response.text)
                    data = json.loads(data)
                    password = data["Session"]["Key"]
                    onetimeToken = data["Session"]["OnetimeToken"]
                    self.apiAes = AESCryptoHandler(password, onetimeToken[:16],10001,onetimeToken[-16:])
                case _: 
                    if not flow.request.noQueryPath.startswith('/api/web'):
                        if self.apiAes:
                            data = self.apiAes.decrypt(flow.response.content)
                            flow.metadata['decryptedResponse'] = data
                            flow.comment += f"response:\n{data}"
                        else:
                                logger.warning(f"apiAes not init, can't decrypt request {flow.request.noQueryPath}") 
        if 'X-Access-Token' in flow.response.headers:
            onetimeToken = flow.response.headers['X-Access-Token']
            if self.apiAes:
                self.apiAes.iv = onetimeToken[-16:].encode()
                self.apiAes.salt= onetimeToken[:16]

class Unlocker:
    def __init__(self):
        pass

    def response(self, flow: http.HTTPFlow):
        if flow.request.pretty_host in apiHost:
            match flow.request.noQueryPath:
                case '/api/chara/list':
                    if realdata := flow.metadata.get('decryptedResponse'):
                        data = json.loads(realdata)
                        data = ApiModifier.modifyChara(data)
                        flow.metadata['decryptedResponse'] = json.dumps(data)
                        flow.metadata["needreEncrypt"] = 1
                case '/api/shop/hold':
                    if realdata := flow.metadata.get('decryptedResponse'):
                        data = json.loads(realdata)
                        data["Records"] = []
                        flow.metadata['decryptedResponse'] = json.dumps(data)
                        flow.metadata["needreEncrypt"] = 1
                case '/api/lyric/angel/list':
                    if realdata := flow.metadata.get('decryptedResponse'):
                        data = json.loads(realdata)
                        data = ApiModifier.modifyCharaLyric(data)
                        flow.metadata['decryptedResponse'] = json.dumps(data)
                        flow.metadata["needreEncrypt"] = 1
                case '/api/item/list':
                    if realdata := flow.metadata.get('decryptedResponse'):
                        data = json.loads(realdata)
                        data = ApiModifier.modifyItem(data)
                        flow.metadata['decryptedResponse'] = json.dumps(data)
                        flow.metadata["needreEncrypt"] = 1
                case "/api/user-possession/list":
                    if realdata := flow.metadata.get('decryptedResponse'):
                        data = json.loads(realdata)
                        data = ApiModifier.modifyPossession(data)
                        flow.metadata['decryptedResponse'] = json.dumps(data)
                        flow.metadata["needreEncrypt"] = 1
                        
class reEncryptor:
    def __init__(self) -> None:
        pass

    def response(self, flow: http.HTTPFlow):
        if flow.request.pretty_host in apiHost:
            if flow.metadata.get("needreEncrypt"):
                if realdata := flow.metadata.get('decryptedResponse'):
                    flow.response.content = cryptor.apiAes.encrypt(realdata.encode())
                            

cryptor = Cryptor()
 
