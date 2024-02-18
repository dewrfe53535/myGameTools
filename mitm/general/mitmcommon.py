from urllib.parse import urlparse, urlunparse
from mitmproxy import http
from loguru import logger
import mimetypes
import os
import pickle

__version__ = 202402182227


def setmitmNoQueryPath():
    # https://github.com/mitmproxy/mitmproxy/issues/6345 : path may include query
    @property
    def noQueryPath(self):
        return urlparse(self.path).path

    @noQueryPath.setter
    def noQueryPath(self, value):
        o = urlparse(self.url)._replace(path=value)
        self.url = urlunparse(o)
    return noQueryPath


class GeneralFileSaver:
    def __init__(self, dataPath, isOverwrite=False):
        self.blacklistHost = []
        self.blacklistHostPath = []
        self.dataPath = dataPath
        self.isOverwrite = isOverwrite

    def response(self, flow: http.HTTPFlow):
        if self.should_handle(flow):
            self.save_response(flow, self.should_save_header(flow))

    def should_handle(self, flow: http.HTTPFlow) -> bool:
        if (flow.request.pretty_host in self.blacklistHost or
                flow.request.pretty_host + flow.request.noQueryPath in self.blacklistHostPath):
            return False
        return True

    def should_save_header(self, flow: http.HTTPFlow):
        '''如果有.,认为有扩展名，就当作是一个完全静态的文件。必要时重写该方法。'''
        if '.' in flow.request.noQueryPath.rsplit('/', 1)[-1]:
            return False
        return True

    def save_response(self, flow: http.HTTPFlow, isSaveHeader=True):
        if flow.request.method not in ['OPTIONS', 'HEAD']:
            url_path: str = flow.request.noQueryPath
            if url_path.endswith('/'):
                # Handle the case of URL ending with '/', use __mitmindex__.html
                url_path += "__mitmindex__.html"

            # Normalize and create the full file path
            file_name = os.path.join(self.dataPath, flow.request.pretty_host, url_path.removeprefix('/'))
            # Create the directory structure if it doesn't exist
            os.makedirs(os.path.dirname(file_name), exist_ok=True)

            if not os.path.exists(file_name) or self.isOverwrite:
                # Save response content to the file
                logger.info(f'saving file : {file_name}')
                with open(file_name, 'wb') as file:
                    file.write(flow.response.content)
                if isSaveHeader:
                    # Save response headers to a separate file with .mitmheader extension
                    header_file_name = file_name + '.mitmheader'
                    with open(header_file_name, 'wb') as header_file:
                        pickle.dump(flow.response.headers, header_file)


class GeneralFileResponser(GeneralFileSaver):

    def __init__(self, dataPath, isOverwrite=False, isSaveHeader=True, toServer=True):
        self.blacklistHost = []
        self.blacklistHostPath = []
        self.dataPath = dataPath
        self.isOverwrite = isOverwrite
        self.toServer = toServer
        self.needSaveResp = []

    def request(self, flow: http.HTTPFlow):
        if self.should_handle(flow):
            flow.request.needSaveResp = False
            local_file = self.find_local_file(flow)
            if local_file:
                self.generate_local_response(flow, local_file)
            else:
                if self.toServer:
                    self.needSaveResp.append(flow.request.noQueryPath)
                else:
                    flow.response = http.Response.make(404)

    def response(self, flow: http.HTTPFlow):
        if self.should_handle(flow):
            if flow.request.noQueryPath in self.needSaveResp:
                self.save_response(flow)
                self.needSaveResp.remove(flow.request.noQueryPath)

    def find_local_file(self, flow: http.HTTPFlow) -> str:
        url_path = flow.request.noQueryPath
        if not url_path or url_path.endswith('/'):
            url_path += "__mitmindex__.html"

        file_name = os.path.join(self.dataPath, flow.request.pretty_host, url_path.removeprefix('/'))
        if os.path.exists(file_name):
            return file_name
        return None

    def generate_local_response(self, flow: http.HTTPFlow, local_file: str):
        headerPath = local_file + '.mitmheader'
        if os.path.exists(headerPath):
            with open(headerPath, 'rb') as f:
                headerInfo = pickle.load(f)
        else:
            headerInfo = {}
            contentType = mimetypes.guess_type(local_file)[0]
            if contentType:
                headerInfo[b'Content-Type'] = contentType
        logger.info(f'serving file :{local_file}')
        with open(local_file, 'rb') as f:
            fileData = f.read()
        flow.response = http.Response.make(200, fileData, headerInfo)


class optionsOK:
    def __init__(self) -> None:
        pass

    def request(self, flow):
        if flow.request.method == 'OPTIONS':
            flow.response = http.Response.make(204)
            flow.response.headers['allow'] = 'OPTIONS,GET,HEAD,POST'
