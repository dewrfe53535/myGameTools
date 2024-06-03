# 老代码，可能问题较多
import base64
from py3rijndael import RijndaelCbc, ZeroPadding
import requests
import os
import clr
import pickle
import shutil
import UnityPy
requests.adapters.DEFAULT_RETRIES = 5

# C# 导入，由于pycryptodome不支持rijndael(256 key)
from System.Security.Cryptography import Rijndael, CryptoStream, CryptoStreamMode, PaddingMode  # much faster
from System.IO import MemoryStream, StreamWriter, StreamReader
clr.AddReference("System")
err = []


url1 = 'https://XXXXX/XXXXX'
aeskey = b'XXXXX'
aesiv = b'XXXXX'
rijndael_cbc = RijndaelCbc(
    key=aeskey,
    iv=aesiv,
    padding=ZeroPadding(32),
    block_size=32
)
req = requests.session()
headers = {'X-Unity-Version': '',
           'User-Agent': ''}
req.headers = headers
crijn = Rijndael.Create()
crijn.BlockSize = 256
crijn.Key = aeskey
crijn.IV = aesiv
crijn.Padding = PaddingMode.Zeros
crijnenc = crijn.CreateEncryptor(crijn.Key, crijn.IV)
crijndec = crijn.CreateDecryptor(crijn.Key, crijn.IV)


def cenc(bytevar):  # c# to encrypt
    v1 = MemoryStream()
    v2 = CryptoStream(v1, crijnenc, CryptoStreamMode.Write)
    v2.Write(bytevar, 0, len(bytevar))
    v2.FlushFinalBlock()
    return bytes(v1.ToArray())


def cdec(bytevar):  # c# to decrypt
    v1 = MemoryStream(bytevar)
    v2 = CryptoStream(v1, crijndec, CryptoStreamMode.Read)
    v3 = MemoryStream()
    v2.CopyTo(v3)
    return bytes(v3.ToArray())


def getassetlist():
    '''
    :return:资源列表
    '''
    v1 = req.get(url1).text
    v1 = base64.b64decode(v1)

    v1list = cdec(v1).decode().strip('\x00').split(',')

    return v1list


def downloadaddition():
    '''
    :no return
    下载与rst_file列表中不一样的资源
    '''
    req = requests.session()
    file = os.walk('rst_file')
    listall = getassetlist()
    file_name_list = []
    for i in listall:
        if '.normal' in i:
            listall.remove(i)
    for path, dir_list, file_list in file:
        for file_name in file_list:
            file_name_list.append('{0}:{1}'.format(file_name, os.path.getsize(os.path.join(path, file_name))))
    additionlist = list(set(listall) - set(file_name_list))
    print(additionlist)
    print(len(additionlist))
    if additionlist != []:
        for i in additionlist:
            if 'masterdata:' in i:
                continue
            try:
                v1 = req.get('https://XXXXX/XXXXX/' + i.split(':')[0]).content
            except requests.exceptions:
                if not os.path.exists("downloadtemp"):
                    tempfile = open("downloadtemp", "wb")
                    pickle.dump(additionlist, tempfile)
                    tempfile.close()
                    return
            with open('rst_newfile/%s' % i.split(':')[0], 'wb') as f:
                f.write(v1)
        for root, dirs, files in os.walk('rst_newfile'):
            for file in files:
                src_file = os.path.join(root, file)
                shutil.copy(src_file, 'rst_file')

    for i in additionlist:
        if 'masterdata:' in i:
            additionlist.remove(i)

    if os.path.exists("downloadtemp"):
        tempfile = open("downloadtemp", 'rb')
        pickle.load(tempfile)
        return [i.split(':')[0] for i in tempfile]
    if additionlist != []:
        return [i.split(':')[0] for i in additionlist]


def downloadall():
    for i in getassetlist():
        v1 = requests.get('https://XXXXX/XXXXX/' + i.split(':')[0]).content

        with open('rst_file/%s' % i.split(':')[0], 'wb') as f:
            f.write(v1)

    file = os.walk('rst_file2\\2')


def decryptfile(path, file_name):  #
    print(os.path.join(path, file_name))  # e.g.c:/exa/exa.u c:/exa exa.u
    with open(os.path.join(path, file_name), 'rb') as file:
        with open(os.path.join(path, file_name)[:-6] + '.unityfs', 'wb') as gnnext:
            filebyte = cdec(file.read())
            filelen = (32 - len(filebyte) % 32)  # 对zeropadding解密文件的兼容处理，避免缺少字节导致unitystudio打不开 ### 正确做法是不使用ZEROpadding
            if filelen != 0:
                for i in range(filelen):
                    filebyte += b'\x00'
            gnnext.write(filebyte)

def newdecrypt(decryptfileloc, decryptfilename, outputfilename, writedec=False):
    assetobj = UnityPy.load(decryptfileloc)
    isn = 0  # 防重复，不过实际运行后并没有发现重复
    for asset in assetobj.objects:
        if asset.type.name == 'TextAsset':
            encbyte = asset.read().script
            decbyte = cdec(encbyte)
            filelen = (32 - len(decbyte) % 32)
            if filelen != 0:
                for i in range(filelen):
                    decbyte += b'\x00'
            if writedec:
                with open('decmono\\%s' % outputfilename, 'wb') as f:
                    f.write(decbyte)
            with open('tempdec', 'wb') as fi:
                fi.write(decbyte)
            assetobj2 = UnityPy.load(os.path.abspath('tempdec'))
            for asset2 in assetobj2.objects:
                if asset2.type.name == 'Texture2D':
                    '''
                    try:
                        os.mkdir("pic_mono_output/%s"%decryptfilename)
                    except:
                        pass
                        '''
                    if isn == 0:
                        isn = ''
                    t2bitmap = asset2.read().image
                    t2bitmap.save("pic_mono_output/%s.png" % (outputfilename + str(isn)))

                    if isn == '':
                        isn = 0
                    # shutil.move("%s.png"%outputfilename,"pic_mono_output/%s/%s.png"%(decryptfilename,outputfilename+str(isn)))
                    isn += 1
                if asset2 == 'MonoBehaviour':
                    dumptext = asset2.dump().encode('utf-8', errors='ignore').decode()
                    '''
                    try:
                        os.mkdir("pic_monoo_output/%s"%decryptfilename)
                    except:
                        pass
                    '''
                    if isn == 0:
                        isn = ''
                    with open('pic_mono_output/{1}.txt'.format(decryptfilename, outputfilename + str(isn)),
                              'w+', encoding='utf8') as f:
                        f.write(dumptext)
                        f.close()
                    if isn == '':
                        isn = 0
            os.remove('tempdec')


# newdecrypt('rst_file/masterdata_encrypted','testasset,','testasset')

def newdecryptaddition():
    file = os.walk('rst_newfile')
    for path, dir_list, file_list in file:
        for file_name in file_list:
            if 'encrypted' in file_name:
                print(file_name)
                newdecrypt(os.path.join(path, file_name), file_name, file_name.replace('_encrypted', ''), True)


def newdecryptall():
    file = os.walk('rst_file')
    for path, dir_list, file_list in file:
        for file_name in file_list:
            if 'encrypted' in file_name:
                print(file_name)
                newdecrypt(os.path.join(path, file_name), file_name, file_name.replace('_encrypted', ''), True)


if __name__ == '__main__':
    downloadaddition()
