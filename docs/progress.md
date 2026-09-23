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
| 6b | Dashboard redesigned in the SentryCore style (glass panels, the page tints itself with the robot's state, animated background). Plain CSS, no CDN, so it still looks right on the robot's own hotspot. |
| 7 | Uno sketch written (`uno/motor_controller/`): compiles for the Uno (16% of its memory), wheel mixing verified by hand, built-in `t` bench test. **Not yet uploaded — the Uno is away.** |
| 11a | **Autostart works.** `deploy/install_service.sh` installed on the Pi; it boots, runs `follow.py` and serves the dashboard with no laptop. Options live in `/etc/default/followbot` (currently `--dry`). |
| 11b | **Hotspot works, tested away from home.** The Pi broadcasts **FollowBot**; laptop and iPad join it and open `http://10.42.0.1:8000`, SSH at `myke@10.42.0.1`. Profile is `followbot-ap`, `autoconnect yes`, priority 100 — so it starts on every boot, anywhere. **Step 11 is done.** |
| Tricks | `pi/moves.py`: spin, dance (single-single-double-double), nod, shake. Buttons on the dashboard, keys 1-4 in the simulator. Only play while running; STOP cancels. Timings checked against the simulator's motion model - spin is one full turn. |
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

**Have:** Raspberry Pi 4, USB webcam, LAFVIN TB6612 motor shield, 2 motors with wheels **mounted on the chassis**, 4× 18650 cells in **two 2-slot holders** (7.4 V each — one runs the robot, one is a spare), 16 GB SD card, ESP32 (spare, unused).

**Away right now:** the **Arduino Uno** — step 7 waits for it.

**Still needed:** 18650 charger, 5 V 3 A power bank (the 3000 mAh 2.1 A one is too weak for the robot), M3 standoffs, camera mount.

> **Never use all four 18650s in series.** 4 cells = 14.8 V (16.8 V charged), and the TB6612 chip's limit is 15 V. Two cells, 7.4 V — that's what `MAX_PWM = 200` in the Uno sketch is calculated for.

## Things to know

- **Camera number:** `1` on the laptop, `0` on the Pi (`--camera`).
- **The Pi:** `followbot.local`, or the address `hostname -I` prints (was 192.168.1.19). Dashboard on port 8000.
- **The repository is private**, so the Pi needs a read-only token to `git pull`.
- **Face models aren't on GitHub** (`.gitignore`) — `deploy/setup_pi.sh` downloads them, or see `pi/models/README.md`.
- **Face fingerprints are never saved to disk**; they only exist while the program runs.
- **The robot starts on boot now.** It holds the webcam and port 8000, so `sudo systemctl stop followbot` before running `pi/follow.py` by hand. Live log: `journalctl -u followbot -f`. Drop the `--dry` in `/etc/default/followbot` once the Uno is connected.
- **iPad / iPhone can't show the video stream.** Safari refuses MJPEG, so the page falls back on its own to single pictures ~8×/s from `/frame.jpg` and shows `· STILLS` in the feed header. That is normal, not a fault. Chrome on a laptop gets the smooth stream.
- **Dim rooms halve the frame rate** (10–12 fps instead of ~20), which is the main thing making a follower wobble. Light the demo room.
- **The Pi boots into hotspot mode now**, so it has **no internet** and cannot `git pull`. To update its code: `sudo bash deploy/hotspot.sh boot-off` → `sudo reboot` → pull on home WiFi → `boot-on` → reboot.
- **The Pi's clone still has the pre-rewrite history** (the Claude attribution was stripped and force-pushed). Its first update must be `git fetch origin && git reset --hard origin/main`, not `git pull`.
- **Home WiFi is saved on the Pi as `HollyMax0306`** — no `_5G`. Useful if you ever need a phone hotspot to impersonate it so the Pi joins automatically.
- **Locked out with no network?** Micro-HDMI (the port **nearest the USB-C socket**) to any TV, plus a USB keyboard, gives a console login. From there `sudo bash deploy/hotspot.sh on` works immediately — no reboot, no SSH to lose. Plug the screen in **before** powering up; a Pi ignores a display connected after boot.
- **The hotspot password is still the default `followbot2026`.** Change it before the demo: `sudo nmcli connection modify followbot-ap wifi-sec.psk 'your-password'` then `sudo nmcli connection up followbot-ap`.

## Next

**Blocked until the Uno is back:**

1. **Step 7 — upload and bench test.** Arduino IDE → upload `uno/motor_controller/` → Serial Monitor at 115200, line ending *Newline*, **wheels off the ground** → type `t`. It runs each wheel on its own and announces it. A wheel turning the wrong way = flip `FWD_L` or `FWD_R` in the sketch. Then remove `--dry` from `/etc/default/followbot`.

**Can be done any time (no Uno needed):**

2. **Try the tricks in the simulator** (`steps/04b_simulator.py`, keys 1–4). Written and tested, but the user hasn't watched them yet. If the dance feels too slow or twitchy, `BEAT` in `pi/moves.py` is the one number that sets the rhythm.
3. **The all-in-one web page** — fold the HSV tuner and the top-view simulator into the dashboard. The user picked this as the next task. Pure code, no hardware.
4. **Step 9 — assemble:** mount the camera ~20 cm up, tilted ~30°.
5. **Step 10 — calibrate** the distance bands and `KP` on the floor, then re-tune HSV in the demo room. A **distance bar** overlay (resume / stop / back-up bands with a marker) was offered for this step — add it then.

## Ideas parked for later

- **One local web page for everything:** the dashboard plus HSV tuning and the simulator as a control panel.
- **Follow your body** once your face is found, so it can follow you when you turn away.
- **Brighten dark faces** (CLAHE) if the demo room's ceiling lights make faces hard to detect.
- **Lock the webcam's frame rate** so dim light doesn't drop it to 12 fps (`v4l2-ctl --list-ctrls`, look for `exposure_dynamic_framerate`).
- **Obstacle stop** with the HC-SR04, and a **tilt servo** for the camera.
