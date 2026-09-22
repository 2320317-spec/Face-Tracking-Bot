# =============================================================================
# Step 5 - face detection, two modes (press s to switch)
# =============================================================================
#   SIMPLE - follow the biggest face, exactly as it is in each frame (the basic version)
#   SMART  - lock onto ONE face and stay on it, smooth its position and size,
#            and show the face details (5 landmarks, head turn, distance)
# Both hand the face's x and w to the same brain as step 4 (brain.py), in "face"
# mode - so the face distance thresholds in brain.py are used.
#
# The face detector is YuNet, built into OpenCV. For every face it gives 15 numbers:
#   [0-3]   the box: x, y, w, h
#   [4-13]  5 landmarks, (x, y) each: right eye, left eye, nose tip,
#           right mouth corner, left mouth corner  ("right" = the person's right)
#   [14]    how sure it is that this is a face, 0 to 1
#
# Needs: pi/models/face_detection_yunet_2023mar.onnx  (see pi/models/README.md)
# Run:   .venv\Scripts\python steps\05_face_detect.py
# Keys:  s = simple/smart   click a face = lock onto it   l = let go of the lock   q = quit
# =============================================================================
import math
import os
import sys
import time

import cv2

from brain import W, H, DEAD_ZONE, ALIGN_ZONE, LOST_GRACE, Follower, wheels, describe


# ---- Settings: camera and detector -------------------------------------------------
CAMERA = 0             # which camera: 0 = first, 1 = second
MODEL = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "pi", "models", "face_detection_yunet_2023mar.onnx"))
SCORE_MIN = 0.7        # How sure (0 to 1) the detector must be before something counts as a face.
                       #   Real faces get missed (dim light, far away) -> lower it, e.g. 0.6
                       #   Random things get boxed as faces           -> raise it, e.g. 0.8

MODE = "smart"         # which mode to start in: "smart" or "simple"


# ---- Settings: SMART mode ----------------------------------------------------------
SMOOTH = 0.4           # Smoothing: each frame, the smoothed x and w move 40 % of the way
                       # toward the new measurement. e.g. smoothed w = 40, new w = 50 -> 44.
                       #   Box / steering still jittery -> lower it (0.2 = smoother)
                       #   Reacts too late when you move -> raise it (1.0 = no smoothing)

LOCK_TIMEOUT = 15      # How many frames (~1 s) the locked face may be missing before we
                       # give up on it and take the closest face again.

LOCK_REACH_MIN = 80    # How far (px) the locked face may move between two frames and still
LOCK_REACH = 3         # count as "the same face": at least 80 px, or 3x the face's width.
                       # Big on purpose: when the robot turns, the whole picture shifts.
                       #   Lock lost when the robot spins      -> raise it
                       #   Lock jumps to a person next to you  -> lower it

LOCK_SIZE_MIN = 0.6    # The same face can't suddenly change size a lot: a face only counts
LOCK_SIZE_MAX = 1.6    # if it's 0.6x to 1.6x the locked face's width. Stops the lock jumping
                       # to someone much nearer or much farther away.

HEAD_TURN = 0.15       # How far the nose must be off the middle of the eyes (as a fraction of the
                       # eye gap) to count as "head turned". Lower = notices smaller turns.

FACE_WIDTH_M = 0.15    # A typical face is about 15 cm wide - used for the distance estimate.
FOCAL = (W / 2) / math.tan(math.radians(60) / 2)   # ~416 px for a 60 degree webcam.
                       # Distance = FOCAL x FACE_WIDTH_M / w. If "~m" is off for your webcam,
                       # change the 60 to your camera's field of view.

FONT = cv2.FONT_HERSHEY_SIMPLEX
STATE_COLORS = {"follow": (0, 200, 0), "hold": (0, 220, 255), "back": (0, 0, 255)}   # green, yellow, red

if not os.path.exists(MODEL):
    sys.exit("Face model not found - download it first, see pi/models/README.md")
# Load YuNet once. It's told the picture size (W, H) so every frame must be that size.
detector = cv2.FaceDetectorYN.create(MODEL, "", (W, H), score_threshold=SCORE_MIN)


# ---- Finding faces -------------------------------------------------------------------
def find_faces(frame):
    """All faces in the frame, widest (= closest) first.
    Each face is a dictionary:
      "box"    (x, y, w, h)
      "points" five (x, y) landmarks: right eye, left eye, nose, right mouth, left mouth
      "score"  how sure the detector is, 0 to 1"""
    _, rows = detector.detect(frame)        # rows = one row of 15 numbers per face, or None
    if rows is None:
        return []
    faces = []
    for f in sorted(rows, key=lambda f: f[2], reverse=True):     # sort by width, biggest first
        faces.append({
            "box": tuple(int(v) for v in f[:4]),
            "points": [(int(f[4 + 2 * i]), int(f[5 + 2 * i])) for i in range(5)],
            "score": float(f[14]),
        })
    return faces


def center(face):
    """Middle of a face's box."""
    x, y, w, h = face["box"]
    return x + w / 2, y + h / 2


def inside(point, box):
    """Is the point (a mouse click) inside the box?"""
    x, y, w, h = box
    return x <= point[0] <= x + w and y <= point[1] <= y + h


class FaceLock:
    """SMART mode: stay on one face, and smooth its position (x) and size (w).
    Each frame it looks for "our" face near where it was last time, at a similar size.
    Note: it tells people apart by POSITION, not by who they are - if two people cross
    paths it can end up on the wrong one (face recognition would fix that later)."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget the locked face (used by the l key and when switching modes)."""
        self.face = None        # the face we are locked on, as last seen
        self.missing = 0        # frames since we last saw it
        self.x = self.w = None  # smoothed center x and width (what the brain gets)
        self.click = None       # (x, y) of a mouse click: lock onto the face there

    def update(self, faces):
        """Find our face among this frame's faces. Returns it, or None if it isn't there."""

        # -- A mouse click on a face: switch the lock to that face --
        if self.click is not None:
            hit = [f for f in faces if inside(self.click, f["box"])]
            self.click = None
            if hit:
                self.face, self.x, self.w = hit[0], None, None      # None = restart smoothing

        # -- Which face is ours this frame? --
        if self.face is None:                       # nothing locked yet: take the closest face
            found = faces[0] if faces else None
        else:                                       # look for our face near where it was
            last, last_w = center(self.face), self.face["box"][2]
            reach = max(LOCK_REACH_MIN, LOCK_REACH * last_w)        # how far it may have moved
            near = [f for f in faces
                    if math.dist(center(f), last) < reach                       # close enough, and
                    and LOCK_SIZE_MIN < f["box"][2] / last_w < LOCK_SIZE_MAX]   # a similar size
            found = min(near, key=lambda f: math.dist(center(f), last)) if near else None   # nearest one

        # -- Not found: count, and give up after LOCK_TIMEOUT frames --
        if found is None:
            self.missing += 1
            if self.missing > LOCK_TIMEOUT:
                self.face, self.x, self.w = None, None, None
            return None

        # -- Found: remember it and update the smoothed x and w --
        self.face, self.missing = found, 0
        x, y, w, h = found["box"]
        if self.x is None:                          # first frame: start from the real values
            self.x, self.w = x + w / 2, float(w)
        else:                                       # then move SMOOTH (40 %) of the way each frame
            self.x += SMOOTH * (x + w / 2 - self.x)
            self.w += SMOOTH * (w - self.w)
        return found


def head_turn(face):
    """Which way the head is turned, as seen in the picture.
    Looking straight at the camera, the nose sits halfway between the eyes.
    Turning the head moves the nose toward one side.
    Returns ("straight" / "left" / "right", offset) - offset = how far the nose is off,
    as a fraction of the gap between the eyes."""
    right_eye, left_eye, nose = face["points"][:3]
    eye_middle = (right_eye[0] + left_eye[0]) / 2
    eye_gap = math.dist(right_eye, left_eye) or 1   # "or 1": never divide by zero
    offset = (nose[0] - eye_middle) / eye_gap
    if offset > HEAD_TURN:
        return "right", offset
    if offset < -HEAD_TURN:
        return "left", offset
    return "straight", offset


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


def draw_details(frame, face, smooth_x, smooth_w):
    """SMART mode: locked box, all 5 landmarks, head-turn arrow, distance, certainty."""
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
    cv2.putText(frame, f"LOCKED  x={round(smooth_x)} w={round(smooth_w)}", (x, max(y - 8, 15)),
                FONT, 0.5, (0, 255, 0), 2)
    cv2.putText(frame, f"~{distance:.1f} m  head {turn_text}  {face['score']:.0%}",
                (x, min(y + h + 18, H - 80)), FONT, 0.45, (0, 255, 255), 1)   # below the box, above the wheel bars


# ---- Open the camera (same as step 1) ------------------------------------------------
cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

mode = MODE
bot = Follower()       # the brain (remembers follow / hold / back between frames)
lock = FaceLock()      # SMART mode's memory of which face we're on


def on_click(event, x, y, flags, param):
    """Mouse click in the video window: ask the lock to switch to the face there."""
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

    # 1. find faces   2. pick the one to follow   3. brain decides   4. (step 6: send to the Uno)
    faces = find_faces(frame)
    if mode == "simple":                                    # SIMPLE: biggest face, as it is right now
        followed = faces[0] if faces else None
        target = None
        if followed is not None:
            x, y, w, h = followed["box"]
            target = (x + w // 2, w)
    else:                                                   # SMART: our locked face, smoothed
        followed = lock.update(faces)
        target = (round(lock.x), round(lock.w)) if followed is not None else None
    fwd, turn = bot.update(target, "face")

    # ---- draw what the robot sees and decides ----
    draw_zones(frame)
    for f in faces:                                         # faces we are NOT following: thin gray
        if f is not followed:
            fx, fy, fw, fh = f["box"]
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (160, 160, 160), 1)
    if followed is not None:
        if mode == "simple":
            draw_simple(frame, followed)
        else:
            draw_details(frame, followed, lock.x, lock.w)
        state_text, state_color = bot.state.upper(), STATE_COLORS[bot.state]
    else:
        if mode == "smart" and lock.face is not None:       # lock still waiting: show where we last saw it
            fx, fy, fw, fh = lock.face["box"]
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 220, 255), 1)
            cv2.putText(frame, f"searching... {LOCK_TIMEOUT - lock.missing}", (fx, max(fy - 8, 15)),
                        FONT, 0.45, (0, 220, 255), 1)
        if bot.lost <= LOST_GRACE:                          # the brain's short grace period
            state_text, state_color = "LOST - keep going", (160, 160, 160)
        else:
            state_text, state_color = "NO FACE", (160, 160, 160)

    cv2.putText(frame, mode.upper(), (W - 80, 25), FONT, 0.6, (0, 255, 255), 2)
    cv2.putText(frame, f"state: {state_text}   faces: {len(faces)}", (10, 50), FONT, 0.6, state_color, 2)
    cv2.putText(frame, f"fwd {fwd}  turn {turn}", (10, 75), FONT, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, describe(fwd, turn), (10, 100), FONT, 0.6, (255, 255, 0), 2)
    cv2.putText(frame, "s: simple/smart  click: lock  l: unlock  q: quit", (80, H - 8),
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
    if key == ord('l'):                                     # let go: next frame locks the closest face
        lock.reset()

cap.release()
cv2.destroyAllWindows()
