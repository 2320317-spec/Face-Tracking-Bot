# Step 5 - face detection, two modes (press s to switch):
#   SIMPLE - follow the biggest face, exactly as it is in each frame (the basic version)
#   SMART  - lock onto one face and stay on it, smooth its position and size,
#            and show the face details (5 landmarks, head turn, distance)
# Both feed the same brain as step 4 (brain.py).
# Needs: pi/models/face_detection_yunet_2023mar.onnx  (see pi/models/README.md)
# Run:  .venv\Scripts\python steps\05_face_detect.py
# Keys: s = simple/smart   click a face = lock onto it   l = let go of the lock   q = quit
import math
import os
import sys
import time

import cv2

from brain import W, H, DEAD_ZONE, ALIGN_ZONE, LOST_GRACE, Follower, wheels, describe

CAMERA = 0
MODEL = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "pi", "models", "face_detection_yunet_2023mar.onnx"))
SCORE_MIN = 0.7        # how sure the detector must be (0 to 1) before it counts as a face

MODE = "smart"         # which mode to start in: "smart" or "simple"
SMOOTH = 0.4           # smart: how fast the smoothed x and w move toward each new value (0-1, lower = smoother)
LOCK_TIMEOUT = 15      # smart: frames the locked face may be missing before the lock is released
FACE_WIDTH_M = 0.15    # a typical face is about 15 cm wide - used for the distance estimate
FOCAL = (W / 2) / math.tan(math.radians(60) / 2)   # ~416 px for a 60 degree webcam

FONT = cv2.FONT_HERSHEY_SIMPLEX
STATE_COLORS = {"follow": (0, 200, 0), "hold": (0, 220, 255), "back": (0, 0, 255)}

if not os.path.exists(MODEL):
    sys.exit("Face model not found - download it first, see pi/models/README.md")
detector = cv2.FaceDetectorYN.create(MODEL, "", (W, H), score_threshold=SCORE_MIN)


# ---------------- finding faces ----------------
def find_faces(frame):
    """All faces in the frame, widest (closest) first.
    Each face: {"box": (x, y, w, h), "points": five (x, y) landmarks, "score": 0-1}
    Landmarks in order: right eye, left eye, nose tip, right mouth corner, left mouth corner."""
    _, rows = detector.detect(frame)        # one row of 15 numbers per face
    if rows is None:
        return []
    faces = []
    for f in sorted(rows, key=lambda f: f[2], reverse=True):
        faces.append({
            "box": tuple(int(v) for v in f[:4]),
            "points": [(int(f[4 + 2 * i]), int(f[5 + 2 * i])) for i in range(5)],
            "score": float(f[14]),
        })
    return faces


def center(face):
    x, y, w, h = face["box"]
    return x + w / 2, y + h / 2


def inside(point, box):
    x, y, w, h = box
    return x <= point[0] <= x + w and y <= point[1] <= y + h


class FaceLock:
    """SMART mode: stay on one face, and smooth its position (x) and size (w)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.face = None        # the face we are locked on, as last seen
        self.missing = 0        # frames since we last saw it
        self.x = self.w = None  # smoothed center x and width
        self.click = None       # (x, y) of a mouse click: lock onto the face there

    def update(self, faces):
        """Find our face in this frame. Returns it, or None if it isn't there."""
        if self.click is not None:                          # clicked on a face: switch to it
            hit = [f for f in faces if inside(self.click, f["box"])]
            self.click = None
            if hit:
                self.face, self.x, self.w = hit[0], None, None
        if self.face is None:                               # nothing locked: take the closest face
            found = faces[0] if faces else None
        else:                                               # look for our face near where it was
            last, last_w = center(self.face), self.face["box"][2]
            reach = max(80, 3 * last_w)     # how far it may move in one frame (the robot turning shifts it a lot)
            near = [f for f in faces
                    if math.dist(center(f), last) < reach and 0.6 < f["box"][2] / last_w < 1.6]
            found = min(near, key=lambda f: math.dist(center(f), last)) if near else None
        if found is None:
            self.missing += 1
            if self.missing > LOCK_TIMEOUT:                 # gone too long: let go
                self.face, self.x, self.w = None, None, None
            return None
        self.face, self.missing = found, 0
        x, y, w, h = found["box"]
        if self.x is None:                                  # first frame: start from here
            self.x, self.w = x + w / 2, float(w)
        else:                                               # move part of the way to the new value
            self.x += SMOOTH * (x + w / 2 - self.x)
            self.w += SMOOTH * (w - self.w)
        return found


def head_turn(face):
    """Which way the head is turned (as seen in the picture), from where the nose sits between the eyes."""
    right_eye, left_eye, nose = face["points"][:3]
    eye_middle = (right_eye[0] + left_eye[0]) / 2
    eye_gap = math.dist(right_eye, left_eye) or 1
    offset = (nose[0] - eye_middle) / eye_gap       # 0 = looking straight at the camera
    if offset > 0.15:
        return "right", offset
    if offset < -0.15:
        return "left", offset
    return "straight", offset


# ---------------- drawing ----------------
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
    cv2.putText(frame, f"{label} {speed}", (x - 6, H - 8), FONT, 0.45, (255, 255, 255), 1)


def draw_simple(frame, face):
    """SIMPLE mode: box, eyes, and the raw x / w."""
    x, y, w, h = face["box"]
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    for ex, ey in face["points"][:2]:
        cv2.circle(frame, (ex, ey), 3, (255, 255, 0), -1)
    cv2.putText(frame, f"x={x + w // 2}  w={w}  {face['score']:.0%}", (x, max(y - 8, 15)),
                FONT, 0.55, (0, 255, 0), 2)


def draw_details(frame, face, smooth_x, smooth_w):
    """SMART mode: locked box, all 5 landmarks, head turn, distance, certainty."""
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
    if turn_text != "straight":                             # arrow: where the nose points
        tip = (int(nose[0] + offset * w * 0.8), nose[1])
        cv2.arrowedLine(frame, nose, tip, (0, 165, 255), 2, tipLength=0.4)

    # yellow cross = the smoothed center the brain actually uses
    cv2.drawMarker(frame, (int(smooth_x), y + h // 2), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)

    distance = FOCAL * FACE_WIDTH_M / smooth_w
    cv2.putText(frame, f"LOCKED  x={round(smooth_x)} w={round(smooth_w)}", (x, max(y - 8, 15)),
                FONT, 0.5, (0, 255, 0), 2)
    cv2.putText(frame, f"~{distance:.1f} m  head {turn_text}  {face['score']:.0%}",
                (x, min(y + h + 18, H - 80)), FONT, 0.45, (0, 255, 255), 1)


# ---------------- main loop ----------------
cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

mode = MODE
bot = Follower()
lock = FaceLock()


def on_click(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        lock.click = (x, y)


cv2.namedWindow("Live feed")
cv2.setMouseCallback("Live feed", on_click)

fps = 0.0
frames = 0
t0 = time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # 1. find faces   2. pick the one to follow   3. brain decides   4. (later: send to the Uno)
    faces = find_faces(frame)
    if mode == "simple":                                    # biggest face, as it is right now
        followed = faces[0] if faces else None
        target = None
        if followed is not None:
            x, y, w, h = followed["box"]
            target = (x + w // 2, w)
    else:                                                   # our locked face, smoothed
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
        if mode == "smart" and lock.face is not None:       # lock kept: show where we last saw it
            fx, fy, fw, fh = lock.face["box"]
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 220, 255), 1)
            cv2.putText(frame, f"searching... {LOCK_TIMEOUT - lock.missing}", (fx, max(fy - 8, 15)),
                        FONT, 0.45, (0, 220, 255), 1)
        if bot.lost <= LOST_GRACE:
            state_text, state_color = "LOST - keep going", (160, 160, 160)
        else:
            state_text, state_color = "NO FACE", (160, 160, 160)

    cv2.putText(frame, mode.upper(), (W - 80, 25), FONT, 0.6, (0, 255, 255), 2)
    cv2.putText(frame, f"state: {state_text}   faces: {len(faces)}", (10, 50), FONT, 0.6, state_color, 2)
    cv2.putText(frame, f"fwd {fwd}  turn {turn}", (10, 75), FONT, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, describe(fwd, turn), (10, 100), FONT, 0.6, (255, 255, 0), 2)
    cv2.putText(frame, "s: simple/smart  click: lock  l: unlock  q: quit", (80, H - 8),
                FONT, 0.4, (200, 200, 200), 1)

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
    cv2.putText(frame, f"{fps:.1f} fps", (10, 25), FONT, 0.6, (0, 255, 0), 2)

    cv2.imshow("Live feed", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    if key == ord('s'):                                     # switch mode, start fresh
        mode = "simple" if mode == "smart" else "smart"
        bot.reset()
        lock.reset()
    if key == ord('l'):                                     # let go: next frame locks the closest face
        lock.reset()

cap.release()
cv2.destroyAllWindows()
