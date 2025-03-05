from dataclasses import dataclass, field
from .decodeUuid import decodeUuid
from loguru import logger


@dataclass
class AssetInfo:
    importType: str = ''
    importVersion: str = ''
    nativeVersion: str = ''
    uuid: str = ''
    importExt: str = '.json'
    nativeExt: str = ''
    realPath: str = ''


@dataclass
class PackInfo:
    packVersion: str = ''
    packPoint: list = field(default_factory=list)


class ManifestJson:
    def __init__(self, manifestName, jsondata: dict, config: dict) -> None:
        self.config = config
        self.jsondata = jsondata
        self.manifestName = manifestName
        self.localImportPath = ''
        self.assetList = [AssetInfo(uuid=decodeUuid(i)) for i in self.jsondata['uuids']]
        self.packinfoDict = {}
        versions = self.jsondata['versions']
        for i in range(0, len(versions['import']), 2):
            point = versions['import'][i]
            if isinstance(point, str):  # for debug resource
                self.assetList[self._getDebugResourceLocation(point)].importType = 'IND'
                self.assetList[self._getDebugResourceLocation(point)].importVersion = versions['import'][i + 1]
            elif len(puuid := self.assetList[point].uuid.split('@')[0]) == 9:  # for pack in new version,not sure
                self.assetList[point].importType = 'PACKSOURCE'
                self.packinfoDict[self.assetList[point].uuid] = PackInfo(versions['import'][i + 1])
            elif isinstance(point, int):
                self.assetList[point].importType = 'IND'
                self.assetList[point].importVersion = versions['import'][i + 1]
            else:
                self.packinfoDict[point] = PackInfo(versions['import'][i + 1])  # not work in new version
        for i in range(0, len(versions['native']), 2):
            point = versions['native'][i]
            if isinstance(point, int):
                self.assetList[point].nativeVersion = versions['native'][i + 1]
            else:
                self.assetList[self._getDebugResourceLocation(point)].nativeVersion = versions['native'][i + 1]
        for i, j in self.jsondata['packs'].items():
            if self.packinfoDict:
                self.packinfoDict[i].packPoint = j

    def _getDebugResourceLocation(self, uuid):
        return self.jsondata['uuids'].index(uuid)

    def convertInfoToUrl(self, resType, resid, version, ext):
        '''
        restype:native or import
        下载文件采用fiddler的导出结构(/域名/path)
        '''
        return '/'.join([self.config['asset_baseurl'], self.manifestName, resType, resid[:2], f'{resid}.{version}{ext}'])

    def getAllpackDownloadUrl(self):
        packurlDict = {}
        for i in self.packinfoDict:
            packurlDict[tuple(self.packinfoDict[i].packPoint)] = self.convertInfoToUrl('import', i, self.packinfoDict[i].packVersion, '.json')
        return packurlDict

    def getAllINDimportDownloadUrl(self):
        urlDict = {}
        for i, j in enumerate(self.assetList):
            if j.importVersion:
                urlDict[i] = self.convertInfoToUrl('import', j.uuid, j.importVersion, j.importExt)
        return urlDict

    def _parseImageAsset(self, data):
        # https://github.com/cocos/cocos-engine/blob/v3.8.6/cocos/asset/assets/image-asset.ts
        extnames = ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.pvr', '.pkm', '.astc']
        if '_' in data:
            data = data.split('_')[0]
        if '@' in data:
            data = data.split('@')[0]
        return extnames[int(data)]

    def _parseTexture2D_Meta(self, data):
        packConfig = data.split(',', 1)[0] if isinstance(data, str) else data
        match packConfig:
            case '0' | 0:
                return '.png'
            case '1' | 1:
                return '.jpg'
            case '2' | 2:
                return ''  # TODO: softlink
            case _:
                logger.error(f'unknown format:{packConfig}')

    def _get_DictNativeExt(self, data: dict):
        ext = []
        match data['type']:
            case 'cc.Texture2D':
                # new version stub
                if isinstance(data['data'], str):
                    for i in data['data'].split('|'):
                        ext.append(self._parseTexture2D_Meta(i))
                else:
                    for i in data['data']:
                        ext.append(self._parseTexture2D_Meta(i[0]))
                return ext
            case  'cc.ImageAsset':
                for i in data['data']:
                    ext.append(self._parseImageAsset(i[5][0]['fmt']))

            case _:
                logger.error(f'unknown data type:{data["type"]}')
        return ext

    def _find_NativeExt(self, data):
        '''
        使用.判断扩展名，不可靠，此外字体文件扩展名前变为文件夹，扩展名后为原名，所以不能简单地检查是否以.开头
        data  = packed_json[5](数据区)
        解析import文件具体涉及到cocos2d的反序列化:
        https://github.com/cocos/cocos-engine/blob/v3.8.3/cocos/asset/asset-manager/pack-manager.ts
        https://github.com/cocos/cocos-engine/blob/v3.8.3/cocos/serialization/deserialize.ts
        但我们只关心_native其所对应的扩展名
        少部分无法使用此方法
        '''
        def tryFinalGet(data):
            try:
                if isinstance(data, list):
                    if isinstance(data[0], list):
                        return tryFinalGet(data[0])
                    elif len(data) >= 3:
                        if isinstance(data[2], str):
                            if '.' in data[2]:
                                ext = data[2]
                                if not data[2].startswith('.'):
                                    ext = f'/{data[2]}'
                                return ext
                    if isinstance(data[0], str):
                        if data[0].count(',') == 7:
                            return self._parseTexture2D_Meta(data[0])
                elif isinstance(data, str):
                    if data.count(',') == 7:
                        return self._parseTexture2D_Meta(data)
                elif isinstance(data, dict):
                    if 'fmt' in data:
                        return self._parseTexture2D_Meta(data['fmt'])

            except (IndexError, TypeError, KeyError):
                return
        extList = []
        for i in data:
            if getext := tryFinalGet(i):
                extList.append(getext)

        return extList

    def setInfoFromimport(self, point: int | list[int] | tuple[int], packjsondata: list | dict):
        if isinstance(point, int):
            ext = self._find_NativeExt(packjsondata[5])
            if ext:
                if self.assetList[point].nativeVersion:
                    self.assetList[point].nativeExt = ext[0]
                    if len(self.assetList[point].nativeExt) > 10:
                        logger.warning(f'{point}-{self.assetList[i].uuid}-{self.assetList[point].nativeVersion} extension name is too long and may wrong.')
                        self.assetList[point].nativeExt = ''
        elif isinstance(point, list) or isinstance(point, tuple):
            if isinstance(packjsondata, list):
                ext = self._find_NativeExt(packjsondata[5])
            elif isinstance(packjsondata, dict):
                ext = self._get_DictNativeExt(packjsondata)
            if ext:
                ext.reverse()
                for i in point:
                    try:
                        i = int(i)
                    except ValueError:
                        i = self._getDebugResourceLocation(i)
                    if self.assetList[i].nativeVersion:
                        self.assetList[i].nativeExt = ext.pop()
                        if len(self.assetList[i].nativeExt) > 10:
                            logger.warning(f'{i}-{point}-{self.assetList[i].uuid}-{self.assetList[i].nativeVersion} extension name is too long and may wrong')
                            self.assetList[i].nativeExt = ''
                        self.assetList[i].importType = 'PACK'

    def getAllNativeUrl(self):
        urls = []
        for i in self.assetList:
            if i.nativeVersion:
                if i.nativeExt:
                    urls.append(self.convertInfoToUrl('native', i.uuid, i.nativeVersion, i.nativeExt))
                else:
                    logger.warning(f'{self.manifestName}-{i.uuid}-{i.nativeVersion} does not have a extension name.This will NOT add to download list.')
        return urls

    def setRealPaths(self):
        for i, j in self.jsondata['paths'].items():
            if not i.isdigit():
                i = self._getDebugResourceLocation(i)
            self.assetList[int(i)].realPath = j[0]

    def mapExt(self):
        for i, j in self.jsondata['extensionMap'].items():
            for point in j:
                self.assetList[int(point)].importExt = i
