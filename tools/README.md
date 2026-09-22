# tools/ — helper scripts

| File | What it's for |
|---|---|
| `hsv_tune.py` | Sliders to find the HSV range of your target color under the current lighting (roadmap step 3). Run it again in the demo room — lighting changes everything. |
| `pi_check.py` | Is this computer ready? Checks versions, face models, webcam, serial ports and (on the Pi) temperature and power — and **measures how fast** color and face detection really run. No windows, so it works over SSH. `--camera 1` for another camera, `--no-camera` to skip it. |

Run from the project root, with the robot's webcam plugged in:

```bash
.venv\Scripts\python tools\hsv_tune.py 1
```

The `1` is the camera index: laptops usually have their built-in camera at `0`, so the USB webcam is often `1`.
