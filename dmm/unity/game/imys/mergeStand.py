# 合成立绘，并以动图形式保存(imageGlass可以以帧浏览)
# 输入解密的assetbundle文件
from PIL import Image
import UnityPy
import os
import sys

def convertFromUnityPy(ab):
    env = UnityPy.load(ab)
    imgDict = {}
    for i in env.objects:
        match i.type.name:
            case 'TextAsset':
                configData = readConfig(i.read().text)
            case 'Sprite':
                i = i.read()
                imgDict[i.name] = i.image

    standImage = imgDict.pop('stand')
    mergeStandAndEmotion(standImage, imgDict, configData)
    return imgDict


def readConfig(config: str):
    fconfig = {}
    configall = config.split('\r\n')
    for line in configall:
        key, values = line.strip().split(':')
        values = list(map(float, values.split(',')))
        fconfig[key] = values
    return fconfig


def mergeStandAndEmotion(stand: Image.Image, emotion: dict[str, Image.Image], configData):
    extraEmotionConfig = list(set(emotion.keys()) & set(configData.keys()))
    for i, image in emotion.items():
        if i in extraEmotionConfig:
            posName = i
        else:
            posName = 'face'
        image.posx = stand.size[0] / 2 - image.size[0] / 2 + configData[posName][0]
        image.posy = stand.size[1] / 2 - image.size[1] / 2 - configData[posName][1]

        image.posx = int(image.posx)
        image.posy = int(image.posy)
        emotion[i] = mergeImage(stand, image)


def mergeImage(image1: Image.Image, image2: Image.Image) -> Image.Image:
    image1 = image1.copy()
    image1.paste(image2, (image2.posx, image2.posy), image2)
    return image1

def output_png(imageDict,outputFolder):
    for i,j in imageDict.items():
        _output_png(j,os.path.join(outputFolder,i))

def _output_png(image,outputPath):
    image.save(outputPath+'.png',format='PNG',quality = 100)

def output_webp(imageList, outputPath):
    imageList[0].save(
        outputPath,
        save_all=True,
        append_images=imageList[1:],
        duration=1500,  # ms
        loop=0,
        format='WEBP',
        quality=100,
        lossless=1
    )

if __name__ == '__main__':
    path = (sys.argv[1])
    data = convertFromUnityPy(sys.argv[1])
    output_webp(list(data.values()),sys.argv[1] + '.webp')