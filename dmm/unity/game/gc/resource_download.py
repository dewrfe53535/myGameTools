
import config
import requests
import aria2p
import os
import json
from util import getsign
from urllib.parse import urlparse
from typing import Callable


class Session(requests.Session):
    def request(self, method, url, **kwargs):
        return super().request(method, 'https://' + url, proxies=config.proxies, timeout=30, **kwargs)


class aria2downloader:
    def __init__(self) -> None:
        self.aria2 = aria2p.API(
            aria2p.Client(
                host="http://localhost",
                port=16800,
                secret=""
            ))
        self.aria2option = aria2p.Options(self.aria2, {})
        self.aria2option.user_agent = config.user_agent
        self.aria2option.allow_overwrite = True
        self.aria2option.auto_file_renaming = False
        self.aria2option.continue_downloads = False

    def downloadfile(self, fileurl, path):
        self.aria2option.dir = os.path.abspath(path)
        self.aria2.add(fileurl, options=self.aria2option)


class resourcemanager:
    def __init__(self, resource_path=f'gameresource/{config.device}/') -> None:
        self.websession = Session()
        self.websession.headers['User-Agent'] = config.user_agent
        self.aria2instancec = aria2downloader()
        self.resource_path = resource_path

    def selectmanifestdata(self, mtype='ab'):
        manifest = []
        match mtype:
            case 'ab':
                manifest = self.assetbundlemanifest['d']
            case 'advvoice':
                manifest = self.advoicemanifest['d']
            case 'master':
                manifest = self.mastermanifest['d']
        return manifest

    def setmanifestdata(self):
        self.manifestdata = self.websession.get(config.cdnhost + config.manifesturl).json()
        self.resourceFullurl = self.manifestdata['url']['resource']
        self.resourceversion = self.manifestdata['resource']['version']
        self.noinitversion = self.manifestdata['resource']['notinit_version']
        self.assetbundlemanifest = self.websession.get(config.cdnhost + config.assetbundleurl).json()
        self.advoicemanifest = self.websession.get(config.cdnhost + config.advvoiceurl).json()
        self.mastermanifest = self.websession.get(config.cdnhost + config.masterurl).json()

    def downloadData(self, mtype='ab', onlyNew=False, fileFilter: Callable = None):
        manifest = self.selectmanifestdata(mtype)
        for i in manifest:
            if fileFilter:
                if fileFilter(i['n']):
                    continue
            if onlyNew:
                localFilepath = os.path.join(self.resource_path, i['n'])
                if os.path.exists(localFilepath):
                    if os.path.getsize(localFilepath) == i['s']:
                        continue
            resurl = self.resourceFullurl + '/' + i['n']
            urlparseurl = urlparse(resurl)
            urlbody = urlparseurl.path
            downloadendpath = i['n'].rsplit('/', 1)[0] if '/' in i['n'] else ''
            downloadpath = os.path.join(self.resource_path, downloadendpath)
            os.makedirs(downloadpath, exist_ok=True)
            urlsign, ts = getsign(urlbody)
            finalurl = resurl + f'?s={urlsign}&t={ts}'
            self.aria2instancec.downloadfile(finalurl, downloadpath)

    def verifyDataIsRemoved(self):
        manifestAB = self.selectmanifestdata()
        manifestVOICE = self.selectmanifestdata('advvoice')
        manifestMASTER = self.selectmanifestdata('master')
        remotefilelist = [os.path.join(self.resource_path, i['n']) for i in manifestAB + manifestVOICE + manifestMASTER]
        localfilelist = []
        for folder, subfolders, files in os.walk(self.resource_path):
            for file in files:
                localfilelist.append(os.path.join(folder, file).replace('\\', '/'))
        removedDatalist = set(localfilelist) - set(remotefilelist)
        return removedDatalist

    def _saveMasterdata(self, masterdataName, masterdataData):
        dirpath = f'{self.resource_path}manifestData/{config.device}/r18'
        os.makedirs(dirpath, exist_ok=True)
        with open(os.path.join(dirpath, masterdataName), 'w+', encoding='utf-8') as f:
            json.dump(masterdataData, f)

    def saveMasterdata(self, overwriteManifest=False):
        if overwriteManifest:
            self._saveMasterdata('manifest.json', self.manifestdata)
        self._saveMasterdata('advvoice.json', self.advoicemanifest)
        self._saveMasterdata('master.json', self.mastermanifest)
        self._saveMasterdata('assetbundle.json', self.assetbundlemanifest)


if __name__ == '__main__':
    instance = resourcemanager()
    instance.setmanifestdata()
    instance.downloadData(onlyNew=True)
    instance.downloadData('advvoice', True)
    instance.downloadData('master', True)
    instance.saveMasterdata()
