from .parser import ManifestJson, AssetInfo
from config import Config
import os
import re
import requests
import chompjs
from tenacity import retry, stop_after_attempt, wait_fixed
import json
from urllib.parse import urlparse
import threading
from loguru import logger


class Session(requests.Session):
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_fixed(5),

    )
    def request(self, method, url, **kwargs):
        resp = super().request(method, url, timeout=10, **kwargs)
        if resp.status_code // 100 != 2:
            logger.warning(f'http {resp.status_code} ,failed to fetch {url}')
        if resp.status_code // 100 == 5:
            resp.raise_for_status()
        return resp


session = Session()


class assetDownloader:
    def __init__(self) -> None:
        self.baseurl = Config.downloader_weburl
        self.manifestData_Dict = {}  # 清单的清单
        self.manifestDataDict = {}
        self.jsurl = '/bin/assets/{typename}/index.{version}.js'
        self.configurl = '/bin/assets/{typename}/config.{version}.json'
        self.thread_semaphore = threading.Semaphore(20)

    def convertUrltoPath(self, url: str):
        url = urlparse(url)
        return os.path.join(Config.downloader_savepath, url.netloc, url.path.strip('/'))

    def downloadAndSaveBinary(self, url, overwrite=False):
        path = self.convertUrltoPath(url)
        if not overwrite:
            if os.path.exists(path):
                return
        data = session.get(url)
        if data.status_code // 100 != 2:
            return
        data = data.content
        self.mkdir(path)
        with open(path, 'wb') as f:
            f.write(data)

    def mkdir(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def saveTextFile(self, path, data):
        self.mkdir(path)
        with open(path, 'w+', encoding='utf-8') as f:
            f.write(data)

    def loadFirstManifest(self, data: str):
        '''
        data:主程序的jsdata
        '''
        settingdata = chompjs.parse_js_object(data)
        self.manifestData_Dict = settingdata['bundleVers']
        # 考虑到主程序相关js的更新可以直接在打开时被mitm替换，这里不做保存处理，让GFSI兜底

    def loadSettingFromWeb(self, url):
        '''
        从网页中找到主设置文件
        '''
        webdata = session.get(self.baseurl).text
        pattern = r'let settingUrl = window.asset_root\(\) \+ (.*?);'
        match = re.search(pattern, webdata)
        if match:
            setting_url = match.group(1)
            setting_url = Config.downloader_assetroot + eval(setting_url)
        else:
            raise ValueError("failed to find setting url")
        settingdata = session.get(setting_url).text
        self.saveTextFile(self.convertUrltoPath(setting_url), settingdata)
        self.loadFirstManifest(settingdata)

    def downloadAllManifest(self, useLocal=True):
        '''
        url form :host/1/bin/assets/{typename}/{index|config}.{version}.{.js|.json}
        '''
        for i, j in self.manifestData_Dict.items():
            url = Config.downloader_assetroot + self.jsurl.format(typename=i, version=j)  # set js url
            path = self.convertUrltoPath(url)
            if useLocal and os.path.exists(path):
                pass
            else:
                data = session.get(url).text
                self.saveTextFile(path, data)

            url = Config.downloader_assetroot + self.configurl.format(typename=i, version=j)  # set configurl
            path = self.convertUrltoPath(url)
            if useLocal and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = f.read()
            else:
                data = session.get(url).text
                self.saveTextFile(path, data)
            self.manifestDataDict[i] = json.loads(data)

    def downloadAndSetImport(self, mj: ManifestJson, url, point, useLocal=True):
        localPath = self.convertUrltoPath(url)
        if useLocal and os.path.exists(localPath):
            with open(localPath, 'r', encoding='utf-8') as f:
                importData = f.read()
        else:
            importData = session.get(url).text
        if not importData:
            logger.error(f'{url} importData is None.')
            return
        mj.setInfoFromimport(point, json.loads(importData))
        self.saveTextFile(localPath, importData)

    def _MTdownloadAndSetimport(self, mj: ManifestJson, url, point, useLocal=True):
        with self.thread_semaphore:
            self.downloadAndSetImport(mj, url, point, useLocal=True)

    def MTdownloadAndSetimport(self, mj: ManifestJson, downloadDict: dict, useLocal=True):
        for point, url in downloadDict.items():
            thread = threading.Thread(target=self._MTdownloadAndSetimport, args=(mj, url, point, useLocal))
            thread.start()
            thread.join()

    def MTdownloadAllNative(self, mj: ManifestJson, overwrite=False):
        urlList: list[str] = mj.getAllNativeUrl()
        for i in urlList:
            thread = threading.Thread(target=self.downloadAndSaveBinary, args=(i, overwrite))
            thread.start()
            thread.join()

    def downloadAllFromMJ(self, mj: ManifestJson, useLocal=True, guess=False):
        nidImport = mj.getAllINDimportDownloadUrl()
        packImport = mj.getAllpackDownloadUrl()
        self.MTdownloadAndSetimport(mj, packImport, useLocal)
        self.MTdownloadAndSetimport(mj, nidImport, useLocal)
        if guess:
            self.guesAllNotSetNativeExt(mj)
        self.MTdownloadAllNative(mj, not (useLocal))

    def downloadAllFromManifest(self, useLocal=True, guess=False):
        for i, j in self.manifestDataDict.items():
            mj = ManifestJson(i, j)
            self.downloadAllFromMJ(mj, useLocal, guess)

    def guessNativeExt(self, mj: ManifestJson, asset: AssetInfo):
        guessList = ['.png', '.jpg', '.plist', '.ccon', '.mp3']
        for i in guessList:
            url = mj.convertInfoToUrl('native', i.uuid, i.nativeVersion, i)
            if session.head(url).status_code // 100 == 2:
                logger.info(f'{mj.manifestName}-{i.uuid}-{i.nativeVersion} native ext guess success.')
                asset.nativeExt = i

    def guesAllNotSetNativeExt(self, mj: ManifestJson):
        for i in mj.assetList:
            if i.nativeVersion and not i.nativeExt:
                self.guessNativeExt(mj, i)
