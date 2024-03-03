import 'pixi-spine' // Do this once at the very start of your code. This registers the loader!

import * as PIXI from 'pixi.js';
import { Spine } from 'pixi-spine';
import { Recorder, RecorderStatus } from "canvas-record";
import { AVC } from "media-codecs";

let frameRate = 60;
let canvasRecorder;

const app = new PIXI.Application(
    {
        width: 1280,
        height: 720,
        preserveDrawingBuffer: true
    }
);

app.view.id = 'main'
document.body.appendChild(app.view)


const tick = async () => {
    if (canvasRecorder.status != RecorderStatus.Recording) return;
    await canvasRecorder.step();
    if (canvasRecorder.status !== RecorderStatus.Stopped) {
        requestAnimationFrame(() => tick());
    }
}


export async function record(filepath, spine_animation = "cut_1") {
    return new Promise(async (resolve) => {
        canvasRecorder = new Recorder(app.renderer.view.getContext('webgl2'), {
            name: "spine-record",
            frameRate: frameRate,
            encoderOptions: {
                codec: AVC.getCodec({ profile: "High", level: "5.1" }),
            },
        });

        PIXI.Assets.load(filepath).then(async (resource) => {
            async function completeCallback() {
                await canvasRecorder.stop();
                animation.destroy();
                canvasRecorder.dispose();
                resolve(); // Resolve the promise when completeCallback is done
            }

            async function startCallback() {
                await canvasRecorder.start({
                    filename: filepath.split('/').pop().replace('.skel', '.mp4')
                });
                tick();
            }

            const animation = new Spine(resource.spineData);
            app.stage.addChild(animation);
            animation.state.addListener({
                start: startCallback,
                complete: completeCallback
            });

            animation.x = window.innerWidth / 2;
            animation.y = window.innerHeight / 2;
            if (animation.state.hasAnimation(spine_animation)) {
                animation.state.setAnimation(0, spine_animation, false);
            }
            else {
                animation.state.setAnimation(0, animation.stateData.skeletonData.animations[0].name, true);
            }
            animation.autoUpdate = true;
        });
    });
}

export async function screenshot(filepath, spine_animation = "wait_45F", isRecordEx = true) {
    return new Promise(async (resolve) => {
        PIXI.Assets.load(filepath).then(async (resource) => {
            const animation = new Spine(resource.spineData);
            app.stage.addChild(animation);
            animation.x = window.innerWidth / 2;
            animation.y = window.innerHeight / 2;
            if (animation.state.hasAnimation(spine_animation)) {
                animation.state.setAnimation(0, spine_animation, true);
            }
            else {
                animation.state.setAnimation(0, animation.stateData.skeletonData.animations[-1].name, true); // -1 for watit_45f
            }
            animation.state.tracks[0].timeScale = 0

            async function downloadCanvasAsImagePromise(canvasele, fileName, fileType = 'image/png') {
                downloadCanvasAsImage(canvasele, fileName, fileType)
                animation.destroy()
                resolve()
            }
            setTimeout(downloadCanvasAsImagePromise, 50, app.view, filepath.split('/').pop().replace('.skel', '.png')) //等待trackTime生效
        });
    })
};

function downloadCanvasAsImage(canvasele, fileName, fileType = 'image/png') {
    const canvas = canvasele;
    canvas.toBlob((blob) => {
        const blobURL = URL.createObjectURL(blob);
        const downloadLink = document.createElement('a');
        downloadLink.href = blobURL;
        downloadLink.download = fileName;
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
        URL.revokeObjectURL(blobURL);
    }, fileType);
}
