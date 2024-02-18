
import json
import logging
import os
import urllib
import asyncio
import pickle
import mimetypes
from mitmproxy.http import flow
from mitmproxy import http, options, ctx
from mitmproxy.tools import dump
from mitmutil.util import *

setattr(http.Request, 'realData', setmitmRealDataProp())
# https://github.com/mitmproxy/mitmproxy/issues/6345 : path may include query
setattr(http.Request, 'noQueryPath', setmitmNoQueryPath())

GFIpath = 'gameresource/webdata'


class viewEncrypt:
    '''
    其他函数的前置解密依赖
    改req body直接改flow.request.realData
    '''

    def __init__(self, isPrintRequest=True, isDecryptRequest=True, isDecryptResponse=True) -> None:
        self.isPrintRequest = isPrintRequest
        self.isDecryptRequest = isDecryptRequest
        self.isDecryptResponse = isDecryptResponse

    def request(self, flow: flow):
        if flow.request.pretty_host in apiHost and self.isDecryptRequest:
            if 'X-OLG-SESSION' in flow.request.headers:
                session = decryptolgsession(urllib.parse.unquote(
                    flow.request.headers['X-OLG-SESSION']))
                flow.request.realsession = session
            if flow.request.method == 'POST':
                data = decryptapidata(session, flow.request.get_content()).decode()
                flow.request.realData = json.loads(data)
                if self.isPrintRequest:
                    print(flow.request.url, '\n', data)

    def response(self, flow: flow):
        if flow.request.pretty_host in apiHost and self.isDecryptResponse:
            if flow.response.headers['Content-Type'] == 'application/octet-stream':
                session = decryptolgsession(urllib.parse.unquote(
                    flow.response.headers['X-Olg-Session']))
                flow.response.realsession = session
                data = decryptapidata(session, flow.response.get_content()).decode()
                data1 = json.loads(data)
                data = json.dumps(data1)
                flow.response.headers['Content-Type'] = "application/json; charset=\"UTF-8\""
                flow.response.set_text(data)


class Apiresponser:
    def __init__(self) -> None:
        self.apiConfigDict = {
            ...
        }
        self.apiReqFuncDict = {
            ...
        }

    def request(self, flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if urlp in self.apiConfigDict:
                    uapiConfig = self.apiConfigDict[urlp]
                    if uapiConfig.isHaveField:
                        if uapiConfig.funcReq:
                            for i in self.apiReqFuncDict[urlp]:
                                i(flow)
                        # 让请求失败的接口正常刷新token
                        flow.request.noQueryPath = '/api/home'
                        if '_token1' in flow.request.realData:  # token1如果为空，请求时不会带上
                            token1 = flow.request.realData['_token1']
                        else:
                            token1 = ''
                        flow.request.realData = {"pc": 0, "r18": 1, "_token1": token1}
                else:
                    if staticfile := GFRI.find_local_file(flow):
                        GFRI.generate_local_response(flow, staticfile)

    def response(self, flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if urlp in self.apiConfigDict:
                    uapiConfig = self.apiConfigDict[urlp]
                    apidata = getApiData(urlp)
                    originData = json.loads(flow.response.text)
                    apidata['cdn_timestamp'] = originData['cdn_timestamp']
                    apidata['request_token'] = originData['request_token']
                    apidata['timestamp'] = originData['timestamp']
                    apidata['_token1'] = originData['_token1']
                    flow.response.set_text(json.dumps(apidata))
                elif staticFile := GFRI.find_local_file(flow):
                    GFRI.generate_local_response(flow, staticFile)

    def editHomeChara(self, flow):
        standaloneData = getApiData('/api/start-standalone')
        changeChara = json.loads(flow.request.realData['favorite_list'])
        standaloneData['contents']['user_status']['favorite_character_list'] = changeChara
        saveApiData('/api/start-standalone', json.dumps(standaloneData), True)


class ApiresponseSaver:
    def __init__(self) -> None:
        self.apiConfigDict = {
            ...
        }

    def response(self, flow: flow):
        if flow.request.pretty_host in apiHost:
            urlp = flow.request.noQueryPath
            if urlp in self.apiConfigDict:
                uapiConfig = self.apiConfigDict[urlp]
                saveApiData(urlp, flow.response.text, uapiConfig.isOverwrite)
            else:
                GFSI.save_response(flow)


class CheckReqData:
    def __init__(self) -> None:
        pass

    def request(self, flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method == 'POST':
                if flow.request.realDataIsModified:
                    encdata = Encrypt(flow.request.realsession, json.dumps(flow.request.realData).encode())
                    flow.request.set_content(encdata)


class RedirectResourceToLocal:
    def __init__(self, resourcePath, manifestPath) -> None:
        self.resourcePath = resourcePath
        self.manifestPath = manifestPath
        self.tempUrlList = []

    def request(self, flow: flow):
        if flow.request.pretty_host in cdnHost:
            urlp = flow.request.noQueryPath
            if 'files/manifest/' in urlp:
                pathSuffix = urlp.split('files/manifest/', 1)[1]
                filePath = os.path.join(self.manifestPath, pathSuffix)
            elif '/resources/' in urlp:
                pathSuffix = urlp.split('/resources/', 1)[1]
                filePath = os.path.join(self.resourcePath, pathSuffix)
            else:
                filePath = ''
            if os.path.exists(filePath):
                logging.debug(f'serving resource:{filePath}')
                with open(filePath, 'rb') as f:
                    data = f.read()
                    flow.response = http.Response.make(200, data)
            elif filePath := GFRI.find_local_file(flow):
                GFRI.generate_local_response(flow, filePath)
            else:
                self.tempUrlList.append(flow.request.noQueryPath)

    def response(self, flow):  # save web resource
        if flow.request.pretty_host in cdnHost:
            urlp = flow.request.noQueryPath
            if urlp in self.tempUrlList:
                self.tempUrlList.remove(urlp)
                GFSI.save_response(flow)


class FakeSession:
    def __init__(self) -> None:
        pass

    def request(self, flow):
        if flow.request.pretty_host in apiHost:
            flow.response = http.Response.make(200, defaultresponseData, defaultresponseHeader)


class dmmReciboApiSaver:
    def __init__(self) -> None:
        self.apiConfigDict = {'/v1/pc/sdk/initialize': apiConfig(),
                              '/v1/receipts': apiConfig(),
                              '/v1/batch/skus': apiConfig(),
                              }

    def response(self, flow):
        if flow.request.pretty_host == dmmReciboApiHost:
            urlp = flow.request.noQueryPath
            if urlp in self.apiConfigDict:
                uapiConfig = self.apiConfigDict[urlp]
                saveApiData(urlp, flow.response.text, uapiConfig.isOverwrite, datatable='dmmReciboApidata')


class LoadOptions:
    def load(self, loader):
        ctx.options.update(
            upstream_cert=False,
            connection_strategy='lazy'
        )


GFSI = GeneralFileSaver(GFIpath, True)
GFRI = GeneralFileResponser(GFIpath, toServer=True)

addons = [LoadOptions(), viewEncrypt(), RedirectResourceToLocal(resPath, manifestPath), ApiresponseSaver(), dmmReciboApiSaver(), dmmOsapiSaver(), CheckReqData(), GFSI]  # 依顺序执行


addonsOffline = [LoadOptions(), optionsOK(), RedirectResourceToLocal(resPath, manifestPath), FakeSession(), viewEncrypt(False, True, False), Apiresponser(), dmmReciboApiResponser(), dmmOsapiResponser(), GFRI]
# addons = addonsOffline
logging.basicConfig()


async def start_proxy():
    opts = options.Options(listen_host='127.0.0.1', listen_port=53535, ssl_insecure=True)
    master = dump.DumpMaster(
        opts,
        with_termlog=True,
        with_dumper=False,
    )
    master.addons.add(*addonsOffline)
    print('mitm proxy is running on port 53535.')
    await master.run()
    return master

if __name__ == '__main__':
    asyncio.run(start_proxy())
