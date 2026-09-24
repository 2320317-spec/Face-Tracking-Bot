# =============================================================================
# Step 7 - hand gestures (on the PC, no robot needed)
# =============================================================================
# Shows your webcam with the 21 hand points drawn on, the gesture it thinks you
# are making, and the command it WOULD send the wheels. Nothing moves - this is
# for checking the gestures feel right before the robot obeys them.
#
# The signals:
#   one finger UP        -> forward
#   one finger LEFT      -> turn left
#   one finger RIGHT     -> turn right
#   two fingers          -> back up
#   fist                 -> stay put
#   open palm            -> STOP (on the robot this disengages it)
#
# Run:   .venv\Scripts\python steps\07_hand_gesture.py
# Keys:  f = flip left/right if it feels backwards   q = quit
#
# If nothing is detected: get closer (your hand must be about 45 px wide in the
# picture - roughly an arm's length), and make sure the room is lit.
# =============================================================================
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi"))
import gestures
from brain import W, H


# ---- Settings ---------------------------------------------------------------------
CAMERA = 0              # which camera: 0 = first (usually the built-in), 1 = second

FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN, GRAY, YELLOW, CYAN, ORANGE = ((0, 255, 0), (160, 160, 160), (0, 220, 255),
                                     (255, 255, 0), (0, 165, 255))

LINKS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
         (0, 9), (9, 10), (10, 11), (11, 12), (0, 13), (13, 14), (14, 15), (15, 16),
         (0, 17), (17, 18), (18, 19), (19, 20), (5, 9), (9, 13), (13, 17)]


cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    raise SystemExit(f"Camera {CAMERA} not found - try changing CAMERA at the top of this file")

hands = gestures.HandTools()
reader = gestures.GestureReader()
fps, frames, t0 = 0.0, 0, time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H))

    # ---- find the hand and name the gesture ----
    found = hands.find(frame)
    hand = found[0] if found else None
    seen = gestures.name_gesture(hand["points"])[0] if hand else None
    obeying = reader.update(seen)

    # ---- draw it ----
    if hand is not None:
        pts = hand["points"].astype(int)
        for a, b in LINKS:
            cv2.line(frame, tuple(pts[a]), tuple(pts[b]), GREEN if obeying else GRAY, 2)
        for i, p in enumerate(pts):
            cv2.circle(frame, tuple(p), 3, YELLOW if i in (4, 8, 12, 16, 20) else CYAN, -1)
        # the arrow along the index finger - this is what decides left / right / up
        cv2.arrowedLine(frame, tuple(pts[5]), tuple(pts[8]), ORANGE, 2, tipLength=0.3)

    command = gestures.COMMANDS.get(obeying)
    if command == gestures.STOP:
        text = "STOP"
    elif command is None:
        text = "waiting for a hand" if seen is None else f"{seen} (no command)"
    else:
        text = f"{obeying}  ->  fwd {command[0]}  turn {command[1]}"

    cv2.rectangle(frame, (0, H - 46), (W, H), (0, 0, 0), -1)
    cv2.putText(frame, text, (8, H - 26), FONT, 0.6, GREEN if obeying else GRAY, 2)
    hold = f"holding {int(reader.progress() * 100)}%" if reader.progress() else ""
    cv2.putText(frame, f"{fps:4.1f} fps   {hold}", (8, H - 8), FONT, 0.45, (200, 200, 200), 1)
    if gestures.POINT_FLIP:
        cv2.putText(frame, "flipped", (W - 70, H - 8), FONT, 0.45, ORANGE, 1)

    cv2.imshow("hand gestures  (f = flip left/right, q = quit)", frame)

    frames += 1
    now = time.time()
    if now - t0 >= 1:
        fps, frames, t0 = frames / (now - t0), 0, now

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    if key == ord('f'):                     # left and right feel the wrong way round?
        gestures.POINT_FLIP = not gestures.POINT_FLIP
        print("POINT_FLIP =", gestures.POINT_FLIP, "- put this in pi/gestures.py to keep it")

cap.release()
cv2.destroyAllWindows()
