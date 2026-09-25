# FollowBot — a face-following robot

**Myke Lhowelle Marundan** · September 2026

A two-wheeled robot that finds me with a webcam, works out whether I am too close or too far, and drives itself to the right distance. It follows a colour, or a face, or only *my* face; it takes hand signals; and it can be driven by hand from a phone. Everything runs on the robot itself — no internet, no cloud service, no API key.

This document is how I built it: what it is made of, how the parts fit together, and — the part I think matters most — everything that went wrong on the way and what each failure taught me.

---

## 1. What it does

| Mode | Behaviour |
|---|---|
| **Colour** | Follows the biggest yellow object it can see |
| **Face · Simple** | Follows the biggest face, whoever it belongs to |
| **Face · Smart** | Locks onto one person, recognises them, and ignores everyone else |
| **Hand** | Obeys gestures — point to steer, two fingers to reverse, fist to hold, open palm to stop |
| **Manual** | I drive it with an on-screen joystick from my phone |

It also performs four canned routines — spin, dance, nod, shake — and serves its own control dashboard over WiFi.

---

## 2. The hardware

| Part | Role |
|---|---|
| Raspberry Pi 4 | Does all the thinking: camera, vision, decisions, web dashboard |
| USB webcam | 640×480, shrunk to 480×360 for processing |
| Arduino Uno | Drives the motors, and nothing else |
| LAFVIN TB6612 motor shield | The motor driver, sitting on the Uno |
| 2 × DC motors with wheels | Differential drive — steering comes from running them at different speeds |
| 2 × 18650 cells (7.4 V) | Motor power. A second pair is a spare. |

> I never put all four cells in series. Four cells is 14.8 V, and 16.8 V freshly charged; the TB6612 chip is rated to 15 V. Two cells at 7.4 V is what every PWM number in the sketch is calculated around.

### Why there are two computers

This is the design decision I get asked about most, and the honest answer has two halves.

The immediate reason is that the TB6612 board I have is an **Arduino shield** — it has the Uno's header pattern and physically does not fit a Pi.

But I would choose the split anyway, because **a watchdog cannot live on the machine it is watching.** The Uno stops the motors if no command arrives for 500 ms. If that failsafe were written in the same Python that runs the camera, the web server and OpenCV, then a hang in any of those would take the failsafe down with it, and the robot would keep driving into whatever was in front of it. The Uno's timer keeps counting because the Uno has no idea anything is wrong — it just notices the talking stopped.

Two supporting reasons: Linux is not a real-time system, so the Pi's process can be delayed by tens of milliseconds at the scheduler's whim and PWM generated that way stutters; and the Uno is the cheap, sacrificial part sitting next to the motors, while the Pi holds my code, my models and my SD card.

It is not free. I now have two programs to keep in sync, a serial protocol between them, and a flashing step that is easy to forget — which bit me once, badly (see §5.9).

---

## 3. The software stack

| Layer | Choice | Version |
|---|---|---|
| Language (robot) | Python | 3.14.7 |
| Vision, camera, drawing, video encoding | **OpenCV** | 4.14.0 (pinned `>=4.8,<5`) |
| Array maths | NumPy | 2.5.3 |
| Web dashboard server | **Flask** | 3.1.3 |
| Serial link to the Uno | pyserial | — |
| Microcontroller | Arduino C++ | — |
| Dashboard front end | Plain HTML, CSS and JavaScript | no framework, no CDN |
| Autostart | systemd | — |
| Robot's own WiFi hotspot | NetworkManager (`nmcli`) | — |

### Why OpenCV

I did not choose OpenCV for the AI. I counted every `cv2.` call in my code:

| What for | Calls |
|---|---|
| Drawing the live view — boxes, lines, labels, markers | 144 |
| Camera, resizing, colour conversion, blob finding, JPEG encoding | 162 |
| Neural networks | 9 |
| **Total** | **315** |

Under 3% of it is AI. OpenCV opens the webcam, shrinks every frame, converts BGR to HSV for colour tracking, finds the blob, draws the entire overlay, and encodes the JPEG that gets streamed to my phone. All of that was needed for steps 1 and 2, long before any face model existed in the project. By the time I got to face detection, `cv2.dnn` was already sitting there — **so the models were chosen to fit the library, not the other way round.**

The constraint that really decided it: I write and test on a Windows laptop and deploy to the Pi with `git pull`. `cv2.VideoCapture(0)` behaves identically on both. Had I used `picamera2`, the obvious Pi camera library, none of it would run on my laptop and every change would have to be tested on the robot.

What it costs me, fairly: OpenCV works in **BGR** by default, which cost me a whole session when the hand models silently found nothing because they wanted RGB — no error, just nothing. It is version-sensitive. And parts of the API are plainly a C++ library wearing a Python hat.

### Why no framework for the dashboard

The demo runs on the robot's own hotspot, which has **no internet**. Anything loaded from a CDN would simply fail to arrive. So the page is one self-contained HTML file with its own CSS and JavaScript — nothing to fetch.

---

## 4. How it works

### The chain

![System architecture](images/01-system-architecture.svg)

`follow.py` runs one loop, about twelve times a second, and it has five steps: **see, find, decide, act, show.** Everything else is a module it calls.

The command it sends the Uno is one line of text: `"<fwd> <turn>"`, each number −100 to 100. That is the entire protocol between the two computers.

Everything in this project is paced by the camera. One frame every 83 ms, and face detection eats 42 ms of that. Almost every design decision downstream exists because the robot gets a fresh look at the world only twelve times a second — **and because it blurs its own view whenever it moves.**

### 4.1 Seeing — `vision.py`

`vision.py` answers exactly one question: *where is the target, and how big is it?* It returns two numbers or nothing at all. The brain never learns whether it is tracking a yellow ball or my face.

**The camera runs on its own thread.** OpenCV buffers frames, so if I only read the camera when my loop is ready, I get handed the *oldest* frame in the queue. The background thread reads continuously and keeps only the newest, so the robot steers toward where I am rather than where I was two frames ago.

**Colour detection** converts to HSV rather than working in RGB. In RGB, "yellow in shadow" and "yellow in sunlight" are completely different numbers because brightness is smeared across all three channels. HSV separates them, so one setting survives changing light.

### 4.2 The two face models

![Face model pipeline](images/05-face-pipeline.svg)

These are two different jobs, and conflating them is the most common mistake in this area:

- **Detection** — "is there a face, and where?" — **YuNet**, 232 KB. Knows nothing about who.
- **Recognition** — "whose face is that?" — **SFace**, 38.7 MB. Cannot find a face; it has to be handed one.

Simple mode uses only YuNet. Smart mode adds SFace on top. That is the whole difference between them.

YuNet returns fifteen numbers per face: the box, five landmarks (both eyes, nose tip, both mouth corners) and a confidence score. The landmarks are the reason this pairing works — `alignCrop` uses the eyes to rotate and crop the face into a standard pose before SFace sees it. Without that, tilting my head would change the fingerprint for reasons that have nothing to do with identity.

**On where these come from:** OpenCV is the library; the models are separate `.onnx` files from the **OpenCV Zoo**, a different repository. Installing OpenCV does not give you face detection — you still have to download the weights. OpenCV happens to include wrapper classes for these two (`cv2.FaceDetectorYN`, `cv2.FaceRecognizerSF`), which is why they take three lines. It has no wrapper for the hand models, which is why `gestures.py` is 369 lines of decoding 2016 anchor boxes by hand.

### 4.3 Smart mode — staying on one person

![FaceLock ladder](images/02-facelock-ladder.svg)

Recognition costs ~65 ms on the Pi, which is more than an entire frame budget. Running it every frame would drop face mode to about 9 fps. So Smart mode is a ladder, cheapest rung first: a nearly free positional test every frame, with the expensive fingerprint test only when that fails.

The clever part — and the bit I am proudest of understanding — is that `learn()` is a **check wearing a learning costume**. Every fifth frame it takes a fresh fingerprint and compares it to the stored ones *before* keeping it. Position tracking can silently drift onto a person standing next to me; within five frames the fingerprint catches it and drops the lock. A cheap test running constantly, audited by an expensive test running occasionally.

The margin it works with is comfortable: the same person scores **0.88–0.96**, different people **0.20**, and the threshold sits at **0.363** — nowhere near either cluster.

Fingerprints exist only in memory. Nothing about anyone's face is ever written to disk.

### 4.4 Deciding — distance

![Distance by frame height](images/03-distance-by-height.svg)

This is my own idea and it replaced a method that never worked properly.

The camera is bolted to the robot, so geometry does something useful for free: **someone far away appears low in the frame, and as they come closer their face rises.** So "distance" is one subtraction — how far the bottom of the face box sits above the bottom of the picture.

**Why three lines and not one.** With a single threshold the robot crosses it, drives, overshoots, crosses back, reverses, and oscillates forever. Three lines give it hysteresis: it *enters* the parked state at 180 but only *leaves* it below 140, and that 40-pixel gap is territory where nothing happens at all.

| Currently | When | Becomes |
|---|---|---|
| anything | chin above 230 | back off |
| following | chin reaches 180 | parked |
| parked | chin drops below 140 | follow |
| backing | chin drops below 180 | parked |

**Calibrating it is one measurement:** stand where I want it to stop, read the number off the live view, put it in the middle slot.

What I gave up, honestly: it is calibrated for *one person's height* — a taller person's chin sits higher at the same distance, so the robot parks further away from them. It breaks if the camera is knocked. And it does not know metres at all.

But that is the trade, and I think it is the right one. The old method tried to answer *"how far away is that person?"* — a measurement problem needing a known object size and a face that does not change shape. The line method answers *"is that person at the right distance?"* — a comparison. And the line **is** the right distance by construction, because I put it there by standing in the spot I wanted.

### 4.5 Deciding — steering

![Steering by duration](images/04-steering-by-duration.svg)

Which way to turn is easy. How *much* is where it gets interesting, and the answer is not what I first assumed.

The natural approach is proportional steering — turn harder the further off-centre the target is. But the number goes to the Uno, which maps it onto PWM 65–95 for a pivot:

| Command | Actual PWM | |
|---|---|---|
| `turn 5` | 66 | barely pivoting |
| `turn 20` | 71 | barely pivoting |

A **4× difference in the command produces a 7% difference in voltage**, and both sit on the floor where the wheels only just break friction. Proportional steering is a fiction at the bottom of the range — which is exactly where it is needed, because most corrections are small.

So the robot steers by **time** instead. The power is the same every time; what varies is how long it lasts — 0.06 s for a small correction, up to 0.20 s for a big one.

Driving is continuous but turning pauses, and that asymmetry is deliberate: **rotation smears the picture, driving straight barely does.** When the robot pivots, every pixel sweeps sideways across the sensor and the detector fails on the blur. Driving forward, the scene mostly just scales.

### 4.6 Acting — the Uno

An Arduino has no operating system and runs one program: `setup()` once, then `loop()` forever. The Uno is **not waiting** for commands — it runs flat out thousands of times a second, and commands land into an already-running program.

That matters, because **a command sets a target, not a speed.** When `"50 0"` arrives, the sketch writes `targetL` and `targetR` and returns. A separate function walks the actual wheel speeds toward those targets a little on every pass. That is only possible because the loop is always running.

The easing is deliberately lopsided:

| | Rate | Standing start to full speed |
|---|---|---|
| Ramping up | 180/s | 0.56 s — gentle; this is what killed the lurch |
| Ramping down | 700/s | 0.14 s — quick |

Braking never feels like a lurch, so there is no reason to be slow about it — and a slow wind-down would eat the camera's look-pauses.

`setup()` calls `drive(0, 0)` **before** opening the serial port, so there is no window where the pins are configured but undefined. That is what stops the robot twitching when I plug it in.

### 4.7 The joystick, and three independent stops

Driving by hand uses the same path; my thumb just replaces the brain. One real push — 60% of a radius, 20° right of straight up:

| Stage | What it does | Result |
|---|---|---|
| Browser | dead zone, axis detent, expo curve | `fwd 27 · turn 6` |
| Pi | ×70% and ×50% | `fwd 19 · turn 3`, sent as `"19 3"` |
| Uno mixes | `left = fwd+turn`, `right = fwd−turn` | left 22, right 16 |
| Uno converts | map onto PWM 70–140 | **PWM 84 and 80** |

Left wheel slightly faster than right, so it curves gently right — reaching that speed over 0.12 s rather than instantly.

Three separate things stop it, each on a different machine from the failure it catches:

| Guard | Where | Catches |
|---|---|---|
| Release posts zero | browser | lifting my thumb |
| 0.5 s joystick timeout | Pi | phone locked, WiFi dropped, tab closed |
| **500 ms serial timeout** | **Uno** | **the Pi crashing, or the cable being pulled** |

Only the last one still works when the thinking half is dead. That is the entire reason the Uno exists.

---

## 5. Testing — what went wrong, and what each failure taught me

This is the real story of the project. Almost none of it was in the plan.

### 5.1 It lurched on every single move

**What I saw:** every command made the robot jump rather than move.

**What I assumed:** my speeds were too high.

**What it actually was:** the Uno's `MIN_PWM`. Any non-zero command is lifted to at least the minimum, so even a gentle `fwd 25` came out as PWM 117 — applied instantly.

**What I changed:** lowered `MIN_PWM` 90→70 and `MAX_PWM` 200→140, and added ramping so a change is spread over a moment instead of arriving all at once.

### 5.2 It drove into me

**What I saw:** it would approach and then keep going, right into me.

**What I assumed:** the distance threshold was wrong.

**What it actually was:** it drove forward, its own movement blurred the picture, detection failed — and my "grace window" repeated the last command, which was *drive forward*. It advanced blind, and a single flickering detection reset the grace and let it do it again.

**What I changed:** the grace window now commands zero forward.

### 5.3 The distance was 24% wrong

**What I saw:** it stopped much too close, from every starting distance.

**What I did:** measured instead of guessing. With a tape measure at 30 inches, the live view read `w=66`. The code assumed a face is 0.15 m wide as the detector draws it; the real figure was **0.12 m**. Every reading was inflated, so aiming for 0.80 m actually drove to 0.64 m.

**What I learned:** I had written a guess into the code with no comment saying it was one. It behaved exactly like a measurement for weeks.

### 5.4 It still crept in whenever I turned my head

**What I saw:** it held distance well when I faced it, and closed in whenever I looked away.

**What it actually was:** I was measuring distance by how *wide* my face looked, and a profile is much narrower than a face-on view. The robot read that narrowing as me stepping backwards.

**What I changed:** this is where I had the idea to add a horizontal line and judge distance by **where my face sits in the frame** instead. Vertical position does not change when I turn my head. Three rounds of re-tuning the thresholds had never fixed this, because the thresholds were not the problem — the measurement was.

### 5.5 It snapped round whenever I stepped aside

**What I saw:** step slightly left or right and it would whip round rather than follow smoothly.

**What I assumed:** the turn gain was too high. Lowering it changed almost nothing, which was the clue.

**What it actually was:** the PWM floor again. `turn 5` and `turn 25` come out at nearly the same wheel speed, so proportional steering was effectively on/off and every correction was the same 18° snap.

**What I changed:** steer by *how long* the wheels turn rather than how hard, and give pivoting its own, gentler PWM range. A small correction now swings 1.7°, a big one 11.7°.

### 5.6 It bolted off searching the moment it lost me

**What I saw:** blink, or turn my head, and it would immediately start sweeping the room.

**What I changed:** losing a face usually means I moved my head, not that I left. So now it stands still for 5 frames, then watches without moving for **3 seconds**, and only then starts sweeping. Reappearing at any point picks straight back up.

### 5.7 After a small turn it bolted again and overshot

**What I saw:** it would correct toward me, then swing straight past.

**What it actually was:** the same mistake as §5.2, which I had only half fixed. I stopped the grace window repeating *forward*, but deliberately left it repeating *turning*, reasoning that turning blind is harmless. It is not — the robot's own turn blurs the picture, the blur loses the face, and it keeps turning on a view it no longer has. Five frames at 12 fps is another 30°. I reproduced it in simulation: **11.8° past centre, ending on the wrong side.**

**The rule I settled on:** *if it cannot see, it does not move.* One sentence, and it killed two separate bugs.

**What I actually learned:** the last command is not evidence about the present.

### 5.8 The search froze after its first burst

**What I saw:** it would turn once, then sit there forever.

**What it actually was:** the search pauses between steps to let the camera get a sharp picture, and the pause returned `0`. The caller read `0` as "the search gave up".

**What I changed:** a pause returns `0`, giving up returns `None`. Two different kinds of nothing needed two different values.

### 5.9 None of the motor fixes were live

**What I saw:** the lurching persisted through several rounds of fixes.

**What it actually was:** I had never re-uploaded the Arduino sketch. Every change was sitting in a file on my laptop.

**What I changed:** the sketch now prints a version banner on startup, so I can always tell which build is actually flashed.

### 5.10 The hand models found nothing at all

**What I saw:** the palm detector's best score was 0.07. No error, no warning, just silence.

**What it actually was:** those models expect **RGB**, and OpenCV hands you **BGR**. The colours were swapped, so the model was looking at something that did not resemble a hand.

**What I changed:** one conversion, and the score went to 0.91. I wrote it into the code comments and the model README so I never lose a session to it again.

### 5.11 The camera is the bottleneck, not the Pi

**What I measured:** face detection takes 41.7 ms on the Pi, so the Pi could sustain **23 fps**. The webcam delivers **12**.

**Why:** the camera offers no MJPG, so every frame crosses the USB cable uncompressed. 640×480 at 30 fps is 18.4 MB/s, which it cannot sustain — so it quietly sends fewer frames instead.

**What it means:** the Pi sits idle about half the time, and nearly every problem above traces back to acting on a picture that was already stale. This is the single biggest thing still limiting the robot.

### 5.12 The joystick was imprecise

**What I saw:** hard to drive accurately from a phone.

**What it actually was:** two things. Touching the pad anywhere instantly jumped the knob there, so tapping near the rim meant near-full speed immediately. And the PWM floor meant the bottom of the stick's travel did nothing perceptible.

**What I changed:** the pad now reads how far my thumb has moved *since it landed* rather than where it landed; a 12% dead zone in the middle; a 10° detent so driving dead straight is easy to hold; and a curved response that spends most of the stick's travel on the slow end.

### 5.13 The routines felt slow even after speeding them up

**What I saw:** I sped the canned routines up by 15%, then 30%, and they still felt sluggish.

**What I suspected:** the battery was flat. PWM delivers a *fraction of pack voltage*, so as the cells drain, the same command produces less power.

**The real problem:** I had no way to tell. I had been tuning against an unknown power supply.

**What I changed:** a battery monitor — two equal resistors halving the pack voltage into an analog pin, reported to the dashboard. It is measured only while the wheels are stopped, because a pack sags under load and the sagging number says more about the motors than the charge.

### The pattern in all of it

Reading these back, two themes run through nearly every one.

**The robot kept acting on a view it no longer had.** At 12 fps, with movement blurring its own pictures, the gap between "what it can see" and "what is true" is where almost every bug lived.

**Several of my constants were guesses that read like measurements.** The face width, every PWM value, the distance bands. A guess with a confident comment next to it is indistinguishable from a measurement until something goes wrong.

---

## 6. What I measured

| | Value |
|---|---|
| Face detection (YuNet), Pi 4 | ~42 ms per frame → the Pi could do 23 fps |
| Face recognition (SFace), Pi 4 | ~65 ms per face |
| Colour detection, Pi 4 | ~2.6 ms |
| Webcam, actual | ~20 fps in good light, ~12 in dim |
| Detector's range limit | faces under ~26 px wide are missed → about 2.4 m |
| Recognition | same person 0.88–0.96, different people 0.20, threshold 0.363 |
| Face width as the detector draws it | 0.12 m (measured, not assumed) |
| Driving speed | about 8 cm/s, continuous |

---

## 7. What I know is still weak

- **Every PWM value in the Arduino sketch is still a guess of mine.** The sketch has a calibration routine that creeps the power up in steps until the wheels move; I have not run it yet, and it must be run on a charged battery.
- **The frame rate.** 12 of a possible 23. Everything else would improve if this did.
- **The distance calibration assumes my height and a fixed camera.** It has to be redone once the camera is properly mounted, and it will park further away from a taller person.
- **Gesture mode obeys the nearest hand, whoever it belongs to.** Verifying identity would need face detection running at the same time, which gesture mode deliberately avoids for speed.
- **Dim rooms halve the frame rate**, which is the main thing that makes a follower wobble. The demo room needs to be lit.

---

## 8. What is left

1. Run the PWM calibration on a charged battery and replace my guesses with measurements.
2. Chase the frame rate — a USB 3 port, and a smaller capture size if that helps.
3. Mount the camera at about 48 cm, tilted 45°, and recalibrate the distance line.
4. Fold the colour tuner and the top-view simulator into the dashboard as one page.

Ideas I have written up but not built: a local language model on my laptop that can take spoken commands and explain the robot's own decisions, and having gesture mode obey only the person it recognises.
