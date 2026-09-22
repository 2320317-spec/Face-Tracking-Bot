# pi/models/ — face detection model

The face detector expects `face_detection_yunet_2023mar.onnx` in this folder. It's a downloaded file, so `.gitignore` keeps it off GitHub — download it once on every machine that runs the code.

From the project root:

**Windows (PowerShell)**

```powershell
curl.exe -L -o pi/models/face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

**Raspberry Pi / Linux**

```bash
wget -P pi/models https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

The file is about 232 KB. It needs OpenCV 4.8 or newer, but **not OpenCV 5** — that version uses a different model file (`2026may`). The requirements files already pin OpenCV below 5.

Source: [OpenCV Zoo — YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
