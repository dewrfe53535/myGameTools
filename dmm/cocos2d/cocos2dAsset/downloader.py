from threading import local
from .parser import ManifestJson, AssetInfo
from typing import Type
import os
import re
import requests
import chompjs
import json
from tenacity import retry, stop_after_attempt, wait_fixed
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from loguru import logger


class Session(requests.Session):
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_fixed(2),

    )
    def request(self, method, url, **kwargs):
        resp = super().request(method, url, timeout=10, **kwargs)
        logger.debug(url,method)
        if resp.status_code // 100 != 2:
            logger.warning(f'http {resp.status_code} ,failed to fetch {url}')
        if resp.status_code // 100 == 5:
            resp.raise_for_status()
        return resp


session = Session()


class assetDownloader:
    def __init__(self, config: dict) -> None:
        '''
        config: {
            'downloader_weburl': '', # 不填，仅适用于部分老版本
            'downloader_assetroot': '',  # 用于下载manifest的地址前缀
            'downloader_savepath': '', # 保存位置
            'downloader_threadnum': 10,
            'asset_baseurl': '', # 用于manifestJson拼接的地址前缀
        }
        '''
        self.config = config
        self.baseurl = self.config['downloader_weburl']
        self.manifestOfmanifestData = {}  # 清单的清单
        self.remoteBundles = []
        self.remoteUrl = ''
        self.manifestData = {}
        self.jsurl = '/bin/assets/{typename}/index.{version}.js'
        self.configurl = '/bin/assets/{typename}/config.{version}.json'
        self.downloadCallback = None # 会传递url,path,data，返回值为True则不继续做保存处理
        self.customManifestJson :Type[ManifestJson] = None 

    def _loadJson(self,jsondata):
        return json.loads(jsondata)

    def convertUrltoPath(self, url: str):
        url = urlparse(url)
        return os.path.join(self.config['downloader_savepath'], url.netloc.replace(':', '#COLON#'), url.path.strip('/'))

    def downloadAndSaveBinary(self, url, overwrite=False):
        path = self.convertUrltoPath(url)
        if not overwrite:
            if os.path.exists(path):
                return
        data = session.get(url)
        if data.status_code // 100 != 2:
            return
        data = data.content
        if self.downloadCallback:
            isTakeOver = self.downloadCallback(url, path, data)
            if isTakeOver:
                return

        self.mkdir(path)
        with open(path, 'wb') as f:
            f.write(data)

    def mkdir(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def saveTextFile(self, path, data):
        '''
        use bytes because some games use encryption
        '''
        self.mkdir(path)
        if isinstance(data, str):
            data = data.encode()
        with open(path, 'wb') as f:
            f.write(data)
        
    def loadFirstManifest(self, data: str):
        '''
        data:主程序的jsdata
        '''
        settingdata = chompjs.parse_js_object(data)
        self.manifestOfmanifestData = settingdata['bundleVers']
        # 考虑到主程序相关js的更新可以直接在打开时被mitm替换，这里不做保存处理，让GFSI兜底

    def loadSettingFromWeb(self, url):
        '''
        从网页中找到主设置文件，仅适用于部分老版本
        '''
        webdata = session.get(self.baseurl).text
        pattern = r'let settingUrl = window.asset_root\(\) \+ (.*?);'
        match = re.search(pattern, webdata)
        if match:
            setting_url = match.group(1)
            setting_url = self.config['downloader_assetroot'] + eval(setting_url)
        else:
            raise ValueError("failed to find setting url")
        settingdata = session.get(setting_url).text
        self.saveTextFile(self.convertUrltoPath(setting_url), settingdata)
        self.loadFirstManifest(settingdata)

    def downloadAllManifest(self, useLocal=True):
        '''
        url form :host/1/bin/assets/{typename}/{index|config}.{version}.{.js|.json}
        '''
        for i, j in self.manifestOfmanifestData.items():    
            if i in self.remoteBundles:
                url= self.remoteUrl + self.jsurl.format(typename=i, version=j)
            else:
                url = self.config['downloader_assetroot'] + self.jsurl.format(typename=i, version=j)  # set js url
            path = self.convertUrltoPath(url)
            if useLocal and os.path.exists(path):
                pass
            else:
                data = session.get(url).content
                self.saveTextFile(path, data)
            if i in self.remoteBundles:
                url= self.remoteUrl + self.configurl.format(typename=i, version=j)
            else:
                url = self.config['downloader_assetroot'] + self.configurl.format(typename=i, version=j)  # set configurl
            path = self.convertUrltoPath(url)
            if useLocal and os.path.exists(path):
                with open(path, 'rb') as f:
                    data = f.read()
            else:
                data = session.get(url).content
                self.saveTextFile(path, data)
            self.manifestData[i] = self._loadJson(data)

    def downloadAndSetImport(self, mj: ManifestJson, url, point, useLocal=True):
        localPath = self.convertUrltoPath(url)
        if useLocal and os.path.exists(localPath):
            with open(localPath, 'rb') as f:
                importData = f.read()
        else:
            importData = session.get(url).content
        if not importData:
            logger.error(f'{url} importData is None.')
            return
        if url.endswith('json'):
            mj.setInfoFromimport(point, self._loadJson(importData),os.path.basename(url))
        else:
            logger.warning(f'not know how to parse import {url}')
        if useLocal and os.path.exists(localPath):
            return
        self.saveTextFile(localPath, importData)

    def MTdownloadAndSetimport(self, mj: ManifestJson, downloadDict: dict, useLocal=True):
        with ThreadPoolExecutor(max_workers=self.config['downloader_threadnum']) as executor:
            for point, url in downloadDict.items():
                executor.submit(self.downloadAndSetImport, mj, url, point, useLocal)

    def MTdownloadAllNative(self, mj: ManifestJson, overwrite=False):
        with ThreadPoolExecutor(max_workers=self.config['downloader_threadnum']) as executor:
            for i in mj.getAllNativeUrl():
                executor.submit(self.downloadAndSaveBinary, i, overwrite)

    def downloadAllFromMJ(self, mj: ManifestJson, useLocal=True, guess=False):
        mj.mapExt()
        nidImport = mj.getAllINDimportDownloadUrl()
        packImport = mj.getAllpackDownloadUrl()
        self.MTdownloadAndSetimport(mj, packImport, useLocal)
        self.MTdownloadAndSetimport(mj, nidImport, useLocal)
        if guess:
            self.guesAllNotSetNativeExt(mj)
        self.MTdownloadAllNative(mj, not (useLocal))

    def getMJfromName(self, name):
        mj = ManifestJson(name, self.manifestData[name], self.config) if not self.customManifestJson else self.customManifestJson(name, self.manifestData[name], self.config)
        if name in self.remoteBundles:
            mj.remoteUrl = self.remoteUrl
        return mj

    def downloadFromSingleManifest(self, manifestName, useLocal=True, guess=False):
        mj = ManifestJson(manifestName, self.manifestData[manifestName], self.config) if not self.customManifestJson else self.customManifestJson(manifestName, self.manifestData[manifestName], self.config)
        if manifestName in self.remoteBundles:
            mj.remoteUrl = self.remoteUrl
        self.downloadAllFromMJ(mj, useLocal, guess)

    def downloadAllFromManifest(self, useLocal=True, guess=False):
        for i, j in self.manifestData.items():
            mj = ManifestJson(i, j, self.config) if not self.customManifestJson else self.customManifestJson(i, j, self.config)
            if i in self.remoteBundles:
                mj.remoteUrl = self.remoteUrl
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
