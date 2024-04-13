from mitmdata.mitmcommon import *
from mitmdata.mitmutil import *
from loguru import logger
from mitmproxy.http import flow
from mitmproxy import http, options, ctx
from mitmproxy.tools import dump
from cryptprovider import *
import json
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
        allowHosts = [''] + apiHost
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

    def request(self, flow: flow):
        if flow.request.pretty_host in apiHost and self.isDecryptRequest:
            if flow.request.method == 'POST':
                if flow.request.headers['Content-Type'] == 'application/json':
                    reqEncJson = flow.request.json()
                    data = request_decrypt(reqEncJson['_Re'])
                flow.request.realData = json.loads(data)
                if self.isPrintRequest:
                    print(flow.request.url, '\n', data)

    def response(self, flow: flow):
        if flow.request.pretty_host in apiHost and self.isDecryptResponse:
            if flow.request.method != 'OPTIONS':
                if flow.response.headers['Content-Type'] == 'application/json':
                    flow.request.text = json.dumps(flow.request.realData)
                    respEncJson = flow.response.json()
                    if 're' in respEncJson:
                        data = response_decrypt(respEncJson['re'])
                        flow.response.set_text(data)


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
            flow.response = http.Response.make(200, data.encode(), defaultresponseHeader)  # data str会出现错误转义


class Apiresponser:
    def __init__(self, isLocal=True) -> None:
        self.apiConfigDict = {


        }
        '''
        如果不想继续替换，自定义函数要返回True
        '''
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
                    flow.response.set_text(json.dumps(apidata))

                elif staticFile := GFRI.find_local_file(flow):
                    GFRI.generate_local_response(flow, staticFile)

    def charaDetailHandle(self, flow: http.HTTPFlow):
        apidata = getApiData('/api/namelist/chara/detail', sid=flow.request.realData['chara_id'])
        flow.response.text = json.dumps(apidata)
        return True

    def episodeindexHandle(self, flow):
        apidata = getApiData('/api/namelist/episode/index', sid=flow.request.realData['chara_id'])
        flow.response.text = json.dumps(apidata)
        return True

    def episodeExecHandle(self, flow):
        apidata = getApiData('/api/namelist/episode/exec', sid=flow.request.realData['episode_id'])
        flow.response.text = json.dumps(apidata)
        return True


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


# addons = [LoadOptions(),optionsOK(),viewEncrypt(),dmmOsapiSaver(),ApiresponseSaver(),]
addons = [LoadOptions(), optionsOK(), FakeSession(), viewEncrypt(), dmmOsapiResponser(), Apiresponser(),]


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
