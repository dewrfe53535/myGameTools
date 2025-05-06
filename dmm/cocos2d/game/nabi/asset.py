from cocos2dAsset.downloader import assetDownloader
from cocos2dAsset.parser import ManifestJson
from config import *
from decrypt import decryptAndLoadJson,decrypt
from requests import Session
from hashlib import md5
from os import path

session = Session()


def getHashedFilename(basename):
    ext = path.splitext(basename)[1]
    enc_name = md5(basename.encode()+ SALT).hexdigest()
    enc_id = insert_chars(enc_name, [8, 13, 18, 23], '-')
    return enc_id

def insert_chars(s, positions, char):
    for i in sorted(positions, reverse=True):
        s = s[:i] + char + s[i:]
    return s

class NabiManifestJson(ManifestJson):
    def __init__(self, manifestName, jsondata: dict, config: dict) -> None:
        super().__init__(manifestName, jsondata, config)
        
    def convertInfoToUrl(self, resType, resid, version, ext, custom_url=None):
        original_url =  super().convertInfoToUrl(resType, resid, version, ext, custom_url)
        if ext[1:] in Unencrypted_extensions:
            return original_url
        basename = path.basename(original_url)
        if len(basename) < 23:
            return original_url
        else:
            for i in [8,13,18,23]:
                if basename[i] != '-':
                    return original_url
        hashedName = getHashedFilename(basename)
        org_toreplace = f"{basename[:2]}/{basename}"
        hashedPath = f"{hashedName[:2]}/{hashedName}{ext}"
        realUrl = original_url.replace(org_toreplace, hashedPath)
        return realUrl
    
    
class NabiDownloader(assetDownloader):
    def __init__(self, config: dict):
        super().__init__(config)
        
    def _loadJson(self,data):
        return decryptAndLoadJson(data)
    

def downloaderCallbackGen(downloader:NabiDownloader):
    def callback(url, savepath, data):
        if path.splitext(savepath)[1] in Unencrypted_extensions:
            return False
        data = decrypt(data)
        downloader.mkdir(savepath)
        with open (savepath,'wb') as f:
            f.write(data)
        return True
    return callback
    
def loadConfigAndCreate(configUrl):
    resp = session.get(configUrl).content
    downloader = NabiDownloader(cocosasset_config)
    assetConfig = decryptAndLoadJson(resp)
    downloader.manifestOfmanifestData = assetConfig['assets']['bundleVers']
    downloader.remoteBundles = assetConfig['assets']['remoteBundles']
    downloader.remoteUrl = assetConfig['assets']['server'] + 'remote'
    downloader.customManifestJson = NabiManifestJson
    downloader.jsurl = '/{typename}/index.{version}.js'
    downloader.configurl = '/{typename}/config.{version}.json'
    downloader.downloadCallback = downloaderCallbackGen(downloader)
    
    return downloader

