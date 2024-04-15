from mitmcommon import *
from mitmutil import *
from loguru import logger
from mitmproxy.http import flow
from mitmproxy import http, options, ctx
from mitmproxy.tools import dump

import json
import simplejson
import asyncio
import urllib


GFIpath = 'resource/webdata'
GFSI = GeneralFileSaver(GFIpath, True)
GFSI.blacklistHost.extend(apiHost + cdnHost)
GFSI.blacklistHost.append(dmmOsapiHost)
GFRI = GeneralFileResponser(GFIpath, toServer=True)
GFRI.blacklistHost = GFSI.blacklistHost

setattr(http.Request, 'realData', setmitmRealDataProp())
setattr(http.Request, 'noQueryPath', setmitmNoQueryPath())


class LoadOptions:
    def load(self, loader):
        allowHosts = [] + apiHost
        allowHosts.append(dmmOsapiHost)
        ctx.options.update(
            upstream_cert=False,
            connection_strategy='lazy',
            http2=False,
            allow_hosts=allowHosts
        )


class FakeSession:
    def __init__(self) -> None:
        self.apiConfigDict = {
        }

    def request(self, flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if urlp in self.apiConfigDict:
                    flow.response = http.Response.make(200, defaultresponseData, defaultresponseHeader)


class viewEncrypt:
    '''
    其他函数的前置解密依赖
    改req body直接改flow.request.realData
    '''

    def __init__(self, isPrintRequest=True, isDecryptRequest=True, isDecryptResponse=True) -> None:
        self.isPrintRequest = isPrintRequest
        self.isDecryptRequest = isDecryptRequest
        self.isDecryptResponse = isDecryptResponse

    def request(self, flow: http.HTTPFlow):
        if flow.request.pretty_host in apiHost and self.isDecryptRequest:
            if flow.request.method == 'POST':
                if flow.request.content.startswith(b'{"enc'):
                    flow.request.realData = json.loads(apiDataCrypt(
                        bytes(flow.request.json()['enc'], encoding='utf-8'), cryptkey_request))
                    if self.isPrintRequest:
                        print(flow.request.url, '\n', flow.request.realData)
                else:
                    flow.request.realData = flow.request.json()

    def response(self, flow: http.HTTPFlow):
        if flow.request.pretty_host in apiHost:
            if 'content-type' in flow.response.headers:
                if flow.response.headers['content-type'] == 'application/json':
                    if not flow.response.content.startswith(b'{'):
                        flow.response.content = apiDataCrypt(flow.response.content, cryptkey_response)
            if hasattr(flow.request, 'realData'):
                flow.request.text = json.dumps(flow.request.realData)


class ApiresponseSaver:
    def __init__(self) -> None:
        self.apiConfigDict = {
        }

    def response(self, flow: flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if urlp in self.apiConfigDict:
                    uapiConfig = self.apiConfigDict[urlp]
                    saveApiData2(urlp, flow.response.text, uapiConfig.isOverwrite)
                else:
                    GFSI.save_response(flow)


class Apiresponser:
    def __init__(self, isLocal=True) -> None:
        self.apiConfigDict = {

        }
        self.apiReqFuncDict = {

        }

        self.apiRespFuncDict = {
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
                                abortsign = i(flow)
                                if abortsign:
                                    return True
                else:
                    if staticfile := GFRI.find_local_file(flow):
                        GFRI.generate_local_response(flow, staticfile)

    def response(self, flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if urlp in self.apiConfigDict:
                    uapiConfig = self.apiConfigDict[urlp]
                    if uapiConfig.funcResp:
                        for i in self.apiRespFuncDict[urlp]:
                            abortsign = i(flow)
                            if abortsign:
                                return
                    apidata = getApiData(urlp)
                    originData = json.loads(flow.response.text)
                    apidata['server_time'] = originData['server_time']
                    flow.response.set_text(json.dumps(apidata))

                elif staticFile := GFRI.find_local_file(flow):
                    GFRI.generate_local_response(flow, staticFile)

    def storyPlayResp(self, flow):
        apidata = getApiData('/api/story/play')
        originData = json.loads(flow.response.text)
        apidata['server_time'] = originData['server_time']
        advid = flow.request.realData['adv_id']
        apidata['result']['scenario_list'] = json.loads(get_storylist_by_unitid(advid // 10))
        flow.response.text = json.dumps(apidata)
        return True


class dmmOsapiSaver:
    def __init__(self) -> None:
        self.apiConfigDict = {'/gadgets/ifr': apiConfig(),
                              '/gadgets/makeRequest': apiConfig(funcResp=True)
                              }
        self.respFuncDict = {
            '/gadgets/makeRequest': [self.custom_makeReq_resp]
        }

    def response(self, flow):
        if flow.request.pretty_host == dmmOsapiHost:
            urlp = flow.request.noQueryPath
            if urlp in self.apiConfigDict:
                uapiConfig = self.apiConfigDict[urlp]
                if not uapiConfig.funcResp:
                    saveApiData(urlp, flow.response.text, uapiConfig.isOverwrite, datatable='dmmOsApidata')
                else:
                    for i in self.respFuncDict[urlp]:
                        i(flow)
            else:
                GFSI.save_response(flow)

    def custom_makeReq_resp(self, flow: http.HTTPFlow):
        if flow.request.method == 'POST':
            mrdataUrl = urllib.parse.parse_qs(flow.request.get_text())['url'][0]
            uapiConfig = self.apiConfigDict[flow.request.noQueryPath]
            saveApiData(mrdataUrl, flow.response.text, uapiConfig.isOverwrite, datatable='dmmOsApiMRdata')


class dmmOsapiResponser:
    def __init__(self) -> None:
        self.apiConfigDict = {'/gadgets/ifr': apiConfig(),
                              '/gadgets/makeRequest': apiConfig(funcReq=True)
                              }
        self.reqFuncDict = {
            '/gadgets/makeRequest': [self.custom_makeReq_req]
        }

    def request(self, flow):
        if flow.request.pretty_host == dmmOsapiHost:
            urlp = flow.request.noQueryPath
            if urlp in self.apiConfigDict:
                uapiConfig = self.apiConfigDict[urlp]
                if not uapiConfig.funcReq:
                    apidata = getApiData(urlp, datatable='dmmOsApidata')
                    flow.response = http.Response.make(200, apidata.encode())
                else:
                    for i in self.reqFuncDict[urlp]:
                        i(flow)
            elif staticFile := GFRI.find_local_file(flow):
                GFRI.generate_local_response(flow, staticFile)

    def custom_makeReq_req(self, flow: http.HTTPFlow):
        if flow.request.method == 'POST':
            mrdataUrl = urllib.parse.parse_qs(flow.request.get_text())['url'][0]
            uapiConfig = self.apiConfigDict[flow.request.noQueryPath]
            data = getApiData(mrdataUrl, datatable='dmmOsApiMRdata')
            flow.response = http.Response.make(200, data.encode())  # data str会出现错误转义


class dmmSDKFake:
    def response(self, flow):
        if flow.request.pretty_host == dmmSDKHost:
            if flow.request.method == 'POST':
                if flow.request.url.endswith('sdk/request'):
                    flow.response.text = '{"result_code":0,"onetime_token":"1111111111111111111111111111111","install_status":"0","accept_time":1689212348}'


class CheckReqData:
    def __init__(self) -> None:
        pass

    def request(self, flow):
        if flow.request.pretty_host in apiHost:
            if flow.request.method == 'POST':
                if flow.request.realDataIsModified:
                    encdata = apiDataCrypt(json.dumps(flow.request.realData).encode(), cryptkey_request)
                    flow.request.set_content(encdata)
                    data = simplejson.dumps({"enc": encdata})
                    flow.request.set_text(data)


addons = [optionsOK(), dmmSDKFake(), FakeSession(), viewEncrypt(), Apiresponser(), CheckReqData()]


async def start_proxy():
    opts = options.Options(listen_host='127.0.0.1', listen_port=53535, ssl_insecure=True)
    master = dump.DumpMaster(
        opts,
        with_termlog=True,
        with_dumper=False,
    )
    master.addons.add(*addons)
    print('mitm proxy is running on port 53535.')
    await master.run()
    return master

if __name__ == '__main__':
    asyncio.run(start_proxy())
