# Step 2 - live color detection
# Finds the biggest blob of one color, draws a box around it, and shows its
# center x and width w - the two numbers the robot will steer and drive by.
# Run:  .venv\Scripts\python steps\02_color_detect.py      Quit: press q in the video window
import sys
import time

import cv2
import numpy as np

CAMERA = 0             # which camera? 0 = first, 1 = second
W, H = 480, 360        # size the robot works at

COLOR = "green"        # which color to look for (a name from COLORS)
COLORS = {             # HSV low, HSV high  (OpenCV hue goes 0-179)
    "green":  ((40, 100, 80),  (80, 255, 255)),
    "orange": ((10, 150, 100), (25, 255, 255)),
}
MIN_AREA = 300                       # blobs smaller than this many pixels are noise
KERNEL = np.ones((3, 3), np.uint8)   # small square used to clean specks out of the mask


def find_color(frame):
    """Return (box, mask). box = (x, y, w, h) of the biggest COLOR blob, or None."""
    lo, hi = COLORS[COLOR]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))       # white where the color matches
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)     # remove tiny specks
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, mask
    biggest = max(contours, key=cv2.contourArea)              # closest / largest object
    if cv2.contourArea(biggest) < MIN_AREA:
        return None, mask
    return cv2.boundingRect(biggest), mask


cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

fps = 0.0
frames = 0
t0 = time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    box, mask = find_color(frame)

    # White line = middle of the frame. The robot will turn to put the target on it.
    cv2.line(frame, (W // 2, 0), (W // 2, H), (255, 255, 255), 1)

    if box is not None:
        x, y, w, h = box
        cx = x + w // 2                                    # center x of the target
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(frame, (cx, y + h // 2), 4, (0, 0, 255), -1)
        cv2.putText(frame, f"x={cx}  w={w}", (x, max(y - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    else:
        cv2.putText(frame, "no target", (10, H - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # FPS, same as step 1
    frames = frames + 1
    now = time.time()
    if now - t0 >= 1:
        fps = frames / (now - t0)
        frames = 0
        t0 = now
    cv2.putText(frame, f"{fps:.1f} fps", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("Live feed", frame)
    cv2.imshow("Mask", mask)               # what the computer "sees" as your color

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
