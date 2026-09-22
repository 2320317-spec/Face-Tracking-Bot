# pi/ — the robot program

Everything the robot runs. It also runs on the PC with `--dry` (no Uno needed), so you can test it before the robot exists.

| File | What it is |
|---|---|
| `follow.py` | **The main program.** Every frame: camera → find the target → brain decides → send `fwd turn` to the Uno → update the web page. |
| `brain.py` | The decisions: follow / hold / back up, steering, searching. **Driving settings live here.** |
| `vision.py` | The eyes: camera, color detection, face detection + recognition, the SMART lock. **Color and face settings live here.** |
| `web.py` | The phone dashboard's web server. |
| `templates/index.html` | The phone page: live view, mode buttons, Start / STOP, joystick. |
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

The robot always starts **STOPPED** — nothing moves until you press **Start** on the page.
