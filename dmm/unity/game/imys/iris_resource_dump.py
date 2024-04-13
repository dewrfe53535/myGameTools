import hmac
import json
import logging
import os
import random
from typing import Callable, Optional
import zlib
import UnityPy
import requests
from tenacity import retry, stop_after_attempt
from hashlib import sha256
from Crypto.Cipher import AES
from requests.adapters import HTTPAdapter


from config_all import *

aeskey = hmac.new(HmacKey, DataKey, digestmod=sha256).digest()
MasterKey = hmac.new(ApiKey, b'', digestmod=sha256).digest()


class Session(requests.Session):
    def request(self, method, url, **kwargs):
        url += '?x=' + str(random.getrandbits(50))
        logging.debug(url)
        return super().request(method, url, proxies=proxies, timeout=30, **kwargs)


session = Session()
session.mount('http://', HTTPAdapter(max_retries=10))
session.mount('https://', HTTPAdapter(max_retries=10))
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.54 Safari/537.36'}
Session.headers = headers


def perparefordownload():
    getpath(version)
    os.chdir(os.path.abspath(version))


def getpath(path):
    if not os.path.exists(path):
        os.makedirs(path)


def errtofile(text):
    with open('err.txt', 'a+') as f:
        f.write(text + '\n')


def decryptdata(data: bytes, aeskey=aeskey) -> bytes:
    cipher = AES.new(aeskey, AES.MODE_CBC)
    return cipher.decrypt(data)[16:]  # iv prefixed


def decryptvideoheader(data: bytes, XorKey=XorKey) -> bytes:  # should 352 bytes
    XorKey *= 88
    result = b''
    for a, b in zip(data, XorKey):
        result += bytes([a ^ b])
    return result


def decryptvideofile1(filename):
    with open(filename, 'rb') as f:
        encryptedheader = f.read(352)
        decryptedheader = decryptvideoheader(encryptedheader)
        data = f.read()
    with open(filename + '_dec', 'wb') as f2:
        f2.write(decryptedheader)
        f2.write(data)


def decryptmasterdata(masterdata: bytes):
    return zlib.decompress(decryptdata(masterdata, aeskey=MasterKey), 15 + 32)  # gzip


def downloadmanifest():
    perparefordownload()
    getpath(platform)
    data = session.get(bundlemanifest).content
    with open(f'{platform}\\{platform}', 'wb') as f:
        f.write(data)
    os.chdir('..')


def readmanifest():
    data = UnityPy.load(f'{platform}\\{platform}')
    try:
        manifest = data.objects[1]
    except BaseException:
        logging.error('read manifest failed')
        raise
    info = manifest.read_typetree()
    databytes = []
    for i in info['AssetBundleInfos']:
        allbyte = b''
        for j in range(15):
            allbyte += bytes([i[1]['AssetBundleHash']['bytes[%s]' % j]])
        databytes.append(allbyte)
    AssetBundleNames = info['AssetBundleNames']  # [(id1,name1)...]
    return AssetBundleNames, databytes


def downloadmasterdatafromjson(masterdataversion):
    getpath('master_{}'.format(masterdataversion))
    with open(r'master_{}\masterlist.json'.format(masterdataversion)) as f:
        data = f.read()
    masterdata = json.loads(data)['contents']['master_list']
    for i in masterdata:
        rep = download_downloader(masterdataurl.format(masterdataversion=masterdataversion) + i)
        try:
            data = decryptmasterdata(rep[1])
        except BaseException:
            continue
        realmasterdata = json.loads(data)['contents']['masterdata']
        with open(r'master_{}\{}.json'.format(masterdataversion, i), 'wb') as f:
            f.write(realmasterdata.encode())


def downloadmasterdatabyconnect(masterdataversion=None):
    try:
        os.makedirs('master_{}'.format(masterdataversion))
    except BaseException:
        pass
    try:
        from iris_connect import irismysteria as irisacc
    except BaseException:
        return
    d = irisacc()
    d.login(masterconnectuuid, masterconnectid)
    master = d.master_list()
    with open(r'master_{}\masterlist.json'.format(masterdataversion), 'wb') as f:
        f.write(json.dumps(master).encode())
    masterdata = master['contents']['master_list']
    if not masterdataversion:
        masterdataversion = master['versions']['master']
    for i in masterdata:
        rep = download_downloader(masterdataurl.format(masterdataversion=masterdataversion) + i)
        try:
            data = decryptmasterdata(rep[1])
        except BaseException:
            continue
        realmasterdata = json.loads(data)['contents']['masterdata']
        with open(r'master_{}\{}.json'.format(masterdataversion, i), 'wb') as f:
            f.write(realmasterdata.encode())


def media_getbaseurl(mediatype, additionmode=None):  # movie使用不同的url
    if '@' not in mediatype:
        if not additionmode:
            url = basemediaurl
        else:
            url = basemediaurl.replace(version, additionmode)
    else:
        if not additionmode:
            url = baseallurl
        else:
            url = baseallurl.replace(version, additionmode)
    return url


def readmediamanifest(mediatype, additionmode=None):
    mediatypes = mediatype.strip('@')
    try:
        if additionmode:
            path = f'..\\{additionmode}\\{mediatypes}\\manifest.json'
        else:
            path = f'{mediatypes}\\manifest.json'
        with open(path) as f:
            jsondata = json.load(f)
            filelist = [i['path'] for i in jsondata['entries']]
            return filelist, jsondata
    except BaseException:
        url = media_getbaseurl(mediatype, additionmode=additionmode)
        jsondata = session.get(url + mediatypes + '/manifest.json').json()
        filelist = [i['path'] for i in jsondata['entries']]
        return filelist, jsondata


@retry(sleep=5, stop=stop_after_attempt(10))
def download_downloader(url, skip_decrypt=True):
    rep = session.get(url)
    print(url)
    if rep.status_code == 200 and len(rep.content) == 0:
        raise ValueError
    if rep.status_code == 200 and not skip_decrypt and len(rep.content) % 16 != 0:
        raise ValueError
    return rep.status_code, rep.content


def tryrestore():
    with open('restoreprocess', 'r') as f:
        return int(f.read()) - 1  # 安全考虑,向前回滚1个文件


def download_data(start=0, end=None, try_restore: bool = True, additionmode: Optional[iter] = None, filter: Optional[Callable[[str], bool]] = None, noDecrypt=False) -> None:
    """
    :param filter:filter(filename) True to filter
    """
    if additionmode is not None:
        data = additionmode
        perparefordownload()
    else:
        perparefordownload()
        data = [i[1] for i in readmanifest()[0]]
    getpath('assetbundle')
    os.chdir('assetbundle')
    if os.path.exists('restoreprocess') and try_restore:
        start = tryrestore()
        logging.info(f'continue from {start}')
    now = start
    data = list(data)
    for i in data[start:end]:
        skipdecrypt = False if not noDecrypt else True
        officalNotEncrypted = False
        if filter:
            if filter(i):
                logging.info(f'skip id:{now},name:{i}')
                now += 1
                continue
        if '/' in i:
            path = '/'.join(i.split('/')[:-1])
            getpath(path)
        url = baseurl + i + '.encrypted'
        logging.info('downloading id:{0},url{1}:'.format(now, url))
        try:
            rep = download_downloader(url, skipdecrypt)
        except BaseException:
            continue
        if rep[0] != 200:
            # try without encrypt
            url = baseurl + i
            logging.info('try download no encrypted url:{0}'.format(url))
            rep = download_downloader(url)
            if rep[0] != 200:
                logging.warning('download failed url:{0}'.format(url))
                errtofile(url + ',response code error')
                continue
            else:
                officalNotEncrypted = True
                skipdecrypt = True
        rep = rep[1]
        if not skipdecrypt:
            realdata = decryptdata(rep)
        else:
            realdata = rep
        if noDecrypt:
            if officalNotEncrypted:
                filename = i
            else:
                filename = i + '.encrypted'
        else:
            filename = i
        with open(filename, 'wb') as f:
            f.write(realdata)
        now += 1
        with open('restoreprocess', 'w') as f:
            f.write(str(now))
    try:
        os.remove('restoreprocess')
    except BaseException:
        pass
    os.chdir('../..')


def download_media(additionmode=None, noDecrypt=False, skipExist=True):  # additionmode = oldversion (列表)
    perparefordownload()
    for i in manifest_list:
        if not additionmode:
            filelist, jsondata = readmediamanifest(i)
        else:
            filelist, jsondata = readmediamanifest(i, additionmode=None)
            filelist_old = readmediamanifest(i, additionmode=additionmode)[0]
            filelist = set(filelist) - set(filelist_old)
        url = media_getbaseurl(i, additionmode=None)
        mediatype = i.strip('@')
        getpath(mediatype)
        os.chdir(mediatype)
        with open('manifest.json', 'w+') as f:
            f.write(json.dumps(jsondata))
        for v in filelist:
            if skipExist:
                if os.path.exists(v):
                    continue
            code, data = download_downloader(url + mediatype + '/' + v)
            if code != 200:
                logging.warning('download failed url:{0}'.format(url + mediatype + '/' + v))
                errtofile(url + mediatype + '/' + v + ',response code error')
                continue
            if '/' in v:
                path = '/'.join(v.split('/')[:-1])
                getpath(path)
            with open(v, 'wb') as f:
                if not noDecrypt:
                    if v.endswith('.usm'):
                        data = decryptvideoheader(data[0:352]) + data[352:]
                f.write(data)
        os.chdir('..')
    os.chdir('..')


def compare_bundle(mode='simple'):
    if mode == 'json':
        download_data(additionmode=('hachiroku/json',))  # 确保json已下载
        json1 = json.loads(
            UnityPy.load(f'{version}\\assetbundle\\hachiroku\\json').objects[0].read().text)  # broken for python3.9(64)
        json2 = json.loads(UnityPy.load(f'{previous_version}\\assetbundle\\hachiroku\\json').objects[0].read().text)
        versionlist = []
        previous_versionlist = []
        for i in json1['d']:
            versionlist.append((i['p'], i['s']))
        for v in json2['d']:
            previous_versionlist.append((v['p'], v['s']))
        outlist = set(versionlist) - set(previous_versionlist)
        return outlist

    else:
        getpath(version)
        os.chdir(previous_version)
        asname, ashash = readmanifest()
        manifest_old = [i[1] for i in asname]
        if mode == 'complete':
            manifest_old = (zip(manifest_old, ashash))
        os.chdir('../' + version)
        asname, ashash = readmanifest()
        manifest_new = [i[1] for i in asname]
        if mode == 'complete':
            manifest_new = (zip(manifest_new, ashash))
        os.chdir('..')
        if mode == 'complete':
            return list(zip(*(set(manifest_new) - set(manifest_old))))[0]
        else:
            return (set(manifest_new) - set(manifest_old))


def download_addmedia(noDecrypt=False):
    download_media(additionmode=previous_version, noDecrypt=noDecrypt)


def download_addition(filter=None, mode='simple', noDecrypt=False):
    download_data(additionmode=compare_bundle(mode), filter=filter, noDecrypt=noDecrypt)