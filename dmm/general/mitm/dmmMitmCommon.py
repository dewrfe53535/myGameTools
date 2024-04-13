class dmmReciboApiResponser:
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
                apidata = getApiData(urlp, datatable='dmmReciboApidata')
            flow.response = http.Response.make(200, json.dumps(apidata))


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