# pi/models/ — face and hand models

Four model files from the [OpenCV Zoo](https://github.com/opencv/opencv_zoo). They're downloaded files, so `.gitignore` keeps them off GitHub — download them once on every machine that runs the code.

| File | Size | What it does | Needed for |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | 232 KB | **YuNet** — finds faces: box, 5 landmarks (eyes, nose, mouth corners), certainty | all face steps |
| `face_recognition_sface_2021dec.onnx` | 38.7 MB | **SFace** — recognizes faces: turns a face into a "fingerprint" of 128 numbers; the same person gives similar numbers | SMART mode ("follow only me"). Without it, SMART follows by position only. |
| `palm_detection_mediapipe_2023feb.onnx` | 3.8 MB | **Palm detector** — finds boxes where hands are, plus 7 rough points | gesture mode |
| `handpose_estimation_mediapipe_2023feb.onnx` | 4.0 MB | **Hand landmarks** — 21 points on one hand: wrist, and 4 per finger | gesture mode |

Both run entirely on the computer — no internet, no cloud. Face fingerprints are only kept in memory while the program runs, never saved to disk.

## Download

From the project root:

**Windows (PowerShell)**

```powershell
curl.exe -L -o pi/models/face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl.exe -L -o pi/models/face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
curl.exe -L -o pi/models/palm_detection_mediapipe_2023feb.onnx https://github.com/opencv/opencv_zoo/raw/main/models/palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx
curl.exe -L -o pi/models/handpose_estimation_mediapipe_2023feb.onnx https://github.com/opencv/opencv_zoo/raw/main/models/handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx
```

**Raspberry Pi / Linux**

```bash
wget -P pi/models https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
wget -P pi/models https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
wget -P pi/models https://github.com/opencv/opencv_zoo/raw/main/models/palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx
wget -P pi/models https://github.com/opencv/opencv_zoo/raw/main/models/handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx
```

Both need OpenCV 4.8 or newer, but **not OpenCV 5** (it uses a newer YuNet file, `2026may`). The requirements files already pin OpenCV below 5.

Sources: [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) · [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) · [palm detection](https://github.com/opencv/opencv_zoo/tree/main/models/palm_detection_mediapipe) · [hand landmarks](https://github.com/opencv/opencv_zoo/tree/main/models/handpose_estimation_mediapipe)

**The two hand models need their pictures in RGB**, not OpenCV's usual BGR. Feed them BGR and they simply never find a hand - no error, just nothing. `pi/gestures.py` does the swap.
