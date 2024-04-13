# 更新要更
# osapi里的版本日期
# mitm version 版本日期
# master/list的版本地址
# user/info

import asyncio
import urllib
from loguru import logger
from mitmproxy.http import flow
from mitmproxy import http, options, ctx
from mitmproxy.tools import dump
from mitmcommon import *
from mitmutil import *
from mitmutils import modifyApiData
from mitmproxy.script import concurrent

GFIpath = 'gameresource/webdata'
GFSI = GeneralFileSaver(GFIpath, True)
GFSI.blacklistHost.extend(apiHost + cdnHost)
GFSI.blacklistHost.append(dmmOsapiHost)
GFSI.blacklistHost.append('mitm.it')
GFRI = GeneralFileResponser(GFIpath, toServer=True)
GFRI.blacklistHost = GFSI.blacklistHost

setattr(http.Request, 'realData', setmitmRealDataProp())
setattr(http.Request, 'noQueryPath', setmitmNoQueryPath())


class FakeSession:
    def __init__(self) -> None:
        self.apiConfigDict = {

        }

    def request(self, flow):
        if flow.request.pretty_host in apiHost:
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
            if 'Content-Type' in flow.response.headers:
                if flow.response.headers['Content-Type'] == 'application/octet-stream' and 'X-Olg-Session' in flow.response.headers:
                    session = decryptolgsession(urllib.parse.unquote(
                        flow.response.headers['X-Olg-Session']))
                    flow.response.realsession = session
                    data = decryptapidata(session, flow.response.get_content()).decode()
                    data1 = json.loads(data)
                    data = json.dumps(data1)
                    flow.response.headers['Content-Type'] = "application/json; charset=\"UTF-8\""
                    flow.response.set_text(data)


class Apiresponser:
    def __init__(self, isLocal=True) -> None:
        self.apiConfigDict = {


        }
        self.apiReqFuncDict = {

        }

        self.apiRespFuncDict = {

        }
        self.tempUrlList = []

    @concurrent
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
                                    return
                else:
                    if staticfile := GFRI.find_local_file(flow):
                        logger.info(f"api url {flow.request.url} not found in api dict, will served by GFRI.")
                        GFRI.generate_local_response(flow, staticfile)
                    else:
                        logger.warning(f"resource {flow.request.noQueryPath} not found, will handled by GFRI.")
                        self.tempUrlList.append(flow.request.noQueryPath)

    @concurrent
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
                    apidata['timestamp'] = originData['timestamp']
                    apidata['versions'] = originData['versions']
                    flow.response.set_text(json.dumps(apidata))

                # elif staticFile := GFRI.find_local_file(flow):
                #     GFRI.generate_local_response(flow, staticFile)

                elif urlp in self.tempUrlList:
                    self.tempUrlList.remove(urlp)
                    GFSI.save_response(flow)

    def reqModifyFavorite(self, flow):
        unit_id = flow.request.realData['unit_id']
        modifyApiData.reqModifyFavorite(unit_id)

    def reqModifyDress(self, flow):
        modifyApiData.reqModifyDress(flow.request.realData)

    def respModifyFavorite(self, flow):
        apidata = modifyApiData.respModifyFavorite()
        originData = json.loads(flow.response.text)
        apidata['timestamp'] = originData['timestamp']
        apidata['versions'] = originData['versions']
        flow.response.set_text(json.dumps(apidata))
        return True


class ApiresponseSaver:
    def __init__(self) -> None:
        self.apiConfigDict = {

        }

    def response(self, flow: flow):
        if flow.request.pretty_host in apiHost:
            urlp = flow.request.noQueryPath
            if urlp in self.apiConfigDict:
                uapiConfig = self.apiConfigDict[urlp]
                saveApiData(urlp, flow.response.text, uapiConfig.isOverwrite)
            else:
                GFSI.save_response(flow)


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


class LoadOptions:
    def load(self, loader):
        allowHosts = ['ajax.googleapis.com'] + apiHost + cdnHost
        allowHosts.append(dmmOsapiHost)
        ctx.options.update(
            upstream_cert=False,
            connection_strategy='lazy',
            http2=False,
            allow_hosts=allowHosts
        )


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
    def __init__(self, resourcePath, serverVersion, localVersion=None, platform='WebGL') -> None:
        self.resourcePath = resourcePath
        self.serverVersion = serverVersion
        self.localVersion = localVersion if localVersion else serverVersion
        self.tempUrlList = []
        self.platform = platform

    @concurrent
    def request(self, flow: flow):
        if flow.request.pretty_host in cdnHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if self.serverVersion in urlp:
                    if '/sound/' + self.platform in urlp:
                        pathSuffix = urlp.split(self.serverVersion + '/assetbundle/sound/' + self.platform + '/', 1)[1]
                    elif 'movie/' in urlp:
                        pathSuffix = urlp.split(self.serverVersion + '/assetbundle/', 1)[1]
                    else:
                        try:
                            pathSuffix = urlp.split(self.serverVersion + '/assetbundle/' + self.platform + '/', 1)[1]
                            pathSuffix = 'assetbundle/' + pathSuffix
                        except IndexError:
                            pathSuffix = ''
                    filePath = os.path.join(self.resourcePath, self.localVersion, pathSuffix)
                    print(filePath)
                else:
                    filePath = ''
                if os.path.exists(filePath) and os.path.isfile(filePath):
                    logger.debug(f'serving resource:{filePath}')
                    with open(filePath, 'rb') as f:
                        data = f.read()
                        flow.response = http.Response.make(200, data, {'Access-Control-Allow-Origin': '*',
                                                                       'Access-Control-Allow-Headers': '*'})
                elif filePath := GFRI.find_local_file(flow):
                    logger.info(f"resource {filePath} not found in assetdata, will served by GFRI.")
                    GFRI.generate_local_response(flow, filePath)
                else:
                    logger.warning(f"resource {flow.request.noQueryPath} not found, will handled by GFRI.")
                    self.tempUrlList.append(flow.request.noQueryPath)

    @concurrent
    def response(self, flow):  # save web resource
        if flow.request.pretty_host in cdnHost:
            if flow.request.method != 'OPTIONS':
                urlp = flow.request.noQueryPath
                if urlp in self.tempUrlList:
                    self.tempUrlList.remove(urlp)
                    GFSI.save_response(flow)


# addons = [LoadOptions(), viewEncrypt(), ApiresponseSaver(), dmmOsapiSaver(), CheckReqData()]  # 依顺序执行
addons = [LoadOptions(), optionsOK(), viewEncrypt(), FakeSession(), RedirectResourceToLocal(r'gameresource\gameasset', 'xxxxxxxx_1'), dmmOsapiResponser(), Apiresponser(), CheckReqData(), GFRI]  # for offline ,resource need ENCRYPTED version


async def start_proxy():
    opts = options.Options(listen_host='0.0.0.0', listen_port=53535, ssl_insecure=True)
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
