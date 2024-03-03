'''
catalog数据的处理还有很多要调整的部分
'''
from config import *
#  https://github.com/kvarenzn/phisap
from ext import catalog
import requests
import time
import aria2p
import os
import json
import shutil
import builtins
import UnityPy
from pythonnet import set_runtime, _LOADED
if not _LOADED:
    set_runtime('coreclr')
import clr
#  https://github.com/nesrak1/AddressablesTools catalog.py部分id为负的解析不好处理
from AddressablesTools import AddressablesJsonParser
clr.AddReference(os.path.abspath(r'ext\addressabletool\AddressablesTools.dll'))
fullCatalogPraser = catalog.Catalog


def getLQbundle(bundle: str | bytes = None, jsondata: str = None):
    '''
    FIXME:仍然有部分Lowquality
    '''
    result = set()
    if bundle:
        ccd = AddressablesJsonParser.FromBundle(bundle)
    else:
        ccd = AddressablesJsonParser.FromString(jsondata)
    for i, j in ccd.Resources.items():
        match type(i):
            case builtins.int:
                pass
            case builtins.str:
                if 'LowQuality' in i:
                    for k in j:
                        if isinstance(k.Dependency, str):
                            if k.Dependency.endswith('.bundle'):
                                result.add(k.Dependency)
    return result


def downloadcurrentcatalog():
    data = requests.get(catalogurl)
    if catalogurl.endswith('.json'):
        return data.text
    env = UnityPy.load(data.content)
    for i in env.objects:
        if i.type == 'TextAsset':
            return i.read().decode('utf-8')


def savecurrentcatalog(data):
    nowtime = int(time.time())
    with open(f'resource/catalog_list/catalog_{nowtime}.json', 'w+') as f:
        f.write(data)


def getcleanfilelist(loadedjsondata: dict):
    prefix = loadedjsondata['m_InternalIdPrefixes']
    prefixurl = prefix[-1]  # assume the last is uri.
    fileindex = len(prefix) - 1
    bundlefile_clean = [i for i in loadedjsondata['m_InternalIds'] if i.startswith(f'{fileindex}#')]
    return prefix, prefixurl, fileindex, bundlefile_clean


def geturllist(loadedjsondata: dict, exclude=None):
    prefix, prefixurl, fileindex, bundlefile_clean = getcleanfilelist(loadedjsondata)
    if exclude:
        bundlefile_clean = set(bundlefile_clean) - exclude
    bundlefile_fullurl = [i.replace(f'{fileindex}#', f'{prefixurl}') for i in bundlefile_clean]
    return bundlefile_fullurl


def readcatalogfromfile(catalogtimestamp):
    with open(f'resource/catalog_list/catalog_{catalogtimestamp}.json', 'r') as f:
        return json.load(f)


def downloadfile(filelist, isnew=False):
    aria2 = aria2p.API(
        aria2p.Client(
            host="http://localhost",
            port=6800,
            secret=""
        ))
    aria2option = aria2p.Options(aria2, {})
    if isnew:
        aria2option.dir = os.path.abspath('resource/newbundle')
    else:
        aria2option.dir = os.path.abspath('resource/bundle')
    for i in filelist:
        download = aria2.add(i, options=aria2option)


def checknewcatalog():
    data = requests.get(cataloghashurl).text
    if not os.path.exists('resource/catalog_list/nowcataloghash'):
        with open('resource/catalog_list/nowcataloghash', 'w+') as f:
            f.write(data)
        return False
    else:
        with open('resource/catalog_list/nowcataloghash', 'r') as f:
            oldhash = f.read()
            if oldhash == data:
                return False
            else:
                with open('resource/catalog_list/nowcataloghash', 'w') as f:
                    f.write(data)
                return True


def downloadnewcatalog(oldts=1689558895, exclude: set =
                       True):
    nowjsondata = downloadcurrentcatalog()
    excludelist = getLQbundle(jsondata=nowjsondata)
    savecurrentcatalog(nowjsondata)
    if exclude:
        ddata = set(geturllist(json.loads(nowjsondata), excludelist)) - set(geturllist(readcatalogfromfile(oldts), excludelist))
    else:
        ddata = set(geturllist(json.loads(nowjsondata))) - set(geturllist(readcatalogfromfile(oldts)))
    downloadfile(list(ddata), isnew=True)


def removeNonexistFile(ts):
    prefix, prefixurl, fileindex, bundlefile_clean = getcleanfilelist(readcatalogfromfile(ts))
    filenamelist = [i.replace(f'{fileindex}#/', '') for i in bundlefile_clean]
    for root, dirs, files in os.walk('resource/bundle'):
        for file in files:
            file_path = os.path.join(root, file)

            if file not in filenamelist:
                # os.remove(file_path)
                shutil.move(file_path, 'resource/oldbundle/')
                print(f"To delete file: {file_path}")


def checkNotDownloadedFile(ts):
    prefix, prefixurl, fileindex, bundlefile_clean = getcleanfilelist(readcatalogfromfile(ts))
    filenamelist = [i.replace(f'{fileindex}#/', '') for i in bundlefile_clean]
    folder_files = os.listdir('resource/bundle')
    missing_files = [file for file in filenamelist if file not in folder_files]

    print("Missing files:")
    for file in missing_files:
        print(file)


def downloadfilesizemismatched(oldts, exclude=True):
    '''
    json data only
    '''
    filesizepair = {}
    downloadfilelist = []
    with open(f'resource/catalog_list/catalog_{oldts}.json', 'r') as f:
        data = f.read()
    excludelist = getLQbundle(jsondata=data)
    with open(f'resource/catalog_list/catalog_{oldts}.json', 'r') as f:
        catalogdata = fullCatalogPraser(f)
    for i in catalogdata.entries:
        if i['dependencyKey'] is None and i['provider'] == 'UnityEngine.ResourceManagement.ResourceProviders.AssetBundleProvider' and not i['internalId'].startswith('0#'):
            filesizepair[i['primaryKey']] = i['data']['json']['m_BundleSize']
    for i in filesizepair.items():
        name, size = i
        if os.path.exists(f'resource/bundle/{name}'):
            if os.path.getsize(f'resource/bundle/{name}') != size:
                if name in excludelist:
                    continue
                downloadurl = filerooturl + name
                downloadfilelist.append(downloadurl)
    if exclude:
        catalogdata = readcatalogfromfile(oldts)
        downloadfilelist = set(downloadfilelist) - getLQbundle(jsondata=json.dumps(catalogdata))
    downloadfile(downloadfilelist, True)

