# Where the project stands

Updated 25 September 2026. Short status of the build: what works, what's measured, what's left.

## Done

| Step | Result |
|---|---|
| 1–3 | Live camera feed, color detection (yellow), HSV tuner (`tools/hsv_tune.py`) |
| 4 | Decision logic in `pi/brain.py`: follow / hold / back up with hysteresis, proportional steering, searching when lost |
| 4b | Top-view simulator (`steps/04b_simulator.py`): drag yourself and a stranger, watch the robot decide |
| 5 | Face detection (YuNet) with two modes: **Simple** (biggest face) and **Smart** (locks onto you, recognizes you with SFace, ignores strangers) |
| 6 | The robot program `pi/follow.py` + phone dashboard (`pi/web.py`): color / face / manual, Start-STOP, joystick, tap-your-face. Verified on the laptop and on the Pi, viewed from a phone. |
| 6b | Dashboard redesigned in the SentryCore style (glass panels, the page tints itself with the robot's state, animated background). Plain CSS, no CDN, so it still looks right on the robot's own hotspot. |
| 7 | **Uno done.** Sketch uploaded and bench-tested with the `t` routine: all six steps matched their labels, so `FWD_L`/`FWD_R` are correct and left/right are not swapped. Typed commands (`50 0`, `0 50`) drive the wheels. |
| Driving | **The Pi drives the motors for real.** Uno on `/dev/ttyUSB0` (CH340 clone board), `--dry` removed from `/etc/default/followbot`. First drive was good. |
| Smooth driving | **Driving is continuous again; only turning pauses** (`PULSE_DRIVE = False`). Rotation is what smears the picture - driving straight barely does - so the pauses were only ever needed for turning. `SPEED_FWD` 30 -> 18, which is about 8 cm/s continuously, close to what the pulsed version actually achieved but smooth. Still parks at height 180 from every starting distance. |
| No blind movement | **The overshoot after a small turn was my own fix from earlier the same day.** When the face is lost for a frame or two, `LOST_GRACE` used to repeat the last command. I had already stopped it repeating *forward* (it walked into the user) but deliberately left *turning*, reasoning that turning blind is harmless. It is not: the robot's own turn blurs the picture, the blur loses the face, and it then keeps turning on a view it no longer has - 5 frames at 12 fps is another 30 degrees. Reproduced in simulation: 11.8 degrees past centre, ending on the wrong side. **The rule is now simply: if it cannot see, it does not move.** Same test after: settles without ever crossing centre. |
| Waiting | **It no longer bolts into a search the moment it loses you.** Losing the face usually means you turned your head or the picture blurred, not that you walked off - so it now stands still and watches for **3 seconds** (`WAIT_BEFORE_SEARCH`) before sweeping. Order is: 5 frames keeping the last turn, then 3 s motionless, then the search. Reappearing during the wait picks straight back up. |
| Turning power | **Turning has its own PWM range now** (`MIN_PWM_TURN` 65, `MAX_PWM_TURN` 95), separate from driving's 70-140. Sharing one range was why it snapped: the floor that lets it drive was also the slowest it could ever pivot. Only applies when turning on the spot - a curve while driving is gentle anyway, because the two wheels simply run at slightly different speeds. The sketch also gained a **`c` calibration sweep**: it creeps the PWM up in steps of 5, announcing each, so the real floor can be read off instead of guessed. Run it with the wheels ON the floor. |
| Steering by time | **It snapped round whenever the user stepped aside.** The cause is the Uno's PWM floor: with `MIN_PWM 70`, a turn command of 5 and of 25 come out at nearly the same wheel speed, so proportional steering was effectively on/off and every correction was the same 18 degree snap. The robot now steers by **how long** it turns rather than how hard: a nudge from `TURN_ON_MIN` 0.06 s up to `TURN_ON_MAX` 0.20 s depending on the error. Swing per step is now 1.7 deg for a small correction and 11.7 deg for a big one, and it lines up on someone 35 deg off in 1.5 s. `TURN_MAX` also 25 -> 20. |
| Height measure | **Distance is now judged by where the face sits in the picture, not how wide it is** (the user's idea). Width shrinks when you turn your head, and the robot read that as you stepping back and crept forward - which is why it kept closing in no matter how the bands were set. Vertical position does not move when you turn. `MEASURE` in `brain.py` switches between the two; both produce a number that grows as you approach, so the follow/hold/back logic is unchanged. The live view draws the three thresholds as horizontal lines, with **park here on the centre line of the frame**. Thresholds (145, 180, 225) are still rough - read the `height` number off the live view when standing where it should park, and set the middle one to that. |
| Calibrated | **The distance estimate was 24% too far, which is why it kept driving into the user.** Measured on 25 Sep: the bar read `w=66` at a tape-measured 30 inches, so w x distance = 50.3. The code assumed 62.4 (`FOCAL 416 x FACE_WIDTH_M 0.15`), so every reading was inflated - aiming for '0.80 m' actually drove to 0.64 m. `FACE_WIDTH_M` is now **0.12**, the measured width of a face as YuNet draws the box (not ear to ear). Bands re-anchored in the user's own units: **follows past 34 in, parks at 30 in, backs off under 25 in**. Verified it parks at 30 inches from every starting distance between 14 and 60 inches, and then stays put. |
| Tuning 5 | **The ring.** The user drew what they wanted: one circle it settles on, mirroring them - step in and it backs off, step out and it follows. Ring moved from 0.55 m out to **0.80 m** (follows past 0.90, backs off under 0.70), and the no-reaction band tightened from 30 cm to **20 cm** so it actually responds. The tighter band is safe now because each move step only covers 3.4 cm. Simulated from five starting distances: settles at 0.79-0.80 m every time, with zero state changes afterwards. |
| Tuning 4 | **Fixed the robot creeping into you.** It drove forward, the movement blurred the picture, detection failed, and `LOST_GRACE` repeated the last command - which was 'drive forward'. So it advanced blind, and a single flickering detection reset the grace and let it do it again. Now the grace keeps the **turn** but zeroes the **forward**: turning blind is harmless, driving blind is how a follower walks into someone. The pulse also applies to driving now, not just turning, so the camera gets a sharp look between steps - 0.25 s moving, 0.22 s still (2.6 frames at 12 fps), about 7 cm/s. Simulated with detection failing on every moving frame: it now settles at 0.55 m instead of pushing through to 0.52 m. |
| Tuning 3 | The Uno was the reason it lurched: `MIN_PWM` meant even `fwd 25` became PWM 117 applied instantly. Now `MIN_PWM` 90 -> 70, `MAX_PWM` 200 -> 140 (~4 V instead of 5.8 V), and the sketch **ramps**: gently up (`RAMP_UP` 180/s, so a standing start takes 0.14 s) but quickly down (`RAMP_DOWN` 700/s). Asymmetric on purpose - braking never feels like a lurch, and a slow wind-down would eat the camera's look-pauses, leaving 1 sharp frame per turn burst instead of 2. The 500 ms failsafe still stops dead with no ramp. |
| Tuning 2 | Closer and much gentler, after watching it on a table: holds at **0.55 m** (follows past 0.75, backs off under 0.45), `SPEED_FWD` 35 -> 25, `KP` 60 -> 35, `TURN_MAX` 60 -> 25, and **turning now happens in bursts** (`PULSE_ON` 0.15 s on, `PULSE_OFF` 0.25 s off) because the Uno's MIN_PWM floor means a small turn number cannot make the motors rotate slowly. Effective turn rate 35 deg/s instead of 220, with 56% of frames taken standing still. A **distance bar** on the live view shows the three bands and where you are, for re-measuring. |
| Tuning | After that first drive: both modes now hold at **0.65 m** (follow past 0.9 m, back off under 0.5 m), `SPEED_FWD` 50 -> 35, and searching changed from a continuous 92 deg/s spin to **turn 0.3 s, stand still 0.4 s and look** - half the frames are now taken while stationary, which is what the detector needs at 10 fps. |
| 11a | **Autostart works.** `deploy/install_service.sh` installed on the Pi; it boots, runs `follow.py` and serves the dashboard with no laptop. Options live in `/etc/default/followbot` (now empty - it drives the motors for real). |
| 11b | **Hotspot works, tested away from home.** The Pi broadcasts **FollowBot**; laptop and iPad join it and open `http://10.42.0.1:8000`, SSH at `myke@10.42.0.1`. Profile is `followbot-ap`, `autoconnect yes`, priority 100 — so it starts on every boot, anywhere. **Step 11 is done.** |
| Joystick | **Manual driving got precise.** Four changes, all in the page - nothing to reflash. **Grab, don't jump:** touching the pad is no longer a command; the robot moves by how far your thumb travels *since* it landed. Tapping near the rim used to mean instant near-full speed. **12% dead zone**, with the knob greying out so you can see when it is live. **Angular detent:** within 10 deg of an axis the off-axis part is forced to exactly 0, so a dead straight line or a clean pivot is easy to hold - and it eases back out smoothly rather than jumping (a plain cut-off would have stepped 19 units the moment you left it). **Expo** (`0.25s + 0.75s³`), so most of the stick travel is spent on the slow end where the resolution is needed, with a small `CRAWL` floor so leaving the dead zone always does *something*. Verified against real pointer events in the browser: a grab at the rim now reads `FWD 0 · TURN 0`. |
| Tricks | `pi/moves.py`: spin, dance, nod, shake. Buttons on the dashboard, keys 1-4 in the simulator. Only play while running; STOP cancels. **`TEMPO` is now the single knob for their pace** - at 1.15 every trick is 15% quicker than it was written. Spin is the exception that proves the rule: it cannot just stop sooner or it would end up facing the wrong way, so TEMPO spins it *harder* (`SPIN_TURN` 60 -> 69) and it finishes in 1.59 s instead of 1.80 s, still turning a verified 360 deg. Dance, shake and nod all end facing where they started, with zero net drift. |
| Gestures | **Hand signals work.** `pi/gestures.py` ports the MediaPipe palm + 21-landmark models from the OpenCV Zoo (no new library). Its own dashboard mode, so nothing else competes for frames: point up/left/right to drive, two fingers to reverse, fist to stay put, open palm to STOP. Take your hand away and it stops. ~15 fps on the laptop. |
| Pi setup | Pi 4 with Raspberry Pi OS Lite 64-bit, code cloned from GitHub, `deploy/setup_pi.sh` run, `tools/pi_check.py` passing |

## How it behaves now (after the 25 Sep tuning session)

The eight `Tuning` rows above are the history; this is the summary.

| | |
|---|---|
| **Distance judged by** | Where the face sits in the picture, **not how wide it is** (`MEASURE = "height"`). Width shrank whenever the user turned their head, and the robot read that as them stepping back. |
| **Parks when** | The chin is on the **centre line** of the live view. Three horizontal lines are drawn: follow / park here / too close. |
| **Driving** | Continuous, ~8 cm/s (`SPEED_FWD 18`, `PULSE_DRIVE False`). |
| **Turning** | In short nudges, 0.06–0.20 s depending on how far off-centre — because the Uno's PWM floor makes turning *gently* impossible, so it turns *briefly* instead. Pivots have their own power range (65–95, vs 70–140 for driving). |
| **When it loses you** | Stands still. 5 frames, then 3 s of waiting and watching, then it sweeps. **It never moves while it cannot see** — that rule killed two separate bugs (walking into the user, and swinging past them). |
| **Uno** | Soft ramp into every change: gentle up (180/s), quick down (700/s). The 500 ms failsafe still stops dead. |

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

**Have:** Raspberry Pi 4, USB webcam, **Arduino Uno** (back, sketch uploaded and tested), LAFVIN TB6612 motor shield, 2 motors with wheels **mounted on the chassis**, 4× 18650 cells in **two 2-slot holders** (7.4 V each — one runs the robot, one is a spare), 16 GB SD card, ESP32 (spare, unused).

**Still needed:** 18650 charger, 5 V 3 A power bank (the 3000 mAh 2.1 A one is too weak for the robot), M3 standoffs, camera mount.

> **Never use all four 18650s in series.** 4 cells = 14.8 V (16.8 V charged), and the TB6612 chip's limit is 15 V. Two cells, 7.4 V — that's what `MAX_PWM = 200` in the Uno sketch is calculated for.

## Things to know

- **Camera number:** `0` on both now — the user set `CAMERA = 0` in steps 05 and 07. It used to be `1` on the laptop, so if a step script shows the wrong camera, that is the one line to change.
- **The Pi:** `followbot.local`, or the address `hostname -I` prints (was 192.168.1.19). Dashboard on port 8000.
- **The repository is private**, so the Pi needs a read-only token to `git pull`.
- **Face models aren't on GitHub** (`.gitignore`) — `deploy/setup_pi.sh` downloads them, or see `pi/models/README.md`.
- **Face fingerprints are never saved to disk**; they only exist while the program runs.
- **The robot starts on boot now.** It holds the webcam and port 8000, so `sudo systemctl stop followbot` before running `pi/follow.py` by hand. Live log: `journalctl -u followbot -f`.
- **iPad / iPhone can't show the video stream.** Safari refuses MJPEG, so the page falls back on its own to single pictures ~8×/s from `/frame.jpg` and shows `· STILLS` in the feed header. That is normal, not a fault. Chrome on a laptop gets the smooth stream.
- **The webcam's own limits** (from `v4l2-ctl --list-ctrls` / `--list-formats-ext`, 24 Sep):
  - **No zoom control at all**, and every mode is 4:3 (640x480 down to 160x120). So the "slight zoom" is simply the lens - a narrower field of view than the ~60 deg the maths assumed. It cannot be switched off; `FOCAL` in `vision.py` has to be measured instead.
  - **No MJPG - YUYV only.** The MJPG request in `Camera` has always been a no-op on this camera.
  - **It can do 30 fps at 640x480.** It doesn't, because `auto_exposure` is on "Aperture Priority" and the camera lengthens its exposure in dim light instead. Try `v4l2-ctl -d /dev/video0 -c auto_exposure=1`, then check whether `exposure_time_absolute` appears and set it.
  - `power_line_frequency` is already 60 Hz, correct for the Philippines.
- **The camera is the bottleneck, not the Pi** (`pi_check.py`, 24 Sep): face detection takes 41.7 ms, so the Pi could run at **23 fps** in face mode - but the webcam only delivers **12 fps**, even after forcing 30 with `v4l2-ctl -p 30` and switching to manual exposure (which this driver allows but gives no `exposure_time_absolute` to set). The cause is bandwidth: YUYV has no compression, and 640x480x30 is 18.4 MB/s over USB. **Next things to try: a blue USB 3 port, and `tools/camera_speed.py` to see what a smaller capture size delivers.**
- **Dim rooms halve the frame rate** (10–12 fps instead of ~20), which is the main thing making a follower wobble. Light the demo room.
- **Hotspot vs home WiFi.** The Pi is back on home WiFi for now (`followbot.local`), with the hotspot profile saved but not auto-starting. Turn it back on before going out: `sudo nmcli connection modify followbot-ap connection.autoconnect yes` then reboot; `no` to come back. **On the hotspot it has no internet, so `git pull` only works on home WiFi** (or plug an Ethernet cable into the router, which keeps both).
- **The Pi's clone still has the pre-rewrite history** (the Claude attribution was stripped and force-pushed). Its first update must be `git fetch origin && git reset --hard origin/main`, not `git pull`.
- **Home WiFi is saved on the Pi as `HollyMax0306`** — no `_5G`. Useful if you ever need a phone hotspot to impersonate it so the Pi joins automatically.
- **Locked out with no network?** Micro-HDMI (the port **nearest the USB-C socket**) to any TV, plus a USB keyboard, gives a console login. From there `sudo bash deploy/hotspot.sh on` works immediately — no reboot, no SSH to lose. Plug the screen in **before** powering up; a Pi ignores a display connected after boot.
- **The hotspot password is still the default `followbot2026`.** Change it before the demo: `sudo nmcli connection modify followbot-ap wifi-sec.psk 'your-password'` then `sudo nmcli connection up followbot-ap`.

## Next

1. **Run the `c` sweep on the Uno, wheels ON the floor.** Serial Monitor at 115200, line ending Newline, type `c`. It creeps the power up in steps of 5 and announces each one, so you can read off the slowest PWM that actually moves the robot - driving first, then pivoting on the spot. **Every PWM number in that sketch is still a guess** (`MIN_PWM 70` / `MAX_PWM 140`, `MIN_PWM_TURN 65` / `MAX_PWM_TURN 95`), and those guesses are exactly what forced the steer-by-time workaround. Measure the real floors and some of that complexity can come back out.
2. **Fine-tune where it parks.** Stand where you want it to stop, read the `height` number off the live view, and put that in the **middle** slot of `_BANDS_HEIGHT` in `pi/brain.py` (`"face": (140, 180, 230)` today). The outer two are the follow and back-off thresholds: spread them wider if it fusses over nothing, tighter if it reacts too late. This is the one calibration that matters, and **it has to be redone after the camera is mounted** - the number is a position in the picture, so it moves when the camera does.
3. **Chase the frame rate.** The camera delivers **12 fps while the Pi could run 23**, so it sits idle half the time - and nearly every problem this project has had traces back to acting on a picture that was already stale. Try a **blue USB 3 port** first, then `tools/camera_speed.py` (stop the service first) to see what a smaller capture size really delivers. Put the winner in `CAPTURE` in `pi/vision.py`.
4. **Try gesture mode on the Pi.** It runs at ~15 fps on the laptop (`.venv/Scripts/python steps/07_hand_gesture.py`, no robot needed). On the robot, check left and right feel the right way round - if pointing left sends it right, set `POINT_FLIP = True` in `pi/gestures.py`. Speeds are `GESTURE_FWD` / `GESTURE_TURN` / `GESTURE_BACK` in the same file.
5. **Watch the tricks in the simulator** (`steps/04b_simulator.py`, keys 1-4). Written and timing-checked against the motion model, but nobody has actually looked at them. If the dance feels slow or twitchy, `BEAT` in `pi/moves.py` is the one number that sets the rhythm.
6. **Step 9 - mount the camera. The height matters.** At 20 cm up and tilted 30 deg, the frame covers only 0.30-1.19 m above the floor at the distance it now parks at - hip height, so a standing person's face is out of shot entirely. **About 48 cm up and tilted 45 deg** covers 0.80-2.31 m there, which works for a standing adult all the way in. (Sitting at a desk the low mount is fine, which is why close testing works today.) Two things follow from mounting it: redo item 2, and note that judging distance by height is **person-specific** - a taller person's chin sits higher in the frame, so the robot parks further away from them. If that matters for the demo, calibrate for whoever will be standing in front of it.
7. **Step 10 - calibrate in the demo room itself.** Re-tune HSV where the demo will happen (`tools/hsv_tune.py`), and redo item 2 under that room's lighting. Light level changes the frame rate, and the frame rate changes how the robot behaves - so a calibration done in a bright room is not the one you want in a dim hall.
8. **The all-in-one web page** - fold the HSV tuner and the top-view simulator into the dashboard. Pure code, no hardware needed; the user picked this as the next thing to build.

## Ideas parked for later

- **Gestures: only obey the person Smart mode knows** — today gesture mode obeys the nearest hand, whoever it belongs to. Verifying identity needs face detection running too, which is what gesture mode deliberately avoids. See [the write-up](hand-gestures.md).
- **[LLM companion](llm-companion.md)** — a local model on the laptop that takes spoken/typed commands, explains the robot's own decisions, and writes new dances. Written up in full; the user liked all six features. Nothing built.
- **Follow your body** once your face is found, so it can follow you when you turn away.
- **Brighten dark faces** (CLAHE) if the demo room's ceiling lights make faces hard to detect.
- **Lock the webcam's frame rate** so dim light doesn't drop it to 12 fps (`v4l2-ctl --list-ctrls`, look for `exposure_dynamic_framerate`).
- **Obstacle stop** with the HC-SR04, and a **tilt servo** for the camera.
