# How I Built FollowBot

**Myke Lhowelle S. Marundan**

A record of how this project actually went — the order I did things in, the decisions I had to make, the things I got wrong, and what I learned from each of them.

I am writing this partly so I can explain the robot to someone else, and partly because a lot of what I learned was not in the plan, and I did not want to forget how I got there.

---

## Before I started

I wanted a robot that follows me. Not a remote-control car — something that finds me on its own, decides I am too far away, and comes closer without being told.

What I had: a Raspberry Pi 4, an Arduino Uno, a LAFVIN TB6612 motor shield, two DC motors, a USB webcam, and some 18650 cells.

What I knew: Python, roughly. What a Raspberry Pi was.

What I did not know: anything about computer vision, what PWM meant, how a motor driver worked, how to make two computers talk to each other, or what a neural network model file even was. Most of this project was learning those things one at a time, usually because something had broken and I needed to understand why.

I gave myself four days.

---

## Day 1 — Teaching it to see

*22 September*

### Getting a picture at all

The very first thing I wrote just opened the webcam and showed me the frames. It felt trivial at the time. It was not — it was the moment I found out that **OpenCV** was going to be the backbone of everything.

I want to be honest about this decision, because I think people assume I chose OpenCV because of the AI. I did not. I chose it because it was the one library that could open the webcam, resize the frames, convert colours, draw on the picture, and encode video for a web page. Later, when I counted every `cv2.` call in my finished code, it came to 315 — and only **9 of them were neural networks**. Under 3%. The AI was almost an afterthought in how I actually use the library.

The thing that really settled it was practical: I write code on my Windows laptop and deploy it to the Pi. `cv2.VideoCapture(0)` behaves the same on both. If I had used `picamera2`, which is the obvious Pi camera library, nothing would run on my laptop and I would have had to test every single change on the robot. Given how much of this project I ended up debugging at a desk with no robot attached, that would have cost me the whole schedule.

**What I learned:** pick the dependency that lets you develop where you actually sit.

### Following a colour

Next I made it find a yellow object. This is where I learned about **colour spaces**, and it was the first idea in the project that genuinely surprised me.

My instinct was to look for "yellow pixels" in RGB. That does not work, because in RGB, yellow-in-shadow and yellow-in-sunlight are completely different numbers — the brightness is smeared across all three channels. **HSV** splits them apart: hue is *which* colour, saturation is *how strong*, value is *how bright*. So I could say "hue between 22 and 38, and I do not care much about brightness," and one setting survived the light changing.

I also built a little tuner with sliders so I could find those numbers by eye instead of guessing. That turned out to be the pattern for the rest of the project: **when I could not reason about a number, I built something that let me see it.**

### Two ways to detect a face

By the end of the first day I was on faces, and I did something I am glad about: I wrote it **twice**. One version using OpenCV's high-level face detector class, one working closer to the raw model output.

I kept the high-level one. But writing both is what taught me what the high-level one was actually doing, and three days later — when I had to write the hand detection completely by hand, with no high-level class to help — that knowledge was the only reason I could do it.

**What I learned:** detection and recognition are two completely different jobs, and I had been using the words interchangeably.

- **Detection** asks *"is there a face, and where?"* That is **YuNet**, a 232 KB model.
- **Recognition** asks *"whose face is that?"* That is **SFace**, 38.7 MB.

SFace cannot find a face. It has to be handed one. And that size difference — 232 KB against 38.7 MB, **167 times bigger** — tells you something real: finding a face is a much easier problem than telling two of them apart.

I also learned that these models are not part of OpenCV. OpenCV is the library; the models are separate `.onnx` files from the **OpenCV Zoo**, a different repository. You can install OpenCV and still have no face detection, because you have not downloaded the weights yet.

---

## Day 2 — Making it a robot

*23 September*

### The decision I get asked about most

Day two was when the Pi, the Uno and the motors became one machine, and that meant confronting a question: why two computers at all? The Pi could drive the motor pins directly.

The immediate answer is boring — the TB6612 board I own is an **Arduino shield**. It has the Uno's header pattern and physically does not fit a Pi. That decision was made for me the moment I bought the kit.

But I have since decided I would choose the split anyway, and the reason is worth stating properly:

> **A watchdog cannot live on the machine it is watching.**

The Uno stops the motors if no command arrives for 500 ms. If I had written that failsafe in the same Python that runs the camera, OpenCV and a web server, then a hang in any of those would take the failsafe down with it, and the robot would keep driving into whatever was in front of it. The Uno's timer keeps counting because the Uno has no idea anything is wrong. It just notices the talking stopped.

The protocol between them is deliberately tiny — one line of text per frame, `"<fwd> <turn>"`, each number from −100 to 100. That is the entire interface between the two halves of the robot.

**What I learned:** a system that must not fail should not share a fate with the system most likely to fail.

### Deciding, before any motor moved

I wrote the decision logic — the part that turns "where is the target" into "what should the wheels do" — before the robot could move, and I tested it in a little top-down simulator where I could drag myself around with the mouse.

This is the single best decision I made in the whole project. It meant that by the time the robot actually drove, the logic had already been through dozens of situations.

It is also where I learned about **hysteresis**, which I now think is the most generally useful idea I took from this project. My first version had one threshold: closer than X, stop; further than X, drive. It oscillated forever — cross the line, drive, overshoot, cross back, reverse, repeat.

The fix is to have **three** thresholds instead of one, and to make which threshold applies depend on what the robot is already doing. It *enters* the parked state at one value but only *leaves* it at a different, further value. The gap between them is territory where nothing happens at all, and that gap is what stops the twitching.

**What I learned:** if a system flips back and forth, the problem is usually that it has one threshold where it needs two.

### A dashboard with no framework

I wanted to control it from my phone, so I built a web dashboard with Flask. The constraint that shaped it: **on demo day the robot is its own WiFi hotspot, with no internet.** Anything loaded from a CDN would simply never arrive.

So the entire page is one self-contained HTML file with its own CSS and JavaScript. No React, no Bootstrap, no font from Google. It also meant when I redesigned it to match a style I liked, I had to write all of that myself — which was more work, and taught me more.

Then my iPad refused to show the video. Safari will not display an MJPEG stream. Rather than fight it, I made the page notice the failure and fall back to fetching single pictures about eight times a second. It still works; it just says `· STILLS` in the corner so I know which mode it is in.

**What I learned:** design for the worst network you will actually be on, not the one you are developing on.

### The first real drive

Late on day two, the Uno finally drove the wheels from the Pi's commands. I remember it working and being immediately disappointed — it moved, but every command made it *jump*.

That began the part of the project I learned the most from.

---

## Day 3 — Hands, and the first hard lessons

*24 September*

### Building the hand pipeline from nothing

I wanted gesture control, so I added a hand detector. This is where day one's decision to write face detection twice paid off.

For faces, OpenCV gives you a ready-made class and it is three lines. For hands, there is **no wrapper at all** — just "here is an ONNX file, good luck." I had to build 2016 anchor boxes myself, put the raw scores through a sigmoid, decode the position offsets, run non-maximum suppression to remove duplicate detections, and then compute a rotated crop from the wrist to the middle knuckle before the second model could read the finger positions.

That is why `gestures.py` is 369 lines and the entire face detector is three.

Then it found nothing. Score 0.07, over and over, with **no error message at all** — just silence.

It took me far too long to find: those models expect **RGB**, and OpenCV hands you **BGR**. The colour channels were swapped, so the model was looking at something that did not resemble a hand at all. One conversion, and the score jumped to 0.91.

**What I learned:** the worst bugs do not throw errors. A model that is fed nonsense does not complain — it just confidently finds nothing, and it looks exactly like a model that does not work.

### The lurching, and what PWM actually is

Back to the jumping. I assumed my speeds were too high and kept lowering them. It did not help, and *that* was the clue.

This is where I actually understood **PWM**. The motor is not given a voltage; it is switched on and off very fast, and the fraction of time it spends on is the power. But a motor needs a minimum before it overcomes friction at all — below that it just buzzes. So the Uno code lifts any non-zero command up to a floor value.

Which meant my gentle `fwd 25` was arriving as a much larger number, **applied instantly**.

Two fixes. I lowered the floor and the ceiling. And I added **ramping** — the command now sets a *target*, and a separate piece of code walks the actual wheel speed toward that target a little on every pass of the loop.

I made the ramp deliberately lopsided: gentle speeding up, quick slowing down. Speeding up gently is what kills the lurch. Braking quickly is fine, because braking never feels like a lurch — and a slow wind-down would have eaten into the pauses the camera needs to get a sharp picture.

**What I learned:** a command should set a target, not a value. Let something else decide how fast reality is allowed to catch up.

---

## Day 4 — The day I stopped guessing

*25 September*

This was the longest day and almost all of it was tuning. Looking back, it divides into two kinds of problem: things I had guessed wrong, and one idea that was simply the wrong shape.

### It kept driving into me

The robot would approach and then just keep coming.

I assumed the distance threshold was wrong. It was not. What actually happened: it drove forward, **its own movement blurred the picture**, detection failed for a frame or two, and my code — trying to be helpful — repeated the last command through the gap. The last command was "drive forward." So it advanced blind.

I fixed it so the gap commands zero forward movement. But I left it still repeating *turns*, reasoning that turning blind is harmless.

It is not, and I found that out later the same day when it started swinging straight past me after small corrections. The robot's own turn blurs the picture, the blur loses the face, and it keeps turning on a view it no longer has. Five frames at 12 fps is another 30 degrees. I reproduced it and measured it: **11.8 degrees past centre, ending on the wrong side.**

So I wrote the rule properly this time:

> **If it cannot see, it does not move.**

One sentence, and it killed two separate bugs I had been treating as unrelated.

**What I learned, and I think this is the most important thing in the whole project:** the last command is not evidence about the present. I had been letting the robot act on a memory.

### The 24% error I had written myself

It also stopped too close from every starting distance. So instead of adjusting numbers until it looked right, I measured: tape measure at 30 inches, read the number off the screen.

The code assumed a face is 0.15 m wide as the detector draws the box. The real figure was **0.12 m**. Every distance reading was inflated by about 24%, so when I asked it to stop at 0.80 m it actually drove to 0.64 m.

I had written a guess into the code with a confident comment next to it, and for days it had behaved exactly like a measurement.

**What I learned:** label your guesses. A guess and a measurement look identical in source code, and you will forget which is which within a week.

### The idea that was the wrong shape

Even after calibrating, it crept toward me — but only when I turned my head.

I was measuring distance by how *wide* my face looked. A face seen from the side is much narrower than one seen straight on. So every time I glanced away, the robot read that narrowing as me stepping backwards, and came to find me.

Three separate rounds of re-tuning the thresholds never fixed it, because the thresholds were not the problem. **The measurement was.**

This is where I had the idea I am most pleased with. The camera is bolted to the robot, so geometry does something useful for free: someone far away appears **low** in the frame, and as they come closer their face **rises**. So I stopped measuring width and started measuring *where my face sits in the picture*, with three horizontal lines drawn across the live view showing the thresholds. Chin on the middle line means the right distance.

Vertical position does not change when I turn my head.

What I gave up is real, and I want to be honest about it: this is calibrated for **my** height, so it will park further away from a taller person; it breaks if the camera is knocked; and it does not know distance in metres at all.

But I think it is the right trade, and here is why. The old method tried to answer *"how far away is that person?"* — a measurement problem, needing a known object size and a face that does not change shape. The new one answers *"is that person at the right distance?"* — a comparison. And the line **is** the right distance by construction, because I put it there by standing where I wanted the robot to stop.

**What I learned:** when tuning a system repeatedly fails to fix something, stop tuning and question what you are measuring. I replaced a hard measurement problem with an easy comparison problem, and it worked immediately.

### Steering that was a fiction

It also snapped violently round whenever I stepped to one side. I assumed the turn strength was too high. Lowering it changed nothing — the same clue as before.

The PWM floor again. A turn command of 5 and a turn command of 25 come out at almost the **same wheel speed**, because both sit just above the minimum. A 4× difference in the number produced about a 7% difference in actual power. My proportional steering was a fiction at the bottom of its range, which is exactly where I needed it, because most corrections are small.

So I made the robot steer by **time** instead of power. Same power every time; what changes is how long it lasts — about 0.06 seconds for a small correction, up to 0.20 for a big one.

**What I learned:** if your control has a floor, you cannot control below it. Find a different dimension to vary. I could not vary the voltage usefully, but time is continuous all the way down.

---

## After the four days

The robot worked. Most of what came next was about being able to *trust* it.

**I found out the camera is the bottleneck, not the Pi.** I measured face detection at 41.7 ms, which means the Pi could sustain about 23 frames per second. The webcam delivers 12. The reason is that it offers no compression, so every frame crosses the USB cable raw — 18.4 MB/s at full rate, which it cannot manage, so it quietly sends fewer frames instead.

This reframed the entire project for me. Almost every bug I had fought — the blur, the stale views, the overshoot — traces back to the robot getting a fresh look at the world only twelve times a second. The Pi sits idle about half the time.

**I fixed the joystick**, which had two problems: touching the pad anywhere instantly jumped the control there, so a tap near the edge meant near-full speed immediately; and the PWM floor meant the bottom of its travel did nothing perceptible. It now reads how far my thumb has moved *since it landed*, has a dead zone in the middle, snaps to straight lines, and spends most of its travel on the slow end.

**And I added a battery monitor**, for a reason that annoys me. I had sped the canned routines up by 15%, then by 30%, and they still felt slow. I eventually suspected the battery — PWM delivers a *fraction of pack voltage*, so as the cells drain the same command produces less power. But I had no way to check. I had been tuning against an unknown power supply.

Two resistors dividing the pack voltage into an analog pin, and now the dashboard tells me. It only measures while the wheels are stopped, because a battery sags under load and the sagging number says more about how hard the motors are working than about how much charge is left.

**What I learned:** before you tune something, make sure you can see everything that affects it.

---

## What I would tell myself at the start

**Build the thing that lets you see the problem.** The HSV slider tool, the simulator, the three lines drawn on the live view, the distance bar, the battery readout — none of those are features. Every one of them exists because I could not tell what was happening, and every one of them paid for itself within a day.

**Most of my bugs were one bug.** The robot kept acting on a view it no longer had. Driving into me, overshooting on turns, the search sweeping past me — I treated them as separate problems for two days before I saw they were the same problem wearing different clothes.

**The hardware has opinions.** I expected to spend this project on computer vision. I spent at least as much of it on a motor's minimum power, a webcam's USB bandwidth, and a battery's voltage curve. The clever software was mostly straightforward. The physical floor underneath it shaped almost every decision I made.

**Lowering a number and seeing no change is information.** Twice I assumed a value was too high, lowered it, and got no improvement. Both times that was the system telling me my model of the problem was wrong — and both times I lowered it again before I listened.

**Measuring is faster than guessing, even though it feels slower.** Getting a tape measure took me five minutes and replaced three days of adjusting numbers.

---

## What is still not right

I would rather write this down than pretend otherwise.

- **Every PWM value in the Arduino sketch is still a guess of mine.** I wrote a calibration routine that creeps the power up until the wheels move, and I have not run it yet. It needs to be done on a charged battery, or I will measure a floor that is too high.
- **The frame rate.** 12 of a possible 23. Everything else improves if this does.
- **The distance calibration assumes my height and a camera that does not move.** It has to be redone once the camera is properly mounted.
- **Gesture mode obeys the nearest hand, whoever it belongs to.** Checking identity would mean running face detection at the same time, which gesture mode deliberately avoids for speed.
- **A dim room halves the frame rate**, which is the main thing that makes the following wobble. The demo room needs light.

---

## Where the learning actually went

If someone asked me what this project taught me, I would not lead with the robot. I would say:

I learned that **colour spaces exist and why** — that how you represent data decides which questions are easy to ask.

I learned what a **model file** actually is: not a program, just weights, which some library has to know how to run. And that detection and recognition are different problems with very different costs — 42 ms against 65 ms, which is why my code runs the expensive one only every fifth frame and lets a cheap test carry the rest.

I learned **hysteresis**, and I now see the need for it everywhere.

I learned what **PWM** is, what a minimum duty cycle does to your ability to control anything gently, and that you can sometimes route around a physical limit by varying a different dimension.

I learned a lot of **Linux and networking** I did not expect: systemd so the robot starts on boot with no laptop attached, NetworkManager so it broadcasts its own WiFi, SSH, and how to work on a machine with no screen. On the day I was locked out of it at school, the thing that saved me was knowing I could plug it into a TV with a micro-HDMI cable and get a console.

And I learned something about **debugging** that I do not think I could have learned from a tutorial: that the bug is very rarely where the symptom is. The robot drove into me, and the cause was a comment I had written about being helpful during dropped frames. It snapped when turning, and the cause was a motor's minimum power. It crept forward when I looked away, and the cause was that faces are narrower from the side.

Every single time, the fix was somewhere I was not looking.
