# =============================================================================
# Step 5 - face detection, two modes (press s to switch)
# =============================================================================
#   SIMPLE - follow the biggest face, exactly as it is in each frame.
#            Lost you? The robot sweeps left and right and follows the FIRST
#            person it sees, whoever it is.
#   SMART  - lock onto ONE person and remember what their face looks like.
#            Lost you? It sweeps left and right looking for YOU - other people
#            are ignored ("not you") - and follows you again when it finds you.
#            Also shows face details: 5 landmarks, head turn, distance.
# Both hand the face's x and w to the robot's brain (pi/brain.py), in "face"
# mode. The brain does the searching (the sweep); this file decides WHO counts.
# (The webcam can't turn, so here you'll see "SEARCHING left/right" and the wheel
#  bars - step back into view to be found. Watch the real sweep in step 4b.)
#
# The face code and ALL its settings (SCORE_MIN, SMOOTH, MATCH, LOCK_..., LEARN_...)
# live in pi/vision.py - the same file the robot uses:
#   FaceTools  the two models: YuNet finds faces (box, 5 landmarks, certainty),
#              SFace turns a face into a "fingerprint" of 128 numbers to recognize it
#   FaceLock   SMART's memory: where you are, and what your face looks like
# Everything runs on this computer; fingerprints are never saved to disk.
#
# Run:   .venv\Scripts\python steps\05_face_detect.py
# Keys:  s = simple/smart   click a face = "this is me"   l = forget me   q = quit
# =============================================================================
import os
import sys
import time

import cv2

# Use the robot's own code in pi/ (brain.py, vision.py), so there's only one copy to tune
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi"))
from brain import W, H, DEAD_ZONE, ALIGN_ZONE, Follower, wheels, describe
from vision import FaceTools, FaceLock, head_turn, LEARN_MAX, FOCAL, FACE_WIDTH_M


# ---- Settings ---------------------------------------------------------------------
CAMERA = 1             # which camera: 0 = first, 1 = second
MODE = "smart"         # which mode to start in: "smart" or "simple"

FONT = cv2.FONT_HERSHEY_SIMPLEX
# Color of the state text, by what the brain is doing (see brain.py, Follower.status)
STATE_COLORS = {"follow": (0, 200, 0), "hold": (0, 220, 255), "back": (0, 0, 255),   # green, yellow, red
                "search": (0, 140, 255), "lost": (160, 160, 160), "idle": (160, 160, 160)}  # orange, gray, gray


# ---- Drawing -------------------------------------------------------------------------
def draw_zones(frame):
    """The steering zones from brain.py:
    gray band  = dead zone: face inside it counts as centered, no turning
    dark lines = align zone: face outside them -> spin in place, don't drive"""
    cv2.rectangle(frame, (W // 2 - DEAD_ZONE, 0), (W // 2 + DEAD_ZONE, H), (90, 90, 90), 1)
    for x in (W // 2 - ALIGN_ZONE, W // 2 + ALIGN_ZONE):
        cv2.line(frame, (x, 0), (x, H), (60, 60, 60), 1)


def draw_wheel(frame, x, speed, label):
    """One wheel as a bar: up = forward (green), down = reverse (red). 100 % = 50 px."""
    base = H - 70
    top = base - int(speed * 0.5)
    color = (0, 200, 0) if speed >= 0 else (0, 0, 255)
    cv2.rectangle(frame, (x, min(base, top)), (x + 16, max(base, top)), color, -1)
    cv2.line(frame, (x - 4, base), (x + 20, base), (255, 255, 255), 1)
    cv2.putText(frame, f"{label} {speed}", (x - 6, H - 8), FONT, 0.45, (255, 255, 255), 1)


def draw_simple(frame, face):
    """SIMPLE mode: box, eyes, and the raw x / w / certainty."""
    x, y, w, h = face["box"]
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    for ex, ey in face["points"][:2]:                   # the first two landmarks = the eyes
        cv2.circle(frame, (ex, ey), 3, (255, 255, 0), -1)
    cv2.putText(frame, f"x={x + w // 2}  w={w}  {face['score']:.0%}", (x, max(y - 8, 15)),
                FONT, 0.55, (0, 255, 0), 2)


def draw_details(frame, face, smooth_x, smooth_w, name, match):
    """SMART mode: your box, all 5 landmarks, head-turn arrow, distance, certainty, match."""
    x, y, w, h = face["box"]
    right_eye, left_eye, nose, right_mouth, left_mouth = face["points"]
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.line(frame, right_eye, left_eye, (255, 255, 0), 1)
    cv2.line(frame, right_mouth, left_mouth, (255, 0, 255), 1)
    for p in (right_eye, left_eye):
        cv2.circle(frame, p, 3, (255, 255, 0), -1)          # eyes: cyan
    cv2.circle(frame, nose, 3, (0, 165, 255), -1)           # nose: orange
    for p in (right_mouth, left_mouth):
        cv2.circle(frame, p, 3, (255, 0, 255), -1)          # mouth corners: pink

    turn_text, offset = head_turn(face)
    if turn_text != "straight":                             # arrow from the nose: which way it points
        tip = (int(nose[0] + offset * w * 0.8), nose[1])
        cv2.arrowedLine(frame, nose, tip, (0, 165, 255), 2, tipLength=0.4)

    # yellow cross = the smoothed center - this is what the brain actually steers by
    cv2.drawMarker(frame, (int(smooth_x), y + h // 2), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)

    distance = FOCAL * FACE_WIDTH_M / smooth_w              # estimate, in meters
    cv2.putText(frame, f"{name}  x={round(smooth_x)} w={round(smooth_w)}", (x, max(y - 8, 15)),
                FONT, 0.5, (0, 255, 0), 2)
    details = f"~{distance:.1f} m  head {turn_text}  face {face['score']:.0%}"
    if match is not None:
        details += f"  match {match:.2f}"                  # how much it looks like you (0-1)
    cv2.putText(frame, details, (x, min(y + h + 18, H - 80)), FONT, 0.45, (0, 255, 255), 1)


# ---- Open the camera (same as step 1) ------------------------------------------------
cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

mode = MODE
tools = FaceTools()    # the face models (finding + recognizing)
bot = Follower()       # the brain (follow / hold / back / search)
lock = FaceLock(tools) # SMART mode's memory: where you are and who you are


def on_click(event, x, y, flags, param):
    """Mouse click in the video window: "this face is me"."""
    if event == cv2.EVENT_LBUTTONDOWN:
        lock.click = (x, y)


cv2.namedWindow("Live feed")                    # create the window first, so the mouse can be attached
cv2.setMouseCallback("Live feed", on_click)

fps = 0.0
frames = 0
t0 = time.time()


# ---- The loop ------------------------------------------------------------------------
while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # 1. find faces   2. pick who to follow   3. brain decides (incl. searching)   4. (step 6: to the Uno)
    faces = tools.find(frame)
    if mode == "simple":                                    # SIMPLE: biggest face, whoever it is
        followed = faces[0] if faces else None
        target = None
        if followed is not None:
            x, y, w, h = followed["box"]
            target = (x + w // 2, w)
    else:                                                   # SMART: only you, smoothed
        followed = lock.update(frame, faces)
        target = (round(lock.x), round(lock.w)) if followed is not None else None
    fwd, turn = bot.update(target, "face")

    # ---- draw what the robot sees and decides ----
    draw_zones(frame)
    checked = {id(f): sim for f, sim in lock.checked} if mode == "smart" else {}
    for f in faces:                                         # faces we are NOT following: thin gray
        if f is not followed:
            fx, fy, fw, fh = f["box"]
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (160, 160, 160), 1)
            if id(f) in checked:                            # SMART compared it with you: say so
                cv2.putText(frame, f"not you {checked[id(f)]:.2f}", (fx, max(fy - 6, 15)),
                            FONT, 0.45, (160, 160, 160), 1)
    if followed is not None:
        if mode == "simple":
            draw_simple(frame, followed)
        else:
            draw_details(frame, followed, lock.x, lock.w,
                         "YOU" if lock.knows_you() else "LOCKED", lock.similarity)
    elif mode == "smart" and lock.face is not None:         # just lost you: show where you were
        fx, fy, fw, fh = lock.face["box"]
        cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 220, 255), 1)
        cv2.putText(frame, "last seen", (fx, max(fy - 8, 15)), FONT, 0.45, (0, 220, 255), 1)

    # What the brain is doing: FOLLOW / HOLD / BACK, LOST - keep going (a flicker),
    # SEARCHING left/right (sweeping to find you), NO TARGET - waiting (gave up)
    state_text, kind = bot.status()
    cv2.putText(frame, mode.upper(), (W - 80, 25), FONT, 0.6, (0, 255, 255), 2)
    cv2.putText(frame, f"state: {state_text}   faces: {len(faces)}", (10, 50), FONT, 0.6, STATE_COLORS[kind], 2)
    cv2.putText(frame, f"fwd {fwd}  turn {turn}", (10, 75), FONT, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, describe(fwd, turn), (10, 100), FONT, 0.6, (255, 255, 0), 2)
    if mode == "smart":                                     # does SMART know who you are?
        if tools.recognizer is None:
            who = "no recognition model: follows by position only"
        elif lock.knows_you():
            who = f"knows you: {len(lock.prints)}/{LEARN_MAX} fingerprints"
        else:
            who = "doesn't know you yet: next face = you"
        cv2.putText(frame, who, (10, 125), FONT, 0.5, (0, 255, 255), 1)
    cv2.putText(frame, "s: simple/smart  click: this is me  l: forget me  q: quit", (60, H - 8),
                FONT, 0.4, (200, 200, 200), 1)

    left, right = wheels(fwd, turn)                         # what each wheel would do
    draw_wheel(frame, 20, left, "L")
    draw_wheel(frame, W - 40, right, "R")

    # FPS, same as step 1
    frames = frames + 1
    now = time.time()
    if now - t0 >= 1:
        fps = frames / (now - t0)
        frames = 0
        t0 = now
    cv2.putText(frame, f"{fps:.1f} fps", (10, 25), FONT, 0.6, (0, 255, 0), 2)

    cv2.imshow("Live feed", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    if key == ord('s'):                                     # switch mode and start fresh
        mode = "simple" if mode == "smart" else "smart"
        bot.reset()
        lock.reset()
    if key == ord('l'):                                     # forget who you are: next face = you
        lock.reset()

cap.release()
cv2.destroyAllWindows()
