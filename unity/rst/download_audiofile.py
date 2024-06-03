import re
import os
import multiprocessing
import requests
import clr

# C# import，当时相关模块不支持
from System.Reflection import Assembly
Assembly.UnsafeLoadFrom("dependence\\AssetStudioUtility.dll")
clr.AddReference("AssetStudio")
clr.AddReference("System")
from AssetStudio import AssetsManager

requests.adapters.DEFAULT_RETRIES = 5

def getunity():
    assetobj = AssetsManager()

    assetobj.LoadFiles([os.path.abspath('rst_file/cri_audio_version_list')])
    v1 = list(assetobj.assetsFileList[0].Objects)[2].Dump().replace('\t','')

    return v1
def compare():
    file = getunity()
    v2 =  re.findall(r'SheetName = "(.*?)"',file)
    v3 = list(os.walk('audio'))[0][2]
    v4 = list(set(v2)-set(v3))
    return v4

def download(did):
    print(did)
    with open('audio\\%s'%did,'wb') as file:
        body = requests.get('https://xxxxx.com/CRI/%s'%did,timeout=15).content

        file.write(body)

if __name__ == '__main__':
    p = multiprocessing.Pool(4)
    flist = compare()
    for i in flist:
        p.apply_async(download, args=(i,))
    p.close()
    p.join()