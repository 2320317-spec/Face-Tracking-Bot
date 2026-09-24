# FollowBot — Color & Face Following Robot

A two-wheeled robot that follows a colored target or a person's face, and can be driven from a phone. A Raspberry Pi 4 does the vision (Python + OpenCV) and serves a small web page over WiFi; an Arduino Uno with a TB6612 motor shield drives the wheels.

> **Status:** in progress — building the vision code on a PC first. See the [roadmap](#roadmap).

## Features

- **Color mode** — finds a hardcoded color, turns toward it, drives up to it and stops at a set distance.
- **Face mode** — finds a face and follows it at about 1.5 m, like a dog following you.
- **Manual mode** — drive it yourself with an on-screen joystick.
- **Tricks** — spin, dance, nod and shake, on buttons. It plays one, then goes back to following.
- **Phone dashboard** — live camera view with the detection box, mode buttons, Engage and STOP. The page tints itself with what the robot is doing: green following, amber searching, red backing up.
- **Safe by default** — boots stopped, and stops on its own if the target, the phone or the Pi goes quiet.

## How it works

```
                  phone / laptop browser
        live view · Color/Face/Manual · Start · STOP · joystick
                            ▲
                            │ WiFi
                            ▼
Webcam ──USB──► Raspberry Pi 4 ──USB serial──► Arduino Uno + TB6612 shield ──► 2 motors
                vision + decisions   "fwd turn"    motor speeds + failsafe
```

Every camera frame, the Pi finds the target, decides how fast to drive and how hard to turn, and sends one line of text — `fwd turn`, each from −100 to 100 — to the Uno. The Uno turns that into wheel speeds, and stops the motors if the Pi goes quiet for half a second.

## Hardware

| Part | Job |
|---|---|
| Raspberry Pi 4 Model B | Vision, decisions, web dashboard, WiFi |
| USB webcam | The eye |
| Arduino Uno + LAFVIN TB6612FNG shield | Motor control |
| 2 × DC gear motors with wheels + caster | 2WD drivetrain |
| 2 × 18650 Li-ion cells | Motor power |
| 5 V 3 A power bank | Pi power |

Full parts list, wiring and prices: [build plan](docs/following-robot-plan.md#3-bill-of-materials).

## Repository layout

```
Face_Tracking_Bot/
├── README.md                  ← you are here
├── requirements-pc.txt        Python packages for the laptop
├── requirements-pi.txt        Python packages for the Raspberry Pi
├── .gitignore                 what Git never uploads (venv, face model, captures…)
├── .gitattributes             keeps line endings Linux-friendly for the Pi
├── pyrightconfig.json         tells VS Code that steps/ imports from pi/
│
├── docs/
│   ├── following-robot-plan.md   the full build plan
│   └── images/                   photos and diagrams
├── steps/                     step-by-step PC scripts (roadmap steps 1–5)
├── tools/                     helper scripts (HSV tuner)
├── pi/                        the robot program (runs on the Pi, or the PC with --dry)
│   ├── templates/             the phone page
│   └── models/                face detection model (downloaded, not on GitHub)
├── uno/
│   └── motor_controller/      Arduino Uno sketch
└── deploy/                    Pi setup: autostart on boot, WiFi hotspot
```

Each folder has its own `README.md` explaining what goes in it.

## Getting started (PC)

Everything is built and tested on a laptop first — all you need is the USB webcam.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-pc.txt
.venv\Scripts\python steps\01_live_feed.py
```

On Linux or the Pi, use `.venv/bin/python` instead of `.venv\Scripts\python`. In VS Code, pick the `.venv` interpreter once (Ctrl+Shift+P → *Python: Select Interpreter*) and the ▶ Run button uses it automatically.

## Roadmap

**On the PC** — details in [steps/README.md](steps/README.md)

- [x] 1. Live camera feed + FPS counter
- [x] 2. Live color detection — box, center `x`, width `w`
- [x] 3. HSV tuner with sliders
- [x] 4. Decision logic — `x` and `w` → `fwd turn` command (+ top-view simulator)
- [x] 5. Face detection with YuNet (simple + smart modes)
- [x] 6. Combine everything into `pi/follow.py` + the phone dashboard

**On the robot** — details in the [build plan](docs/following-robot-plan.md#7-build-sequence)

- [x] 7. Uno motor sketch + bench test
- [x] 8. Raspberry Pi setup
- [ ] 9. Assemble the robot
- [ ] 10. Calibrate and floor-test
- [x] 11. Autostart + hotspot for the demo

## Documentation

- [Where the project stands](docs/progress.md) — what works, measured speeds, what's left. **Start here.**
- [Build plan](docs/following-robot-plan.md) — design, parts, wiring, code reference, build sequence, troubleshooting.
- [Raspberry Pi setup](docs/pi-setup.md) — step by step, from a blank SD card to a checked Pi.
- [LLM companion](docs/llm-companion.md) — idea, not built: talking to the robot with a local model on the laptop.
- [Hand gestures](docs/hand-gestures.md) — idea, not built: controlling it by showing it your hand.

## Acknowledgements

- Face detection: [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) from the OpenCV Zoo.
- Motor shield: from the LAFVIN 2WD Smart Robot Car Kit V2.2.
