# Color & Face Following Robot — Build Plan

**Architecture:** Raspberry Pi 4 (vision + WiFi dashboard) + Arduino Uno with the LAFVIN TB6612 shield (motor control)
**Drivetrain:** 2WD differential drive + caster
**Control:** phone browser over WiFi — live camera view, mode buttons, joystick, STOP
**Last updated:** September 2026

---

## 1. Concept

A two-wheeled robot with a forward-facing webcam. You pick what it does from your phone:

- **Color mode** — finds a hardcoded color, turns to center it, drives toward it, and stops at a set distance.
- **Face mode** — finds a human face, centers on it, and follows at a set distance. Behaves like a dog following you.
- **Manual mode** — you drive it with an on-screen joystick.

The phone page also shows the live camera view with the detection box drawn on it, a **Start** button, and an always-visible **STOP**. The robot boots stopped: nothing moves until someone presses Start.

Distance is estimated from the apparent width of the target in the frame: wide means near, narrow means far.

### Follow / stop / resume behavior

The robot keeps a standoff distance instead of driving until contact:

1. Target far → **advance** toward it.
2. Target reaches the stop distance → **hold** position (it still turns to keep facing the target).
3. Target moves away → **resume** advancing, automatically.
4. Target comes too close → **back up** until it is back at the stop distance.
5. Target lost → keep going for a fraction of a second (detections flicker), then **stop**.

### Distance: three states with hysteresis

A single threshold causes **chattering**: with the target right at the boundary, one frame says "stop", the next says "go", and the robot judders in place. The fix is three states with gaps between the thresholds (`resume < stop < backup`, all target widths in pixels):

| State | Wheels | Leaves for | When |
|---|---|---|---|
| **Follow** | forward | Hold | `w ≥ stop` |
| **Hold** | stopped | Follow | `w ≤ resume` |
| **Back** | reverse | Hold | `w ≤ stop` |
| any | — | Back | `w > backup` |

The target must move clearly farther away before the robot restarts, and once backing up, the robot keeps reversing until it is back at the stop distance — not just barely out of "too close".

### Steering: proportional, not left/right

A 2WD robot centers a target by **rotating**, and rotation swings the target across the frame fast. With a fixed turn speed, the robot is still turning when the "centered" frame finally gets processed (~0.1 s later), overshoots, turns back, and wobbles. So the turn rate is **proportional to how far off-center the target is**: big error, fast turn; small error, gentle turn; tiny error, no turn. The frame (480 px wide) is split into zones:

```
x:  0           120           210        270           360         480
    |  spin in  |    curve    | straight |    curve    |  spin in  |
    |  place    |  toward it  |  ahead   |  toward it  |  place    |
```

Far off-center it spins in place first (centering beats distance); nearly centered it curves toward the target while driving.

---

## 2. System Architecture

```
                     phone / laptop browser
           live view · Color/Face/Manual · Start · STOP · joystick
                               ▲
                               │ WiFi (home network, or the robot's own hotspot)
                               ▼
Webcam ──USB──► Raspberry Pi 4 ──USB serial──► Arduino Uno ══ LAFVIN TB6612 shield ──► 2 motors
                vision, decisions,  "fwd turn\n"   mixing, PWM,     (stacked on the Uno)
                web dashboard       every frame    failsafe
```

### Division of labor

| Component | Role | Responsibility |
|---|---|---|
| Webcam | Eye | Supplies frames. No processing. |
| Raspberry Pi 4 | Brain | Capture, detection, steering decisions, web dashboard, WiFi. Python + OpenCV + Flask. |
| Phone / laptop | Remote | A browser. Nothing to install. |
| Arduino Uno | Hands | Parses `fwd turn`, mixes it into left/right wheel speeds, drives PWM, runs the failsafe. No idea what a camera is. |
| LAFVIN TB6612 shield | Power stage | Switches battery current to the motors. Also carries the battery socket, ON/OFF switch and 5 V regulator. |
| ESP32 | — | Not used. Spare. |

### Why the Uno and not the ESP32

- **The shield is made for the Uno.** It plugs on — zero wiring.
- **Logic levels.** The TB6612 on the shield runs at 5 V and needs at least 0.7 × 5 V = **3.5 V** to see a HIGH. The Uno outputs 5 V; the ESP32 outputs 3.3 V — below spec without a level shifter.
- **WiFi already lives on the Pi**, next to the camera and the decisions. The ESP32's WiFi would have nothing to do.

### Command protocol (Pi → Uno)

One text line per camera frame over USB serial, 115200 baud:

```
<fwd> <turn>\n        each an integer from -100 to 100 (percent of full speed)
```

`fwd` > 0 drives forward, < 0 reverses. `turn` > 0 rotates right (clockwise seen from above), < 0 rotates left.

| Line | Meaning |
|---|---|
| `50 0` | Forward, half speed |
| `-40 0` | Reverse |
| `0 30` | Spin right in place |
| `0 -30` | Spin left in place |
| `45 15` | Curve right while advancing |
| `0 0` | Stop |

The Uno does the rest:

- **Mixing:** `left = fwd + turn`, `right = fwd − turn`. If either exceeds 100, both are scaled down together so the curve keeps its shape.
- **Deadband:** any non-zero value maps into `MIN_PWM…MAX_PWM`, so small commands still move the wheels (gear motors don't turn at all below a certain PWM).
- **Failsafe:** no valid line for 500 ms → stop. Since the Pi sends every frame, the command stream doubles as a heartbeat.

The Pi sends **intent** (forward speed + turn rate), not wheel speeds. Only the Uno sketch knows the robot has two wheels, and you can test the Uno by typing lines into the Arduino Serial Monitor.

### Control loop (one frame)

1. Grab the newest frame, 480×360.
2. **Stopped** → send `0 0`. **Manual** → send the joystick's `fwd turn` (`0 0` if the phone has been quiet for 0.5 s).
3. **Color / Face** → detect the target → center `x` and width `w`.
4. No target → repeat the last command for a few frames, then send `0 0` and re-arm Follow.
5. Update the distance state from `w` → `fwd` = +`SPEED_FWD` / 0 / −`SPEED_BACK`.
6. `err = x − 240`. Inside the dead zone `turn = 0`, otherwise `turn = KP × err / 240` (clamped).
7. If `|err| > ALIGN_ZONE`, set `fwd = 0` — center first.
8. Send the line; update the status and live view. Repeat 15–30× per second.

### Safety layers

| Layer | Stops the robot when… |
|---|---|
| Boots stopped | …it powers on. Someone must press Start. |
| STOP button (+ optional physical button) | …you press it. |
| Manual deadman | …the phone sends no joystick update for 0.5 s (screen locked, WiFi dropped). |
| Target lost | …the target has been gone for LOST_GRACE frames (0.2–0.3 s). |
| Uno failsafe | …no command arrives for 0.5 s (Python crash, cable pulled, Pi rebooting). |
| Shield power switch | …you flip it. Motors lose power; the Pi, Uno and page keep running. |

---

## 3. Bill of Materials

Prices are Philippine pesos, carried over as estimates from the previous version of this plan (September 2026) — confirm before ordering. Circuitrocks and Makerlab stock most of these.

### 3.1 Already have

| Item | Role | Notes |
|---|---|---|
| Raspberry Pi 4 Model B | Brain | Any RAM size works. |
| Arduino Uno R3 (LAFVIN kit board) | Motor controller | |
| LAFVIN TB6612FNG expansion shield | Motor driver | From the LAFVIN 2WD Smart Robot Car Kit V2.2. Has battery socket, ON/OFF switch, 5 V regulator. |
| 2 × DC gear motors with wheels | Drive | TT-style 3–6 V yellow gear motors. If yours are different, check their voltage before setting `MAX_PWM`. |
| USB webcam | Eye | Must be UVC (almost all are). |
| ESP32 | Spare | Not used in this design. |

### 3.2 Still need — required

Skip anything you already have.

| Item | Qty | Est. Price | Notes |
|---|---|---|---|
| microSD card 32 GB, A1/A2 rated | 1 | ₱300–500 | A-rated cards install and boot noticeably faster. |
| Power bank, 5 V **3 A**, 10 000 mAh+ | 1 | ₱600–1,200 | **For the Pi only.** Weak banks cause undervoltage warnings and random reboots. |
| USB-C cable, short and thick | 1 | ₱100–150 | Power bank → Pi. Thin cables drop voltage. |
| Heatsink + fan kit for Pi 4 | 1 | ₱150–300 | **Not optional.** Vision + streaming keep the CPU busy; without cooling it throttles silently. |
| USB cable for the Uno (usually USB-A to USB-B, the "printer" type) | 1 | ₱80–150 | Pi → Uno. Probably came with the kit. Must be a data cable, not charge-only. |
| 2WD chassis kit (plate, caster, motor brackets, screws) | 1 | ₱350–600 | Usually includes 2 more motors + wheels — free spares. DIY option: plywood/acrylic plate + ball caster (₱50–100) + brackets. |
| 18650 Li-ion cells | 2 | ₱150–300 ea | **For the motors only.** 2 in series = 7.4 V nominal, 8.4 V full. Buy from a reputable seller — fake "9900 mAh" cells are common. |
| 2×18650 series holder with a 2-pin plug | 1 | ₱50–100 | The plug must fit the shield's **BAT** socket (white 2-pin, same type as the motor sockets — JST-XH 2.54 mm style). **Match polarity:** + to **VS**, − to **GND**, as printed on the shield. |
| 18650 charger | 1 | ₱100–250 | Charges each cell separately. Don't charge the cells in series inside the holder. |
| M3 nylon standoffs + screws | 1 set | ₱100–150 | To stack the Pi above the chassis. |
| Camera mount | 1 | ₱0–100 | Anything that holds the webcam ~20 cm up, tilted ~30° up: small bracket, 3D print, or a glued wedge (see 4.4). |
| Zip ties + double-sided foam tape | 1 each | ~₱110 | A tidy robot is a debuggable robot. |

### 3.3 Recommended small parts

| Item | Qty | Est. Price | Purpose |
|---|---|---|---|
| **0.1 µF (100 nF) ceramic capacitor** | 2–4 | ₱5 ea | One across each motor's terminals, soldered at the motor (skip if your motors already have one). Motor brushes spray electrical noise that can reset the Uno or drop the USB link — the most commonly skipped part and the source of the most baffling bugs. |
| **470–1000 µF electrolytic, 16 V+** | 1 | ₱20–30 | Across the battery leads close to the shield. Absorbs the surge when the motors start. Mind the polarity stripe. |
| **Inline fuse holder + 3 A slow-blow fuse** | 1 | ₱50–80 | Between battery + and the shield. 18650s can push 10 A+ into a short — this is what stops a melted wire. |
| Heat shrink + electrical tape | — | ₱110–150 | |

### 3.4 Optional upgrades

| Item | Est. Price | What it adds |
|---|---|---|
| SG90 micro servo + small tilt bracket | ₱170–280 | Tilts the camera per mode — up for faces, down for a floor-level target (fixes the conflict in 4.4). Plugs straight into the shield's **D10** servo header. The protocol grows a third number (tilt angle). |
| HC-SR04 ultrasonic sensor | ₱80–150 | Obstacle stop. Plugs into the shield's ultrasonic socket (P1: trig D12, echo D13). The Uno can refuse to drive forward when something is closer than ~20 cm — a safety net that works even if the Pi misbehaves. |
| Pushbutton + 2 jumper wires | ₱10–20 | Backup Start/Stop on the Pi (GPIO17 → button → GND), in case WiFi fails at the demo. Already supported in the code. |

### 3.5 Tools

| Item | Notes |
|---|---|
| **Multimeter** | Essential. Check battery polarity before the first plug-in. Most wiring bugs take 30 seconds to find with one and 3 hours without. |
| Soldering iron + solder | Motor capacitors, battery leads. |
| Wire stripper / cutter | |
| Small Phillips screwdrivers | |
| Hot glue gun | Strain relief and quick mounting. |

### 3.6 Demo targets

| Item | Notes |
|---|---|
| Bright neon green or orange object, 15–20 cm across | A ball, a card on a stick, or a neon vest — **held or worn at chest height** (see 4.4). Bigger is detectable from farther. **Avoid red**: skin, wood and clothing trigger false positives constantly. |
| Colored cardstock | Backup target, and handy for HSV tuning. |

### Estimated cost

| Scenario | Cost |
|---|---|
| Required items (3.2) | **₱2,250–4,200** |
| …if you already own a power bank, a microSD card and both cables | **₱1,150–2,200** |
| Recommended small parts (3.3) | +₱200–300 |
| Optional upgrades (3.4) | +₱250–450 |

---

## 4. Wiring & Assembly

### 4.1 Motor side: stack the shield

1. **Plug the shield onto the Uno.** Check every pin lands in its socket — none bent, none hanging outside.
2. **Motors:** left motor → socket **A1**, right motor → socket **B1**. (In LAFVIN's own code channel A is the left motor.) A2/B2 are second sockets on the same channels for the 4WD version — leave them empty.
3. **Battery:** holder plug → **BAT** socket. Check polarity with the multimeter first: + goes to **VS**.
4. **Leave the Bluetooth socket (P2) empty.** It shares pins D0/D1 with the USB serial link to the Pi; a module there garbles commands and blocks uploads.
5. **Uno USB → Pi USB.** That is the command link, and it powers the Uno.

The shield's pin mapping is fixed by the PCB:

| Uno pin | Shield signal | Function |
|---|---|---|
| D2 | DIRA | Left motor direction |
| D5 | PWMA | Left motor speed (PWM) |
| D4 | DIRB | Right motor direction |
| D6 | PWMB | Right motor speed (PWM) |
| D10 | Servo header | Optional tilt servo |
| D12 / D13 | P1 ultrasonic socket | Optional HC-SR04 |
| D0 / D1 | P2 Bluetooth socket | **Leave empty** — used by USB serial |

### 4.2 Power

Two separate supplies. Non-negotiable — sharing one makes the Pi brown out and reboot every time the motors start.

| From | To | Notes |
|---|---|---|
| 2×18650 holder (+) | fuse → shield **BAT VS** | Motors only |
| 2×18650 holder (−) | shield **BAT GND** | |
| Power bank | Pi USB-C | Pi only |
| Pi USB-A | Uno USB-B | Commands + Uno power |
| Pi USB-A | Webcam | |

- **Ground is handled for you.** Uno, shield and battery share ground through the stacked headers, and the Pi joins through the USB cable. No extra ground wires.
- **Use the shield's ON/OFF switch.** With it off, the Pi, Uno and web page keep running while the wheels are dead — the safest way to test anything.
- **Don't power the Pi from the motor battery** (not from the shield's 5 V pins, not through a cheap buck converter).
- **Why `MAX_PWM` is 200, not 255:** the TB6612 loses very little voltage (the L298N in the old plan lost ~2 V). At full PWM the motors would see nearly the whole 7.4–8.4 V pack — above a TT motor's 6 V rating. Capping PWM at 200/255 keeps the average around 6 V.
- **18650 safety:** never short the holder leads, unplug the battery when not in use, charge cells in a proper charger.

### 4.3 Pi connections

| Pi port | Connects to |
|---|---|
| USB-C | Power bank |
| Any USB-A | Webcam |
| Any USB-A | Uno |
| GPIO17 (pin 11) + GND (pin 9) | Optional backup Start/Stop button |

### 4.4 Layout and camera angle

**Stack, bottom to top:** chassis with motors and caster → battery holder, low and near the wheel axle → Uno + shield → standoffs → Pi → webcam at the front, ~20 cm off the floor, tilted ~30° up.

- **Put the heavy parts (battery, power bank) over or near the drive wheels.** Weight on the drive wheels = traction; weight on the caster = skidding turns.
- Route the webcam cable so it can't tug the camera angle.

**What the camera actually sees.** A floor robot looks *up* at people, so two numbers decide whether face mode works: the tilt, and how many pixels a face covers. For a typical ~60° webcam, processing at 480×360:

| Distance | Face (~15 cm wide) | 20 cm color target | Standing adult's face in view? (camera 20 cm up, tilted 30°) |
|---|---|---|---|
| 0.75 m | ~83 px | ~111 px | No — above the frame |
| 1.0 m | ~62 px | ~83 px | Borderline |
| 1.5 m | ~42 px | ~55 px | Yes |
| 2.0 m | ~31 px | ~42 px | Yes |
| 2.5 m | ~25 px | ~33 px | In view, but too small to detect reliably |
| 3.0 m | ~21 px | ~28 px | Face not detected |

Rule of thumb: `w ≈ f × real_width ÷ distance`, where `f ≈ (W/2) ÷ tan(HFOV/2)` ≈ 416 px for a 60° webcam at 480 px wide. The face detector reliably finds faces **≥ ~26 px** wide (measured with a test photo); at 320×240 that would limit face mode to ~1.6 m, which is why this plan processes at 480×360.

What this means:

- **Face mode stops at ~1.5 m** and resumes at ~1.9 m. A standing person closer than ~1 m leaves the top of the frame — the robot treats that as "lost" and stops (safe), so it can only back away from someone crouching or sitting.
- **Color mode: hold or wear the target at chest height.** It stops at ~1.0 m. A ball on the floor is below the frame at this tilt — that is what the optional tilt servo fixes.
- **Ceiling lights behind a face** can make the webcam expose for the lights and leave the face dark. If face detection struggles indoors, reduce the tilt to ~25° and accept a longer standoff.
- **Your webcam's field of view may differ.** The calibration step (7.8) measures your real numbers; use this table to sanity-check them.

### 4.5 Motor noise

- Solder a 0.1 µF capacitor across each motor's terminals, **at the motor**, not on a breadboard — suppress noise at the source.
- Twist each motor's two wires together, and keep them away from the USB cables.
- Symptoms when this is skipped: the Uno resets mid-run (robot stutters, commands stop), or the Pi logs USB disconnects.

---

## 5. Software

### 5.1 Project layout

The project is a Git repository (on GitHub); every folder has a `README.md` explaining what goes in it.

```
Face_Tracking_Bot/
├── README.md                    ← project front page
├── requirements-pc.txt          ← Python packages for the laptop
├── requirements-pi.txt          ← Python packages for the Pi
├── .gitignore / .gitattributes
├── docs/
│   ├── following-robot-plan.md  ← this document
│   └── images/
├── steps/                       ← step-by-step PC scripts: 01_live_feed.py, 02_color_detect.py, …
├── tools/
│   └── hsv_tune.py              ← HSV tuner (runs on a laptop)
├── pi/
│   ├── follow.py                ← main program: camera, vision, control, serial
│   ├── web.py                   ← dashboard server (Flask)
│   ├── templates/index.html     ← phone page
│   └── models/
│       └── face_detection_yunet_2023mar.onnx   ← face model (downloaded, not on GitHub)
├── uno/
│   └── motor_controller/motor_controller.ino
└── deploy/
    └── followbot.service        ← autostart on boot (5.12)
```

### 5.2 Raspberry Pi setup

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In its settings: hostname `followbot`, a username and password, your home WiFi, and SSH enabled. Lite has no desktop — that CPU and RAM go to vision.
2. Boot the Pi, then from your laptop: `ssh <user>@followbot.local`
3. Install the system packages and create the Python environment:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-gpiozero python3-lgpio v4l-utils
python3 -m venv --system-site-packages ~/robot-venv
sudo usermod -aG dialout $USER        # serial port access; log out and back in afterwards
```

4. Get the code from GitHub, install the Python packages, and fetch the face model:

```bash
git clone https://github.com/<your-username>/Face_Tracking_Bot.git ~/Face_Tracking_Bot
cd ~/Face_Tracking_Bot
~/robot-venv/bin/pip install -r requirements-pi.txt
wget -P pi/models https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

After that, getting your latest code onto the robot is `cd ~/Face_Tracking_Bot && git pull`. (A private repo asks for your GitHub username and a personal access token as the password.)

> **Keep OpenCV below 5.** `requirements-pi.txt` pins `opencv-python-headless>=4.8,<5`. A plain `pip install opencv-python-headless` now installs OpenCV 5.0 (released mid-2026), which needs a different face model file (`2026may`). Everything in this plan was tested on OpenCV 4.14 with the `2023mar` model.

5. Check the hardware is seen:

```bash
v4l2-ctl --list-devices                      # webcam listed?
v4l2-ctl -d /dev/video0 --list-formats-ext   # look for MJPG at 640x480
ls /dev/ttyACM* /dev/ttyUSB*                 # Uno: ttyACM0 (original-style) or ttyUSB0 (CH340 clone)
```

### 5.3 Running it

| Where | Command | Then open |
|---|---|---|
| Robot (Pi) | `~/robot-venv/bin/python pi/follow.py` (from `~/Face_Tracking_Bot`) | `http://followbot.local:8000` on your phone — or the Pi's IP (`hostname -I`) if `.local` doesn't resolve (common on Android) |
| Laptop (no robot) | `python -m pip install -r requirements-pc.txt` once, then `python pi/follow.py --dry` | `http://localhost:8000` |
| Robot hotspot (demo) | same as the robot | `http://10.42.0.1:8000` (see 5.13) |

`--dry` skips the Uno, so the whole vision + dashboard side can be built and tested on a laptop with the webcam before the robot exists. `--camera 1` picks another webcam (laptops usually have a built-in one at 0).

### 5.4 Key parameters (top of `follow.py`)

```python
CAPTURE = (640, 480)    # what we ask the webcam for (MJPG)
W, H = 480, 360         # what we process. Faces must be >= ~26 px wide to be found;
                        # at 480 px that reaches ~2.4 m (at 320 px only ~1.6 m).

COLOR = "green"
COLORS = {                                  # HSV lo, hi (OpenCV hue is 0-179)
    "green":  ((40, 100, 80),  (80, 255, 255)),
    "orange": ((10, 150, 100), (25, 255, 255)),
}
MIN_AREA = 300                              # px^2; smaller blobs are noise
KERNEL = np.ones((3, 3), np.uint8)
FACE_MODEL = "models/face_detection_yunet_2023mar.onnx"   # relative to follow.py

# Distance bands per mode: (resume, stop, backup) = target width in px.
# resume < stop < backup. Starting values for a ~60 deg webcam - calibrate them.
BANDS = {
    "color": (64, 83, 104),                 # 20 cm target: ~1.3 m / 1.0 m / 0.8 m
    "face":  (33, 42, 54),                  # face: ~1.9 m / 1.5 m / 1.15 m
}

DEAD_ZONE  = 30     # px either side of center that counts as centered
ALIGN_ZONE = 120    # px; further off-center than this -> turn in place, don't drive
KP         = 60     # turn % when the target is at the edge of the frame
TURN_MAX   = 60     # %
SPEED_FWD  = 50     # %
SPEED_BACK = 40     # %
LOST_GRACE = 5      # frames (0.2-0.3 s) to keep going when the target flickers out

MANUAL_FWD     = 70     # joystick fully up = this % forward
MANUAL_TURN    = 50     # joystick fully sideways = this % turn
MANUAL_TIMEOUT = 0.5    # s without joystick updates -> stop
```

Hue reference (OpenCV scale): orange 10–25 · yellow 25–35 · green 40–80 · blue 100–130 · red 0–10 **and** 170–179 (wraps around, needs two ranges).

Tuning notes:

- **Judders at the stop point** → `resume` too close to `stop`. Widen the gap.
- **Slow to re-follow when you step back** → gap too big. Narrow it (for faces, keep `resume` ≥ ~30 px).
- **Ping-pongs forward/backward** → `backup` too close to `stop`. Push them apart.
- **Wobbles left-right around the target** → `KP` too high or `DEAD_ZONE` too narrow.
- **Turns lazily, stops short of center** → `KP` too low, or `MIN_PWM` on the Uno too low to spin in place.

### 5.5 Control logic

```python
class Follower:
    """Turns (target center x, target width w) into a (fwd, turn) command."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "follow"                   # follow | hold | back
        self.lost = 0
        self.cmd = (0, 0)

    def update(self, target, mode):
        """target = (x, w) in px, or None. Returns (fwd, turn), each -100..100."""
        if target is None:
            self.lost += 1
            if self.lost > LOST_GRACE:          # really gone: stop and re-arm
                self.state, self.cmd = "follow", (0, 0)
            return self.cmd                     # brief flicker: keep going
        self.lost = 0
        x, w = target
        resume_w, stop_w, backup_w = BANDS[mode]

        # Distance: three states with hysteresis
        if w > backup_w:
            self.state = "back"
        elif self.state == "follow" and w >= stop_w:
            self.state = "hold"
        elif self.state == "hold" and w <= resume_w:
            self.state = "follow"
        elif self.state == "back" and w <= stop_w:
            self.state = "hold"
        fwd = {"follow": SPEED_FWD, "hold": 0, "back": -SPEED_BACK}[self.state]

        # Steering: proportional to how far off-center the target is
        err = x - W // 2
        turn = 0
        if abs(err) > DEAD_ZONE:
            turn = round(KP * err / (W / 2))
            turn = max(-TURN_MAX, min(TURN_MAX, turn))
        if abs(err) > ALIGN_ZONE:
            fwd = 0                             # center first, then drive

        self.cmd = (fwd, turn)
        return self.cmd
```

Re-arming to "follow" after a loss is safe: if the target reappears already inside the standoff, the very same update moves it to "hold" before any forward command goes out.

### 5.6 Detection

```python
def find_color(frame):
    """Bounding box (x, y, w, h) of the biggest COLOR blob, or None."""
    lo, hi = COLORS[COLOR]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)       # remove specks
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < MIN_AREA:
        return None
    return cv2.boundingRect(c)


def find_face(detector, frame):
    """Bounding box (x, y, w, h) of the widest (closest) face, or None."""
    _, faces = detector.detect(frame)
    if faces is None:
        return None
    f = max(faces, key=lambda f: f[2])
    return tuple(int(v) for v in f[:4])

# created once at startup:
detector = cv2.FaceDetectorYN.create(model, "", (W, H), score_threshold=0.7)
```

Face detection uses **YuNet**, built into OpenCV: faster and much more accurate than the old Haar cascades, and it handles tilted faces. (Haar with the usual `minSize=(60, 60)` would never see a face beyond ~0.7 m on this robot.)

### 5.7 Camera capture

OpenCV queues frames by default, so lag builds up and the robot chases where you *were*. This class always hands over the newest frame:

```python
class Camera:
    """Grabs frames on a background thread; read() returns only the newest one."""

    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE[1])
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise SystemExit(f"Webcam {index} not found")
        self.frame = None
        self.fresh = threading.Event()
        threading.Thread(target=self._grab, daemon=True).start()

    def _grab(self):
        while True:
            ok, frame = self.cap.read()
            if ok:
                self.frame = frame
                self.fresh.set()
            else:
                time.sleep(0.1)

    def read(self, timeout=1.0):
        """Newest frame at W x H, or None if the camera stalled."""
        if not self.fresh.wait(timeout):
            return None
        self.fresh.clear()
        frame = self.frame
        if frame.shape[:2] != (H, W):
            frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)
        return frame
```

MJPG matters: most webcams default to uncompressed YUYV, which caps them at 5–10 fps over USB.

### 5.8 Uno link and main loop

```python
def open_uno(port=None):
    import serial                               # pyserial
    ports = [port] if port else sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    if not ports:
        raise SystemExit("Uno not found - is the USB cable a data cable?")
    uno = serial.Serial(ports[0], 115200, timeout=0)
    time.sleep(2)                               # opening the port resets the Uno
    return uno


def send(uno, fwd, turn):
    if uno is not None:
        uno.write(f"{fwd} {turn}\n".encode())
```

The heart of `main()` — one pass per frame:

```python
        while True:
            frame = cam.read()
            if frame is None:                   # camera stalled: stop and retry
                send(uno, 0, 0)
                continue
            if shared.mode != mode:             # mode changed on the phone
                mode = shared.mode
                bot.reset()

            box = None
            if mode == "color":
                box = find_color(frame)
            elif mode == "face":
                box = find_face(detector, frame)

            if not shared.running:
                bot.reset()
                fwd, turn = 0, 0
            elif mode == "manual":
                if time.time() - shared.joystick_t < MANUAL_TIMEOUT:
                    jf, jt = shared.joystick
                    fwd, turn = round(jf * MANUAL_FWD / 100), round(jt * MANUAL_TURN / 100)
                else:
                    fwd, turn = 0, 0            # phone went quiet
            else:
                target = None if box is None else (box[0] + box[2] // 2, box[2])
                fwd, turn = bot.update(target, mode)
            send(uno, fwd, turn)
            # ...then: fps + status for the page, and a live-view JPEG if anyone is watching
```

Detection keeps running while the robot is stopped, so the page shows the box and `w` live — that is how you calibrate without the robot moving. The loop prints fps, mode, `w`, state and command once per second (visible over SSH or in the service log).

### 5.9 Web dashboard

`web.py` runs a small Flask server on a background thread inside `follow.py`. The vision loop and the server share one object:

```python
class Shared:
    """State shared between the vision loop and the web server."""

    def __init__(self):
        self.mode = "color"         # color | face | manual
        self.running = False        # boots stopped: nothing moves until Start
        self.joystick = (0, 0)      # last (fwd, turn) from the phone, -100..100
        self.joystick_t = 0.0       # when it arrived
        self.jpeg = None            # newest annotated frame for the live view
        self.viewers = 0            # open live-view streams
        self.status = {}            # state / w / cmd / fps for the page
```

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | The phone page |
| `/stream` | GET | Live view — MJPEG, ~15 fps, 320×240, box and dead zone drawn in |
| `/api/status` | GET | JSON: mode, running, state, w, cmd, fps (the page polls it twice a second) |
| `/api/mode` | POST | `{"mode": "color" \| "face" \| "manual"}` |
| `/api/run` | POST | `{"run": true}` = Start, `{"run": false}` = STOP |
| `/api/drive` | POST | `{"fwd": -100..100, "turn": -100..100}` — joystick, 10× per second while touched |

The live view and the joystick are the interesting routes (`body()` returns the request's JSON as a dict):

```python
    @app.get("/stream")
    def stream():
        def frames():
            shared.viewers += 1
            try:
                while True:
                    jpg = shared.jpeg
                    if jpg is not None:
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    time.sleep(1 / 15)          # ~15 fps is plenty to watch
            finally:
                shared.viewers -= 1
        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.post("/api/drive")
    def drive():
        d = body()
        clamp = lambda v: max(-100, min(100, int(v)))
        shared.joystick = (clamp(d.get("fwd", 0)), clamp(d.get("turn", 0)))
        shared.joystick_t = time.time()
        return "", 204
```

The main loop only JPEG-encodes frames while `viewers > 0`, so the live view costs nothing when nobody is watching.

**The phone page** (`templates/index.html`) has: the live view on top, a status line, Color / Face / Manual buttons, Start and a red STOP, and — in Manual mode — a round joystick pad. Joystick core:

```js
// Joystick: up = forward, sideways = turn. Sent 10x/s while touched;
// the robot stops by itself if updates stop arriving for 0.5 s.
const pad = $("#pad"), knob = $("#knob");
let cmd = null;
function move(e) {
  const r = pad.getBoundingClientRect(), c = v => Math.max(-1, Math.min(1, v));
  const x = c((e.clientX - r.left) / r.width * 2 - 1);
  const y = c((e.clientY - r.top) / r.height * 2 - 1);
  knob.style.left = 80 + x * 80 + "px";
  knob.style.top = 80 + y * 80 + "px";
  cmd = {fwd: Math.round(-y * 100), turn: Math.round(x * 100)};
}
function release() {
  cmd = null;
  knob.style.left = knob.style.top = "80px";
  post("/api/drive", {fwd: 0, turn: 0});
}
pad.onpointerdown = e => { pad.setPointerCapture(e.pointerId); move(e); };
pad.onpointermove = e => { if (pad.hasPointerCapture(e.pointerId)) move(e); };
pad.onpointerup = pad.onpointercancel = release;
setInterval(() => { if (cmd) post("/api/drive", cmd); }, 100);
```

The pad needs `touch-action: none` in its CSS, or the phone scrolls the page instead of driving.

### 5.10 Uno sketch

Board: **Arduino Uno**. Upload from the laptop with the Arduino IDE (Bluetooth socket empty, `follow.py` not running — only one program can hold the port).

```cpp
// Motor controller for the 2WD follower: Arduino Uno + LAFVIN TB6612 shield.
// Reads one line per command from the Pi: "<fwd> <turn>\n", each -100..100.
//   fwd  > 0 forward,     < 0 reverse
//   turn > 0 turn right,  < 0 turn left
// Examples: "50 0" forward, "0 -30" spin left, "0 0" stop.

const int DIR_L = 2, PWM_L = 5;     // shield channel A = left motor  (socket A1)
const int DIR_R = 4, PWM_R = 6;     // shield channel B = right motor (socket B1)

// DIR level that drives each wheel forward. The motors are mirrored, so one
// side is HIGH and the other LOW. Flip one if that wheel runs backwards.
const bool FWD_L = HIGH, FWD_R = LOW;

const int MIN_PWM = 90;             // lowest PWM that still moves the robot (calibrate)
const int MAX_PWM = 200;            // ~6 V average from the 7.4 V pack; TT motors are 3-6 V
const unsigned long TIMEOUT_MS = 500;   // failsafe: stop if the Pi goes quiet

char line[24];
byte len = 0;
unsigned long lastCmd = 0;

// One wheel. v: -100..100. Any non-zero v gets at least MIN_PWM so it really moves.
void motor(int dirPin, int pwmPin, bool fwdLevel, int v) {
  digitalWrite(dirPin, v >= 0 ? fwdLevel : !fwdLevel);
  analogWrite(pwmPin, v == 0 ? 0 : map(abs(v), 1, 100, MIN_PWM, MAX_PWM));
}

void drive(int fwd, int turn) {
  fwd = constrain(fwd, -100, 100);
  turn = constrain(turn, -100, 100);
  int l = fwd + turn, r = fwd - turn;
  int m = max(abs(l), abs(r));
  if (m > 100) {                    // scale both down together so the curve keeps its shape
    l = l * 100 / m;
    r = r * 100 / m;
  }
  motor(DIR_L, PWM_L, FWD_L, l);
  motor(DIR_R, PWM_R, FWD_R, r);
}

void setup() {
  pinMode(DIR_L, OUTPUT); pinMode(PWM_L, OUTPUT);
  pinMode(DIR_R, OUTPUT); pinMode(PWM_R, OUTPUT);
  drive(0, 0);
  Serial.begin(115200);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      line[len] = '\0';
      int fwd, turn;
      if (len > 0 && sscanf(line, "%d %d", &fwd, &turn) == 2) {
        drive(fwd, turn);
        lastCmd = millis();
      }
      len = 0;
    } else if (len < sizeof(line) - 1) {
      line[len++] = c;
    }
  }
  if (millis() - lastCmd > TIMEOUT_MS) drive(0, 0);   // failsafe
}
```

`FWD_L = HIGH, FWD_R = LOW` follows LAFVIN's sample code (forward = DIRA HIGH, DIRB LOW). Your wiring may differ — the bench test (7.1) settles it. **Verify each wheel before trusting the mix:** one reversed motor turns "curve left" into "spin right", and that is nearly impossible to diagnose once everything runs together.

### 5.11 HSV tuner (`tools/hsv_tune.py`, run on a laptop)

```python
"""HSV tuner. Run on a laptop with the robot's webcam:  python tools/hsv_tune.py [camera index]
Drag the sliders until only your target is white in the mask, then press q and copy
the printed numbers into COLORS in follow.py."""
import sys

import cv2
import numpy as np

cap = cv2.VideoCapture(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
cv2.namedWindow("tune")
for name, start, top in [("H lo", 40, 179), ("S lo", 100, 255), ("V lo", 80, 255),
                         ("H hi", 80, 179), ("S hi", 255, 255), ("V hi", 255, 255)]:
    cv2.createTrackbar(name, "tune", start, top, lambda _: None)

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (320, 240))
    t = [cv2.getTrackbarPos(n, "tune") for n in ("H lo", "S lo", "V lo", "H hi", "S hi", "V hi")]
    mask = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), np.array(t[:3]), np.array(t[3:]))
    cv2.imshow("tune", np.hstack([frame, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)]))
    if (cv2.waitKey(1) & 0xFF) == ord("q"):
        print(f'"mycolor": ({tuple(t[:3])}, {tuple(t[3:])}),')
        break
```

Tune with the robot's own webcam, under lighting like the demo room's. Different sensors render the same color differently.

### 5.12 Autostart on boot

So the demo needs no laptop. Save this as `deploy/followbot.service` in the repo (replace `<user>`), then copy it to `/etc/systemd/system/` on the Pi:

```ini
[Unit]
Description=FollowBot vision + dashboard

[Service]
User=<user>
WorkingDirectory=/home/<user>/Face_Tracking_Bot/pi
ExecStart=/home/<user>/robot-venv/bin/python follow.py
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp ~/Face_Tracking_Bot/deploy/followbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now followbot
journalctl -u followbot -f              # live log: fps, mode, w, state, cmd
sudo systemctl stop followbot           # while developing - frees the webcam and the Uno port
```

The robot still boots **stopped** — it waits for Start on the phone.

### 5.13 Demo networking: the robot's own hotspot

School WiFi often blocks device-to-device traffic or needs a login page. Make the Pi its own access point instead (Raspberry Pi OS uses NetworkManager):

```bash
# one-time setup (pick your own password, 8+ characters)
sudo nmcli connection add type wifi ifname wlan0 con-name followbot-ap ssid FollowBot \
    802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
    wifi-sec.psk "choose-a-password" connection.autoconnect no

# demo day: boot straight into the hotspot
sudo nmcli connection modify followbot-ap connection.autoconnect yes connection.autoconnect-priority 100

# afterwards (phone/laptop on FollowBot, ssh <user>@10.42.0.1)
sudo nmcli connection modify followbot-ap connection.autoconnect no
sudo nmcli connection up "<home wifi>"   # name from `nmcli connection show`
```

Phone: join **FollowBot**, open `http://10.42.0.1:8000`. Keep the password — anyone on the robot's WiFi can drive it.

---

## 6. Performance

Latency matters more than raw frame rate: reacting to a 300 ms-old frame at 30 fps is worse than a fresh frame at 15 fps — the robot chases where you *were* and oscillates.

**Already built in:** MJPG capture, newest-frame capture thread with a 1-frame buffer, processing at 480×360, live view encoded only while someone watches (and shrunk to 320×240), no desktop environment.

**What to expect on a Pi 4:**

| Mode | Expected | Limited by |
|---|---|---|
| Color | 25–30 fps | The camera |
| Face | ~13–15 fps | YuNet, ~60 ms per 480×360 frame (OpenCV Zoo measured 6.2 ms at 160×120 on a Pi 4B; the cost scales with pixel count) |

**If face mode is too slow:**

1. Process at `W, H = 400, 300` — ~40 ms per frame, faces still detectable to ~2 m. Recalibrate the bands.
2. Run face detection every 2nd frame and reuse the last box in between.
3. Check for thermal throttling: `vcgencmd get_throttled` should print `throttled=0x0`.

**Measure, don't guess:** fps is printed every second and shown on the page. Above ~15 fps the limit becomes motor response and `KP`/`DEAD_ZONE` tuning, not vision — spend remaining effort there.

---

## 7. Build Sequence

Test each stage alone. Do not skip ahead.

1. **Motors on the bench (laptop + Uno; no Pi yet).** Stack the shield, plug in the motors (A1 left, B1 right) and the battery, **wheels off the ground**. In the sketch set `TIMEOUT_MS = 3000`, upload, open Serial Monitor at 115200 with line ending **Newline**:
   - `40 0` → both wheels roll forward. A wheel runs backwards → flip its `FWD_L` / `FWD_R`.
   - `0 40` → left wheel forward, right wheel back (clockwise spin). Mirrored → the motors are in each other's sockets: swap A1 ↔ B1 and retest.
   - `0 0` stops; so does waiting 3 s (the failsafe). Set `TIMEOUT_MS` back to 500.
2. **Calibrate `MIN_PWM`** (robot on the floor). Temporarily set `MIN_PWM = 0` (and `TIMEOUT_MS = 3000`). Send `0 20`, `0 25`, `0 30`… The first value *N* that really spins the robot in place: set `MIN_PWM ≈ 2 × N` (with `MIN_PWM = 0` and `MAX_PWM = 200`, command *N* ≈ PWM 2*N*). Restore `TIMEOUT_MS`.
3. **Vision on the laptop — no robot needed.** Build it up one script at a time in `steps/` (see `steps/README.md`), then `python pi/follow.py --dry`, open `http://localhost:8000`, move a target around: box follows it, state and `cmd` make sense.
4. **Tune HSV** with `tools/hsv_tune.py`, the robot's webcam, and demo-like lighting.
5. **Pi setup** — flash, SSH, install, clone the repo, fetch the model, confirm webcam and Uno are detected (5.2).
6. **Assemble** — chassis, motors, caster, battery low near the axle, Uno + shield, Pi on standoffs, camera ~20 cm up tilted ~30°. Solder the motor capacitors.
7. **First integrated run, wheels lifted.** Pi ↔ Uno over USB, run `follow.py`, open the page on your phone, press Start, move the target: wheels turn toward it, drive when it's far, stop when it's near.
8. **Calibrate the distance bands.** The robot can stay stopped — the page shows `w` live. Hold the target (or stand, for face mode) where the robot should stop; that `w` is your `stop`. Set `resume ≈ 0.8 × stop` and `backup ≈ 1.25 × stop`. Once per mode. Two minutes here saves an hour of guessing.
9. **Floor test — turning only.** Set `SPEED_FWD = 0`, press Start, stand at the stop distance and step sideways. Raise `KP` until it turns to face you briskly without swinging past; if it wobbles, lower `KP` or widen `DEAD_ZONE`.
10. **Floor test — full follow.** Restore `SPEED_FWD` (start at 35–40). Color mode first, then face mode.
11. **Manual mode and safety checks.** Drive with the joystick. Lock the phone mid-drive → stops within 0.5 s. Press STOP. Pull the Uno's USB cable while driving → stops within 0.5 s.
12. **Autostart + hotspot.** Enable the service (5.12), set up the hotspot (5.13). Reboot test: robot boots stopped, phone joins FollowBot, page loads, Start works.
13. **Optional extras** — tilt servo, ultrasonic stop, backup button.
14. **Rehearse in the demo room.** Re-tune HSV there, check the floor, confirm the hotspot works.

---

## 8. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Nothing moves at all | Shield switch off, battery flat or reversed, sketch not uploaded — or nobody pressed Start. |
| Wheels only twitch when typing in Serial Monitor | Normal: the 500 ms failsafe. Set `TIMEOUT_MS = 3000` for bench tests. |
| Motors hum but don't turn | PWM below the motors' starting point. Raise `MIN_PWM`; charge the battery. |
| One wheel spins backwards | Flip `FWD_L` or `FWD_R` in the sketch. |
| Robot turns *away* from the target | Left and right motors swapped: swap the A1 and B1 plugs, then recheck directions. |
| Wobbles left-right around the target | `KP` too high or `DEAD_ZONE` too narrow. |
| Turns lazily, stops short of center | `KP` too low, or `MIN_PWM` too low to spin in place. |
| Judders at the stop point | `resume` too close to `stop`. Widen the gap. |
| Won't resume following when you step back | `resume` too low — the target never gets that small. Raise it. For faces, also check it's still detected at that distance. |
| Ping-pongs between forward and reverse | `backup` too close to `stop`. |
| Keeps rolling briefly after losing the target | `LOST_GRACE` (0.2–0.3 s) — normal. Lower it if it bothers you. |
| Uno resets / robot stutters when motors start | Motor noise or battery sag: 0.1 µF caps at the motors, 470–1000 µF on the battery input, twisted motor wires, charged cells. |
| Pi reboots randomly, or `vcgencmd get_throttled` ≠ `0x0` | Power bank can't sustain 3 A, cable too thin, or the Pi is overheating. |
| "Uno not found" | Charge-only USB cable, or check `ls /dev/ttyACM* /dev/ttyUSB*`. |
| `Permission denied` on the serial port | `sudo usermod -aG dialout $USER`, then log out and in. |
| Uno ignores commands / sketch won't upload | Something plugged into the Bluetooth socket (P2) — it shares D0/D1. Or `follow.py` is holding the port. |
| Page won't load on the phone | Phone on a different network; try the IP instead of `followbot.local`; is the service running? (`journalctl -u followbot`) |
| Joystick drives in stutters | Phone's updates arriving late (weak WiFi, browser throttling) — the 0.5 s deadman keeps stopping it. Move closer or use the hotspot. |
| Color detection fails in the demo room | HSV tuned under different lighting. Re-tune on site. |
| Face not detected | Too far (face under ~26 px), too close (face above the frame), or backlit by ceiling lights. See 4.4. |
| FPS drops after a few minutes | Thermal throttling. Heatsink + fan; check `vcgencmd get_throttled`. |
| Robot keeps driving after the program stops | Failsafe broken — check `TIMEOUT_MS` in the sketch. |
| Shield chip gets hot | The TB6612 is rated 1.2 A per channel. Stalled wheels (blocked, thick carpet) overheat it; it has thermal shutdown. |

---

## 9. Design Decisions Worth Defending

- **Split brain and hands.** Vision on the Pi, motors on the Uno, one line of text between them. Each side is testable alone: the Uno from a Serial Monitor, the vision on a laptop with `--dry`. The Pi sends *intent* (forward speed, turn rate); only the Uno knows how many wheels there are — the vision code never cares about the drivetrain.
- **The stop lives in hardware.** The Uno stops the motors 0.5 s after the commands stop — a Python crash, a pulled cable or a Pi reboot all end in a stopped robot. A Pi-only design keeps driving.
- **Deterministic motor timing.** PWM from a microcontroller is exact; PWM from a Linux process is subject to scheduler jitter.
- **Uno over ESP32.** The shield plugs onto the Uno and matches its 5 V logic; the ESP32's 3.3 V is below the TB6612's 3.5 V input threshold. WiFi was already on the Pi. Fewer parts, fewer failure points.
- **WiFi on the Pi.** The dashboard needs the camera and the decisions, and both live on the Pi. The robot brings its own hotspot so the demo doesn't depend on the venue's network.
- **Proportional steering.** A 2WD robot centers by rotating; rotation plus camera latency makes fixed-speed turns overshoot. Turn rate proportional to error converges instead of hunting.
- **Three-state distance control with hysteresis.** No judder at the stop point, and backing up restores the standoff instead of stopping at the edge of "too close".
- **Processing at 480×360, measured, not guessed.** The face detector needs faces ≥ ~26 px wide. At 320×240 face mode would give up at ~1.6 m; at 480×360 it reaches ~2.4 m for ~13–15 fps on a Pi 4.
- **Boots stopped.** Nothing moves until a person presses Start.

The honest tradeoff: one more board, a serial protocol to maintain, and a network dependency for control — mitigated by the hotspot, the failsafes, and the optional physical button.

---

## 10. Known Limitations

Worth stating explicitly rather than hoping they go unnoticed:

- Color detection depends on lighting and needs re-tuning when the environment changes.
- Distance from apparent width assumes a known target size; it is not true depth sensing.
- **Fixed camera angle:** face mode works from ~1 m to ~2.4 m for a standing adult; the robot can't back away from someone standing closer than ~1 m (the face leaves the frame). A floor-level color target is not visible without the tilt servo.
- Face detection is limited to ~2.4 m; a person walking away faster than the robot will outrun it and be lost.
- 2WD must rotate to center: a target moving sideways quickly can leave the frame before the robot turns.
- Face detection needs a roughly frontal face; profiles are missed.
- Single target: with several faces or colored objects in view, it follows the biggest (closest).
- No obstacle avoidance unless the ultrasonic sensor is added; it will drive into things that aren't its target.
- Anyone on the robot's WiFi can drive it — use a hotspot password.
- TT motors are modest: fine on tile and low carpet; thick carpet or ramps may stall them.

---

**References:** [LAFVIN 2WD Smart Robot Car Kit V2.2 — Arduino Forum thread (shield pin map)](https://forum.arduino.cc/t/lafvin-2wd-smart-robot-car-kit-v2-2-updating/1235599) · [LAFVIN 2WD kit product page (2×18650 power)](https://lafvintech.com/products/lafvin-smart-robot-car-2wd-chassis-kit-with-ultrasonic-module-l298n-driver-board-remote-ir-control-for-arduino-uno-diy-kit) · [TB6612FNG datasheet (input HIGH ≥ 0.7 × VCC)](https://cdn.sparkfun.com/datasheets/Robotics/TB6612FNG.pdf) · [OpenCV Zoo — YuNet model notes](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md) · [OpenCV Zoo — benchmark results](https://github.com/opencv/opencv_zoo/blob/main/benchmark/README.md) · [opencv-python-headless on PyPI](https://pypi.org/project/opencv-python-headless/)
