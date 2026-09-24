"""Measure what the webcam ACTUALLY delivers at each size.

A webcam will happily tell you it is set to 30 fps and then send you 12. The only
way to know is to count the frames that arrive. This tries every size the camera
offers and reports the real rate, so you can pick one.

Why it matters: this camera has no MJPG, so every frame crosses the USB cable
uncompressed. 640x480 at 30 fps is 18.4 MB/s, which many cheap webcams cannot
sustain - they silently send fewer frames instead. Halve the width and the data
rate drops to a quarter.

Run it on the Pi with the robot stopped (it needs the camera to itself):

    sudo systemctl stop followbot
    ~/robot-venv/bin/python tools/camera_speed.py
    sudo systemctl start followbot

Then put the winner into CAPTURE in pi/vision.py.
"""
import sys
import time

import cv2

CAMERA = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SECONDS = 3.0                       # how long to count frames at each size
SIZES = [(640, 480), (352, 288), (320, 240), (176, 144)]


def measure(cap, width, height):
    """Ask for this size, then count how many frames really arrive per second."""
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)

    for _ in range(5):              # throw away the first few while it settles
        cap.read()

    frames, start = 0, time.time()
    while time.time() - start < SECONDS:
        ok, frame = cap.read()
        if not ok:
            break
        frames += 1
    seconds = time.time() - start
    got_h, got_w = frame.shape[:2]
    return frames / seconds, got_w, got_h


print(f"Measuring camera {CAMERA} - {SECONDS:.0f} seconds per size\n")
cap = cv2.VideoCapture(CAMERA)
if not cap.isOpened():
    raise SystemExit(f"Camera {CAMERA} not found. Is the robot still running? "
                     "Stop it first: sudo systemctl stop followbot")

print(f"  {'asked for':>11} {'actually got':>13} {'fps':>7} {'USB traffic':>12}   verdict")
best = (0, None)
for want_w, want_h in SIZES:
    fps, got_w, got_h = measure(cap, want_w, want_h)
    mb = got_w * got_h * 2 * fps / 1e6           # YUYV = 2 bytes per pixel
    if fps >= 24:
        verdict = "plenty - the Pi becomes the limit"
    elif fps >= 18:
        verdict = "good"
    else:
        verdict = "slow - the camera is holding the robot back"
    print(f"  {f'{want_w}x{want_h}':>11} {f'{got_w}x{got_h}':>13} {fps:6.1f}  {mb:9.1f} MB/s   {verdict}")
    if fps > best[0]:
        best = (fps, (got_w, got_h))

cap.release()

print(f"\nFastest: {best[1][0]}x{best[1][1]} at {best[0]:.1f} fps")
print("\nFace detection takes ~42 ms on this Pi, so anything above ~23 fps is wasted -")
print("pick the BIGGEST size that still reaches about 20 fps, because a bigger")
print("picture means faces stay detectable further away.")
print("\nThen set it in pi/vision.py:   CAPTURE = (width, height)")
