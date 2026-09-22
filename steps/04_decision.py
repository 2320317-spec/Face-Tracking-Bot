# =============================================================================
# Step 4 - decision logic (webcam)
# =============================================================================
# Finds the yellow target (like step 2) and lets the brain (pi/brain.py) decide
# what the robot would do. No motors yet - the decision is drawn on screen:
#   state   FOLLOW / HOLD / BACK   (distance, from the target's width w)
#           SEARCHING left/right   (target lost: the robot would sweep to find it -
#                                   here the webcam can't turn, so just step back into view)
#   command fwd and turn, each -100..100 %, plus the same thing in words
#   wheels  two bars in the bottom corners: up = forward (green), down = reverse (red)
#
# Thresholds (stop distance, dead zone, speeds, search...) live in pi/brain.py,
# the color ranges (COLOR, COLORS) in pi/vision.py - the same files the robot uses.
# Color mode follows the first yellow thing it finds - there's no "who" for colors.
#
# Run:  .venv\Scripts\python steps\04_decision.py
# Keys: q = quit (click the video window first)
# =============================================================================
import os
import sys
import time

import cv2

# Use the robot's own code in pi/ (brain.py, vision.py), so there's only one copy to tune
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi"))
from brain import W, H, DEAD_ZONE, ALIGN_ZONE, Follower, wheels, describe
from vision import find_color          # step 2's color detection: returns (box, mask)

CAMERA = 0             # which camera: 0 = first, 1 = second


# ---- Drawing helpers -----------------------------------------------------------------
def draw_zones(frame):
    """The steering zones from brain.py:
    gray band   = dead zone: target inside it counts as centered, no turning
    dark lines  = align zone: target outside them -> spin in place, don't drive"""
    cv2.rectangle(frame, (W // 2 - DEAD_ZONE, 0), (W // 2 + DEAD_ZONE, H), (90, 90, 90), 1)
    for x in (W // 2 - ALIGN_ZONE, W // 2 + ALIGN_ZONE):
        cv2.line(frame, (x, 0), (x, H), (60, 60, 60), 1)


def draw_wheel(frame, x, speed, label):
    """One wheel as a bar standing on a baseline: up = forward (green), down = reverse (red).
    100 % = 50 pixels tall."""
    base = H - 70                               # y of the baseline
    top = base - int(speed * 0.5)               # other end of the bar
    color = (0, 200, 0) if speed >= 0 else (0, 0, 255)
    cv2.rectangle(frame, (x, min(base, top)), (x + 16, max(base, top)), color, -1)
    cv2.line(frame, (x - 4, base), (x + 20, base), (255, 255, 255), 1)
    cv2.putText(frame, f"{label} {speed}", (x - 6, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


# Color of the state text, by what the brain is doing (see brain.py, Follower.status)
STATE_COLORS = {"follow": (0, 200, 0), "hold": (0, 220, 255), "back": (0, 0, 255),   # green, yellow, red
                "search": (0, 140, 255), "lost": (160, 160, 160), "idle": (160, 160, 160)}  # orange, gray, gray


# ---- Open the camera (same as step 1) ------------------------------------------------
cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

bot = Follower()       # the brain - it remembers its state (follow/hold/back) between frames
fps = 0.0
frames = 0
t0 = time.time()


# ---- The loop ------------------------------------------------------------------------
while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # 1. find the target   2. brain decides   3. (step 6: send the command to the Uno)
    box, mask = find_color(frame)
    target = None if box is None else (box[0] + box[2] // 2, box[2])   # (center x, width w)
    fwd, turn = bot.update(target, "color")

    # ---- draw what the robot sees and decides ----
    draw_zones(frame)
    if box is not None:
        x, y, w, h = box
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(frame, (target[0], y + h // 2), 4, (0, 0, 255), -1)
        cv2.putText(frame, f"x={target[0]}  w={w}", (x, max(y - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    # What the brain is doing: FOLLOW / HOLD / BACK, LOST - keep going (a flicker),
    # SEARCHING left/right (sweeping to find it), NO TARGET - waiting (gave up)
    state_text, kind = bot.status()
    cv2.putText(frame, f"state: {state_text}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, STATE_COLORS[kind], 2)
    cv2.putText(frame, f"fwd {fwd}  turn {turn}", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, describe(fwd, turn), (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    left, right = wheels(fwd, turn)            # what each wheel would do
    draw_wheel(frame, 20, left, "L")
    draw_wheel(frame, W - 40, right, "R")

    # FPS, same as step 1
    frames = frames + 1
    now = time.time()
    if now - t0 >= 1:
        fps = frames / (now - t0)
        frames = 0
        t0 = now
    cv2.putText(frame, f"{fps:.1f} fps", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow("Live feed", frame)
    cv2.imshow("Mask", mask)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
