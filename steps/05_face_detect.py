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
# Both hand the face's x and w to the same brain as step 4 (brain.py), in "face"
# mode. The brain does the searching (the sweep); this file decides WHO counts.
# (The webcam can't turn, so here you'll see "SEARCHING left/right" and the wheel
#  bars - step back into view to be found. Watch the real sweep in step 4b.)
#
# Two models from OpenCV, both in pi/models/ (see pi/models/README.md):
#   YuNet - finds faces. For every face it gives 15 numbers:
#             [0-3]   the box: x, y, w, h
#             [4-13]  5 landmarks, (x, y) each: right eye, left eye, nose tip,
#                     right mouth corner, left mouth corner ("right" = the person's right)
#             [14]    how sure it is that this is a face, 0 to 1
#   SFace - recognizes faces. It turns a face into a "fingerprint" of 128 numbers:
#           the same person gives similar numbers, different people don't.
#           Everything runs on this computer; fingerprints are never saved to disk.
#
# Run:   .venv\Scripts\python steps\05_face_detect.py
# Keys:  s = simple/smart   click a face = "this is me"   l = forget me   q = quit
# =============================================================================
import math
import os
import sys
import time

import cv2

from brain import W, H, DEAD_ZONE, ALIGN_ZONE, Follower, wheels, describe


# ---- Settings: camera and models -------------------------------------------------
CAMERA = 1             # which camera: 0 = first, 1 = second
MODELS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "models"))
DETECT_MODEL = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")      # YuNet (needed)
RECOG_MODEL = os.path.join(MODELS, "face_recognition_sface_2021dec.onnx")     # SFace (for SMART)

SCORE_MIN = 0.7        # How sure (0 to 1) the detector must be before something counts as a face.
                       #   Real faces get missed (dim light, far away) -> lower it, e.g. 0.6
                       #   Random things get boxed as faces           -> raise it, e.g. 0.8

MODE = "smart"         # which mode to start in: "smart" or "simple"


# ---- Settings: SMART mode - following the same face ------------------------------------
SMOOTH = 0.4           # Smoothing: each frame, the smoothed x and w move 40 % of the way
                       # toward the new measurement. e.g. smoothed w = 40, new w = 50 -> 44.
                       #   Box / steering still jittery -> lower it (0.2 = smoother)
                       #   Reacts too late when you move -> raise it (1.0 = no smoothing)

LOCK_TIMEOUT = 15      # How many frames (~1 s) the locked face may be missing before we stop
                       # looking for it near its last spot. (With recognition, we still know
                       # who you are after that - we just search the whole picture.)

LOCK_REACH_MIN = 80    # How far (px) your face may move between two frames and still count as
LOCK_REACH = 3         # "the same face": at least 80 px, or 3x the face's width.
                       # Big on purpose: when the robot turns, the whole picture shifts.
                       #   Lock lost when the robot spins      -> raise it
                       #   Lock jumps to a person next to you  -> lower it

LOCK_SIZE_MIN = 0.6    # The same face can't suddenly change size a lot: a face only counts
LOCK_SIZE_MAX = 1.6    # if it's 0.6x to 1.6x the locked face's width. Stops the lock jumping
                       # to someone much nearer or much farther away.


# ---- Settings: SMART mode - recognizing YOU ------------------------------------------------
MATCH = 0.363          # How alike (0 to 1) two face fingerprints must be to count as the same
                       # person. 0.363 is OpenCV's recommended value. Tested: the same person
                       # scores 0.88-0.96, two different people 0.20.
                       #   Doesn't recognize you (other angle, light)  -> lower it a little, e.g. 0.30
                       #   Mistakes someone else for you              -> raise it, e.g. 0.45

TRUST_FRAMES = 2       # If your face was missing for more than 2 frames, don't trust "it's the
                       # face near where you were" any more - check the fingerprint first.

LEARN_EVERY = 5        # While following you, take another fingerprint every 5 frames. Each new one
                       # is also a check: if it doesn't match you, we drifted onto someone else
                       # (e.g. two people crossing) - so this is also how fast a mix-up gets caught.
                       #   Lower = catches mix-ups sooner, but more work for the Pi.
LEARN_MAX = 5          # Keep up to 5 fingerprints of you (different angles = more reliable).
                       # Speed: one fingerprint takes ~5-10 ms on a laptop, ~65 ms on the Pi 4 (measured).


# ---- Settings: face details ------------------------------------------------------------
HEAD_TURN = 0.15       # How far the nose must be off the middle of the eyes (as a fraction of the
                       # eye gap) to count as "head turned". Lower = notices smaller turns.

FACE_WIDTH_M = 0.15    # A typical face is about 15 cm wide - used for the distance estimate.
FOCAL = (W / 2) / math.tan(math.radians(60) / 2)   # ~416 px for a 60 degree webcam.
                       # Distance = FOCAL x FACE_WIDTH_M / w. If "~m" is off for your webcam,
                       # change the 60 to your camera's field of view.

FONT = cv2.FONT_HERSHEY_SIMPLEX
# Color of the state text, by what the brain is doing (see brain.py, Follower.status)
STATE_COLORS = {"follow": (0, 200, 0), "hold": (0, 220, 255), "back": (0, 0, 255),   # green, yellow, red
                "search": (0, 140, 255), "lost": (160, 160, 160), "idle": (160, 160, 160)}  # orange, gray, gray


# ---- Load the models ---------------------------------------------------------------------
if not os.path.exists(DETECT_MODEL):
    sys.exit("Face detection model not found - download it first, see pi/models/README.md")
# YuNet is told the picture size (W, H), so every frame must be that size.
detector = cv2.FaceDetectorYN.create(DETECT_MODEL, "", (W, H), score_threshold=SCORE_MIN)

recognizer = None      # without SFace, SMART still works, but only by position (can't recognize you)
if os.path.exists(RECOG_MODEL):
    recognizer = cv2.FaceRecognizerSF.create(RECOG_MODEL, "")
else:
    print("Face recognition model not found - SMART will follow by position only. See pi/models/README.md")


# ---- Finding and recognizing faces -------------------------------------------------------
def find_faces(frame):
    """All faces in the frame, widest (= closest) first.
    Each face is a dictionary:
      "box"    (x, y, w, h)
      "points" five (x, y) landmarks: right eye, left eye, nose, right mouth, left mouth
      "score"  how sure the detector is, 0 to 1
      "row"    YuNet's raw 15 numbers (the recognizer needs them)"""
    _, rows = detector.detect(frame)        # rows = one row of 15 numbers per face, or None
    if rows is None:
        return []
    faces = []
    for f in sorted(rows, key=lambda f: f[2], reverse=True):     # sort by width, biggest first
        faces.append({
            "box": tuple(int(v) for v in f[:4]),
            "points": [(int(f[4 + 2 * i]), int(f[5 + 2 * i])) for i in range(5)],
            "score": float(f[14]),
            "row": f,
        })
    return faces


def fingerprint(frame, face):
    """The face's fingerprint: 128 numbers from SFace.
    alignCrop first uses the 5 landmarks to straighten the face and cut it out."""
    aligned = recognizer.alignCrop(frame, face["row"])
    return recognizer.feature(aligned).copy()           # .copy(): keep our own copy of the numbers


def similarity(print_a, print_b):
    """How alike two fingerprints are: about 1 = same person, about 0 = different people."""
    return recognizer.match(print_a, print_b, cv2.FaceRecognizerSF_FR_COSINE)


def center(face):
    """Middle of a face's box."""
    x, y, w, h = face["box"]
    return x + w / 2, y + h / 2


def inside(point, box):
    """Is the point (a mouse click) inside the box?"""
    x, y, w, h = box
    return x <= point[0] <= x + w and y <= point[1] <= y + h


class FaceLock:
    """SMART mode: follow YOU.
    - Short term (every frame, cheap): your face is the one near where it just was, at a
      similar size. Survives the picture shifting when the robot turns.
    - Long term (fingerprints): the first time it locks on, it remembers what your face
      looks like, and learns a few more fingerprints as you move. If you were gone for
      more than TRUST_FRAMES frames, it only accepts a face that matches you - anywhere
      in the picture. Everyone else is "not you".
    Without the SFace model it only has the short-term part (follows by position)."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget everything, including who you are (the l key, and when switching modes)."""
        self.face = None        # your face, as last seen
        self.missing = 0        # frames since we last saw it
        self.x = self.w = None  # smoothed center x and width (what the brain gets)
        self.click = None       # (x, y) of a mouse click to handle
        self.prints = []        # your fingerprints (up to LEARN_MAX)
        self.since_learn = 0    # frames since the last fingerprint
        self.checked = []       # (face, similarity) of faces compared with you this frame (for drawing)
        self.similarity = None  # how well the last check matched you

    def knows_you(self):
        return len(self.prints) > 0

    def update(self, frame, faces):
        """Find YOU among this frame's faces. Returns your face, or None if you're not there."""
        self.checked = []

        # -- A mouse click on a face: that person is "you" from now on --
        if self.click is not None:
            hit = [f for f in faces if inside(self.click, f["box"])]
            self.click = None
            if hit:
                self.face, self.missing, self.x, self.w, self.prints = hit[0], 0, None, None, []

        # -- 1. Short term: your face near where it just was --
        found = None
        recent = self.missing <= TRUST_FRAMES or not self.knows_you()   # can we trust its position?
        if self.face is not None and recent and self.missing <= LOCK_TIMEOUT:
            last, last_w = center(self.face), self.face["box"][2]
            reach = max(LOCK_REACH_MIN, LOCK_REACH * last_w)            # how far it may have moved
            near = [f for f in faces
                    if math.dist(center(f), last) < reach                       # close enough, and
                    and LOCK_SIZE_MIN < f["box"][2] / last_w < LOCK_SIZE_MAX]   # a similar size
            found = min(near, key=lambda f: math.dist(center(f), last)) if near else None

        # -- 2. Long term: look for YOU anywhere in the picture, by fingerprint --
        if found is None and self.knows_you() and faces:
            found = self.find_you(frame, faces)
            if found is not None:
                self.x = self.w = None                  # you're somewhere new: restart smoothing

        # -- 3. Nobody known yet: take the closest face - it becomes "you" --
        if found is None and not self.knows_you() and self.face is None and faces:
            found = faces[0]

        # -- Not found: count, and stop looking near the old spot after LOCK_TIMEOUT frames --
        if found is None:
            self.missing += 1
            if self.missing > LOCK_TIMEOUT:
                self.face, self.x, self.w = None, None, None    # (your fingerprints are kept)
            return None

        # -- Found: check / learn the fingerprint, then update the smoothed x and w --
        self.face, self.missing = found, 0
        if not self.learn(frame, found):                # its fingerprint says: NOT you
            self.face, self.x, self.w = None, None, None
            return None
        x, y, w, h = found["box"]
        if self.x is None:                              # first frame: start from the real values
            self.x, self.w = x + w / 2, float(w)
        else:                                           # then move SMOOTH (40 %) of the way each frame
            self.x += SMOOTH * (x + w / 2 - self.x)
            self.w += SMOOTH * (w - self.w)
        return found

    def find_you(self, frame, faces):
        """Compare every face with your fingerprints. Returns the best match above MATCH, or None."""
        best, best_sim = None, MATCH
        for f in faces:
            sim = max(similarity(fingerprint(frame, f), p) for p in self.prints)
            self.checked.append((f, sim))
            if sim >= best_sim:
                best, best_sim = f, sim
        if best is not None:
            self.similarity = best_sim
        return best

    def learn(self, frame, face):
        """Every LEARN_EVERY frames, take a fingerprint of the face we're following.
        The very first one defines who "you" are. Later ones are checked against you first:
        if one doesn't match, we drifted onto someone else -> returns False.
        Matching ones are kept (up to LEARN_MAX) to recognize you from more angles."""
        if recognizer is None:
            return True                                 # no recognition: nothing to check
        self.since_learn += 1
        if self.prints and self.since_learn < LEARN_EVERY:
            return True                                 # not time for a check yet
        self.since_learn = 0
        new = fingerprint(frame, face)
        if self.prints:
            self.similarity = max(similarity(new, p) for p in self.prints)
            if self.similarity < MATCH:
                return False                            # not you!
        if len(self.prints) < LEARN_MAX:
            self.prints.append(new)
        return True


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
bot = Follower()       # the brain (follow / hold / back / search)
lock = FaceLock()      # SMART mode's memory: where you are and who you are


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
    faces = find_faces(frame)
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
        if recognizer is None:
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
