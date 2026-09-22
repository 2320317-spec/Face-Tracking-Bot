# steps/ — build the vision code one piece at a time (on the PC)

Each step is its own script, written by you. Keep every finished step: the Git history then shows how the project was built. Step 6 combines them into the real program in [`pi/`](../pi/).

Run every script from the project root:

```bash
.venv\Scripts\python steps\01_live_feed.py
```

Try each step yourself first. The build plan has a finished reference for each piece (section numbers below) — use it to check your work afterwards, not before.

---

### Step 1 — `01_live_feed.py`: live camera feed

- **Goal:** open the webcam, show the frames in a window, quit cleanly on a key.
- **Then add:** ask the camera for 640×480 MJPG, shrink each frame to 480×360 (the size the robot processes), and draw the FPS on the frame.
- **You'll use:** `cv2.VideoCapture`, `cap.read`, `cv2.imshow`, `cv2.waitKey`, `cap.set`, `cv2.resize`, `cv2.putText`, `time.time`.
- **Done when:** the window shows 480×360 live video with an FPS number, and closes cleanly on your key.
- **Plan:** 5.7 (camera capture), 6 (performance).

### Step 2 — `02_color_detect.py`: find a colored object

- **Goal:** in every frame, find the biggest blob of your target color, and draw its bounding box, center `x` and width `w`.
- Same pipeline as an image version (HSV → `inRange` → morphology → contours), but live, plus `cv2.boundingRect` for the box.
- Show the mask in a second window. Ignore blobs smaller than ~300 px² — that's noise.
- **Done when:** the box sticks to a green (or orange) object, `w` grows as the object comes closer, and specks in the background are ignored.
- **Plan:** 5.6.

### Step 3 — `../tools/hsv_tune.py`: HSV tuner

- **Goal:** six sliders (H, S, V — low and high) and a live mask, to find the numbers for your target under your lighting.
- **You'll use:** `cv2.createTrackbar`, `cv2.getTrackbarPos`.
- **Done when:** only your target is white in the mask, and the script prints the numbers to paste into step 2.
- It lives in [`tools/`](../tools/) because you'll run it again in the demo room.
- **Plan:** 5.11.

### Step 4 — `04_decision.py`: from `x` and `w` to a motor command

- **Goal:** turn the target's position and size into `fwd turn` (each −100…100) and draw it on screen. No motors yet — just the numbers.
- **Steering:** a dead zone in the middle; outside it, turn proportional to how far off-center the target is.
- **Distance:** three states — follow / hold / back — with separate resume, stop and backup thresholds (hysteresis).
- **Target lost:** keep the last command for a few frames, then stop.
- **Done when:** moving the target left, right, closer and farther changes the command the way the plan describes, without flickering at the thresholds.
- **Plan:** 1 (concept), 5.5 (control logic).
- **Target lost:** after the short grace, the robot **searches** — turns toward the side it last saw the target, then sweeps back the other way, each sweep wider, and gives up after 20 s (`SEARCH_...` settings in `brain.py`).
- **Files:** the brain itself lives in `brain.py` (settings, `Follower`, wheel mixing, searching), so steps 4, 4b and 5 share it — change a setting once, all of them use it.

### Step 4b — `04b_simulator.py`: watch the robot drive (no hardware)

- **Goal:** a top-down virtual robot, shaped like the real one (wheels and camera at the front, free wheel at the back), driven by the same `brain.py`. Its camera is simulated, so the whole loop runs: see → decide → drive → see again.
- **Controls:** drag = move you · right-drag = move the stranger · `n` stranger on/off · `s` SIMPLE / SMART · `a` you walk by yourself · `m` color / face · `r` reset · space pause · `q` quit.
- **On screen:** the camera's view cone, rings at the resume / stop / back-up distances, the path, the robot's camera view, the command and both wheel speeds.
- **Try:** stranger on, then drag yourself behind the robot. It sweeps left and right to search; SIMPLE follows the first person it sees (the stranger), SMART ignores the stranger and keeps looking for you.
- **Use it to:** try new settings in `brain.py` (`KP`, speeds, bands) and see the effect before the real robot exists.
- **Simplified:** flat floor, no wheel slip, instant motors, 0.1 s camera delay, top view only (ignores camera tilt).

### Step 5 — `05_face_detect.py`: faces instead of colors

- **Goal:** detect faces with YuNet, take the widest (closest) one, and feed its `x` and `w` into the same decision logic.
- **Two modes** (press `s` to switch):
  - **SIMPLE** follows the biggest face in each frame. Lost you? It searches and follows the first person it sees.
  - **SMART** locks onto one person and remembers their face (SFace "fingerprints"), smooths `x` and `w`, and shows the face details: 5 landmarks, head turn, distance, certainty, match. Lost you? It searches and follows only **you** — everyone else is "not you". Click a face = "this is me", `l` = forget me.
- **Needs:** both model files in `pi/models/` — see [its README](../pi/models/README.md).
- **You'll use:** `cv2.FaceDetectorYN.create`, `detector.detect`.
- **Done when:** the box sits on your face and stays on it as you step back to about 2 m, with `w` shrinking.
- **Plan:** 4.4 (how big faces are in pixels), 5.6.

### Step 6 — `pi/follow.py` + `pi/web.py`: the real program

- **Goal:** combine steps 1–5 into one program with three modes (color / face with Simple + Smart / manual), a `--dry` flag (runs without the Uno), and the phone dashboard (Flask): live view, mode buttons, Start / STOP, joystick, tap-your-face.
- **Shared code:** the brain and the vision now live in `pi/brain.py` and `pi/vision.py`; steps 4, 4b and 5 import them from there, so there's one copy to tune.
- **Done when:** `.venv\Scripts\python pi\follow.py --dry --camera 1` runs on the laptop, and `http://localhost:8000` shows the live view and switches modes. Then the same with `--dry` on the Pi.
- **Details:** [pi/README.md](../pi/README.md).
