# This and old one is originally wrote for tskx.
import time
import requests
import copy
import os
import shutil
import UnityPy
import json
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

from ext.catalog import Catalog as fullCatalogPraser

proxies = {}


class Session(requests.Session):
    def request(self, method, url, **kwargs):
        return super().request(method, url, proxies=proxies, timeout=30, **kwargs)


class CatalogParser:
    def __init__(self):
        pass

    @staticmethod
    def _getSizeInfoWebGL(catalogData: fullCatalogPraser):
        sizeInfo = {}
        for i in catalogData.entries:
            if i['dependencyKey'] is None and i['provider'].startswith('UnityEngine.ResourceManagement.ResourceProviders'):
                sizeInfo[i['primaryKey']] = i['data']['json']['m_BundleSize']
        return sizeInfo

    @classmethod
    def loadCatalog(cls, catalogData: str, catalogType: str = 'WebGL'):
        thisCatalogItem = {'Items': {}, 'SizeInfo': {}}
        catalogData = fullCatalogPraser(StringIO(catalogData))
        Items = {}
        for i,j in catalogData.fname_map.items():
            if j is not None:
                Items[i] = j
        thisCatalogItem['Items'] = Items
        thisCatalogItem['SizeInfo'] = cls._getSizeInfoWebGL(catalogData)
        return thisCatalogItem

    @staticmethod
    def removeLQbundle(loadedCatalog) -> None:
        iterDict: dict = copy.deepcopy(loadedCatalog['Items'])
        for i in iterDict.keys():
            if '/LowQuality/' in i:
                bundlename = loadedCatalog['Items'][i]
                if bundlename in loadedCatalog['SizeInfo']:
                    del loadedCatalog['SizeInfo'][bundlename]
                del loadedCatalog['Items'][i]


class CatalogDownloader:
    def __init__(self) -> None:
        self.catalogPath = 'resource/catalog_list'
        self.bundlePath = 'resource/bundle'
        self.loadedCatalog = {}
        self.session = Session()
        self.bundleBaseUrl = ''

    def removeNonExistFileFromCatalog(self, catalogData: dict, dstPath='resource/oldbundle/') -> None:
        '''
        移动不在catalog中本地却有的文件(版本迭代淘汰)
        '''
        for root, dirs, files in os.walk(self.bundlePath):
            for file in files:
                file_path = os.path.join(root, file)

                if file not in catalogData['SizeInfo'].keys():
                    shutil.move(file_path, dstPath)
                    logger.info(f"To delete file: {file_path}")

    def downloadCurrentCatalog(self, catalogUrl, isSaveFile=True):
        data = self.session.get(catalogUrl)
        if not catalogUrl.endswith('.json'):
            env = UnityPy.load(data.content)
            for i in env.objects:
                if i.type.name == 'TextAsset':
                    data = i.read().text
        else:
            data = data.text
        self.loadedCatalog['current'] = CatalogParser.loadCatalog(data)
        if isSaveFile:
            with open(os.path.join(self.catalogPath, f'catalog_{int(time.time())}.json'), 'w+') as f:
                f.write(json.dumps(self.loadedCatalog['current']))
        return self.loadedCatalog['current']

    def _downloadBundle(self, bundlename):
        url = self.bundleBaseUrl + bundlename
        r = self.session.get(url)
        r.raise_for_status()
        with open(os.path.join(self.bundlePath, bundlename), 'wb') as f:
            f.write(r.content)

    def downloadBundle(self, loadedCatalog=None, isSkipSameFile=True,isSkipLowRes=True):
        '''
        isSkipSameFile:是否跳过同名且同大小的文件
        '''
        if loadedCatalog is None:
            loadedCatalog = list(self.loadedCatalog.values())[0]
        if isSkipLowRes:
            CatalogParser.removeLQbundle(loadedCatalog)
        for bundlename in loadedCatalog['SizeInfo'].keys():
            if isSkipSameFile:
                if os.path.exists(os.path.join(self.bundlePath, bundlename)):
                    if os.path.getsize(os.path.join(self.bundlePath, bundlename)) == loadedCatalog['SizeInfo'][bundlename]:
                        continue
            # use multithread to download
            with ThreadPoolExecutor(16) as executor:
                executor.submit(self._downloadBundle, bundlename)
