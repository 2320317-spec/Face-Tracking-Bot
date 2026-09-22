# Where the project stands

Updated 23 September 2026. Short status of the build: what works, what's measured, what's left.

## Done

| Step | Result |
|---|---|
| 1–3 | Live camera feed, color detection (yellow), HSV tuner (`tools/hsv_tune.py`) |
| 4 | Decision logic in `pi/brain.py`: follow / hold / back up with hysteresis, proportional steering, searching when lost |
| 4b | Top-view simulator (`steps/04b_simulator.py`): drag yourself and a stranger, watch the robot decide |
| 5 | Face detection (YuNet) with two modes: **Simple** (biggest face) and **Smart** (locks onto you, recognizes you with SFace, ignores strangers) |
| 6 | The robot program `pi/follow.py` + phone dashboard (`pi/web.py`): color / face / manual, Start-STOP, joystick, tap-your-face. Verified on the laptop and on the Pi, viewed from a phone. |
| Pi setup | Pi 4 with Raspberry Pi OS Lite 64-bit, code cloned from GitHub, `deploy/setup_pi.sh` run, `tools/pi_check.py` passing |

## Measured (not estimated)

| | Value |
|---|---|
| Face detection (YuNet), Pi 4 | ~50 ms per frame → face mode ~19 fps |
| Face recognition (SFace), Pi 4 | ~65 ms per face (Smart runs it every 5 frames) |
| Color detection, Pi 4 | ~2.6 ms → limited only by the camera |
| Webcam | ~20 fps in good light, ~12 fps in dim light (it sends uncompressed YUYV) |
| Face detector's limit | faces below ~26 px wide aren't found → ~2.4 m at 480×360 |
| Recognition | same person 0.88–0.96, different people 0.20 (threshold 0.363) |

## Hardware

**Have:** Raspberry Pi 4, USB webcam, Arduino Uno, LAFVIN TB6612 motor shield, 2 motors with wheels, 16 GB SD card, ESP32 (spare, unused).

**Still needed:** 2× 18650 cells + holder + charger, 2WD chassis with caster, 5 V 3 A power bank (the 3000 mAh 2.1 A one is too weak for the robot), M3 standoffs, camera mount.

## Things to know

- **Camera number:** `1` on the laptop, `0` on the Pi (`--camera`).
- **The Pi:** `followbot.local`, or the address `hostname -I` prints (was 192.168.1.19). Dashboard on port 8000.
- **The repository is private**, so the Pi needs a read-only token to `git pull`.
- **Face models aren't on GitHub** (`.gitignore`) — `deploy/setup_pi.sh` downloads them, or see `pi/models/README.md`.
- **Face fingerprints are never saved to disk**; they only exist while the program runs.

## Next

1. **Step 7 — Uno sketch:** upload `uno/motor_controller/`, bench-test each wheel with the wheels off the ground (needs motor power: 18650s, 6×AA or a 9 V battery for a quick test).
2. **Step 9 — assemble** the chassis, and mount the camera ~20 cm up, tilted ~30°.
3. **Step 10 — calibrate** the distance thresholds and `KP` on the floor, then re-tune HSV in the demo room.
4. **Step 11 — autostart + WiFi hotspot** so the demo needs no laptop and no school WiFi.

## Ideas parked for later

- **One local web page for everything:** the dashboard plus HSV tuning and the simulator as a control panel.
- **Follow your body** once your face is found, so it can follow you when you turn away.
- **Brighten dark faces** (CLAHE) if the demo room's ceiling lights make faces hard to detect.
- **Lock the webcam's frame rate** so dim light doesn't drop it to 12 fps (`v4l2-ctl --list-ctrls`, look for `exposure_dynamic_framerate`).
- **Obstacle stop** with the HC-SR04, and a **tilt servo** for the camera.
