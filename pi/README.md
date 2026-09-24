# pi/ — the robot program

Everything the robot runs. It also runs on the PC with `--dry` (no Uno needed), so you can test it before the robot exists.

| File | What it is |
|---|---|
| `follow.py` | **The main program.** Every frame: camera → find the target → brain decides → send `fwd turn` to the Uno → update the web page. |
| `brain.py` | The decisions: follow / hold / back up, steering, searching. **Driving settings live here.** |
| `vision.py` | The eyes: camera, color detection, face detection + recognition, the SMART lock. **Color and face settings live here.** |
| `moves.py` | The tricks: spin, dance, nod, shake. **Their timings live here**, and the simulator plays the same ones. |
| `gestures.py` | Gesture mode: finds your hand, reads its 21 points, names the signal. **Hand settings and speeds live here.** |
| `web.py` | The phone dashboard's web server. |
| `templates/index.html` | The phone page: live view, mode buttons, Engage / STOP, joystick. One self-contained file — no internet needed, so it still looks right on the robot's own hotspot. |
| `models/` | The two face models — downloaded, not on GitHub ([how to get them](models/README.md)). |

`steps/` 4, 4b and 5 use the same `brain.py` and `vision.py`, so a setting you tune here also changes the simulator and the step scripts.

## Run

**On the PC** (no robot needed), from the project root — use `--camera 1` if your USB webcam is the second camera:

```bash
.venv\Scripts\python pi\follow.py --dry --camera 1
```

Then open http://localhost:8000.

**On the Pi**, from `~/Face_Tracking_Bot`. Until the Uno is wired up, keep `--dry`:

```bash
~/robot-venv/bin/python pi/follow.py --dry
```

Then open http://followbot.local:8000 on your phone or laptop (same WiFi). Leave out `--dry` once the Uno is plugged in.

Stop it with **Ctrl+C** — it always sends a final stop to the motors.

## Options

| Option | What it does |
|---|---|
| `--dry` | Don't talk to the Uno — everything else runs |
| `--camera 1` | Use another camera (default 0) |
| `--port COM5` | The Uno's serial port, if it isn't found by itself (Windows: `COM…`) |
| `--mode face` | Start in `color`, `face` or `manual` mode (default `color`) |
| `--web-port 8000` | The dashboard's port |

The robot always starts **STOPPED** — nothing moves until you press **Engage** on the page.

## The dashboard

| | |
|---|---|
| **Tracking state** | Big word at the top — FOLLOWING, HOLDING, BACKING UP, SEARCHING, MANUAL. The whole page takes its color from it: green, amber, red, blue. |
| **Optical feed** | The live view with the boxes drawn in. In Face + Smart, **tap your face** = "this is me". |
| **Numbers** | fps · command sent to the Uno · target width · faces seen. |
| **Control deck** | Mode (Color / Face / Manual), then Simple / Smart and Forget me, then the joystick in Manual. |
| **Engage / STOP** | In the panel at the top, and again in a bar that slides up from the bottom once you scroll past it, so STOP is always a thumb away. |
| **Hand** | Drive it by showing signals to the camera: point up / left / right, two fingers to back up, fist to stay put, open palm to STOP. Nothing else is processed in this mode, so the hand models get the whole frame budget. |
| **Tricks** | Spin, Dance, Nod, Shake. A trick takes over the wheels, then hands them back to whatever mode was running. It only plays while the robot is **running**, and STOP cancels it. Timings are in `moves.py`; try them in the simulator first (keys 1–4). |
| **Keyboard** | On a laptop: **W A S D** or the arrow keys drive in Manual, **space** = STOP. |
| **✦** | Turns the background rain and the dragon off. Both are drawn by your phone, not the Pi. |
