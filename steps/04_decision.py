# Step 4 - decision logic (webcam)
# Finds the yellow target and lets the brain (brain.py) decide the robot's command.
# No motors yet: the command and both wheel speeds are drawn on screen.
# Run:  .venv\Scripts\python steps\04_decision.py      Quit: press q in the video window
import sys
import time

import cv2
import numpy as np

from brain import W, H, DEAD_ZONE, ALIGN_ZONE, LOST_GRACE, Follower, wheels, describe

CAMERA = 0

# ---------------- color detection (same as step 2) ----------------
COLOR = "yellow"
COLORS = {             # HSV low, HSV high  (OpenCV hue goes 0-179)
    "yellow": ((22, 120, 100), (38, 255, 255)),
    "green":  ((40, 100, 80),  (80, 255, 255)),
    "orange": ((10, 150, 100), (25, 255, 255)),
}
MIN_AREA = 300
KERNEL = np.ones((3, 3), np.uint8)


def find_color(frame):
    """Return (box, mask). box = (x, y, w, h) of the biggest COLOR blob, or None."""
    lo, hi = COLORS[COLOR]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, mask
    biggest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(biggest) < MIN_AREA:
        return None, mask
    return cv2.boundingRect(biggest), mask


def draw_zones(frame):
    """Gray band = dead zone (no turning). Dark lines = align zone (outside: spin in place)."""
    cv2.rectangle(frame, (W // 2 - DEAD_ZONE, 0), (W // 2 + DEAD_ZONE, H), (90, 90, 90), 1)
    for x in (W // 2 - ALIGN_ZONE, W // 2 + ALIGN_ZONE):
        cv2.line(frame, (x, 0), (x, H), (60, 60, 60), 1)


def draw_wheel(frame, x, speed, label):
    """One wheel as a bar: up = forward (green), down = reverse (red)."""
    base = H - 70
    top = base - int(speed * 0.5)               # 100% = 50 px
    color = (0, 200, 0) if speed >= 0 else (0, 0, 255)
    cv2.rectangle(frame, (x, min(base, top)), (x + 16, max(base, top)), color, -1)
    cv2.line(frame, (x - 4, base), (x + 20, base), (255, 255, 255), 1)
    cv2.putText(frame, f"{label} {speed}", (x - 6, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


STATE_COLORS = {"follow": (0, 200, 0), "hold": (0, 220, 255), "back": (0, 0, 255)}

cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

bot = Follower()
fps = 0.0
frames = 0
t0 = time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # 1. find the target   2. decide   3. (later: send to the Uno)
    box, mask = find_color(frame)
    target = None if box is None else (box[0] + box[2] // 2, box[2])
    fwd, turn = bot.update(target, "color")

    # ---- draw what the robot sees and decides ----
    draw_zones(frame)
    if box is not None:
        x, y, w, h = box
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(frame, (target[0], y + h // 2), 4, (0, 0, 255), -1)
        cv2.putText(frame, f"x={target[0]}  w={w}", (x, max(y - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        state_text, state_color = bot.state.upper(), STATE_COLORS[bot.state]
    elif bot.lost <= LOST_GRACE:
        state_text, state_color = "LOST - keep going", (160, 160, 160)
    else:
        state_text, state_color = "NO TARGET", (160, 160, 160)

    cv2.putText(frame, f"state: {state_text}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, state_color, 2)
    cv2.putText(frame, f"fwd {fwd}  turn {turn}", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, describe(fwd, turn), (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    left, right = wheels(fwd, turn)
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
