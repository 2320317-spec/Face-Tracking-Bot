# =============================================================================
# vision.py - the robot's eyes: camera, color detection, face detection and recognition
# =============================================================================
# Used by the robot program (follow.py) and by steps 4 and 5, so every vision
# setting below is changed in ONE place.
#
#   Camera      reads the webcam on a background thread; always hands out the newest frame
#   find_color  finds the biggest blob of one color (step 2)          -> box
#   FaceTools   the two face models (step 5): YuNet FINDS faces, SFace RECOGNIZES them
#   FaceLock    SMART mode: stays on ONE person, and finds them again by their face
#
# All pixel numbers are for the W x H picture from brain.py (480 x 360).
# =============================================================================
import math
import os
import threading
import time

import cv2
import numpy as np

from brain import W, H


# ---- Camera ------------------------------------------------------------------
CAPTURE = (640, 480)    # What we ask the webcam for. Every frame is then shrunk to W x H.
                        # (MJPG is asked for too - faster over USB - but some webcams ignore it.)


# ---- Color detection (step 2) ------------------------------------------------
COLOR = "yellow"        # which color to follow - one of the names in COLORS

# HSV color ranges: (lowest H, S, V), (highest H, S, V). A pixel matches if all
# three of its values are inside the range.
#   H = hue: WHICH color. OpenCV goes 0-179:
#       red 0-10 and 170-179, orange 10-25, yellow 25-35, green 40-80, blue 100-130
#   S = saturation: how STRONG the color is (0 = gray, 255 = pure). A high minimum ignores pale things.
#   V = value: how BRIGHT (0 = black, 255 = bright). A minimum ignores dark shadows.
# Find your own numbers with tools/hsv_tune.py - and again in the demo room.
COLORS = {
    "yellow": ((22, 120, 100), (38, 255, 255)),   # 22 keeps out orange/skin/wood (below ~20)
    "green":  ((40, 100, 80),  (80, 255, 255)),
    "orange": ((10, 150, 100), (25, 255, 255)),
}

MIN_AREA = 300          # Blobs smaller than 300 pixels (about 17x17) are noise.
                        #   Random specks get boxed -> raise it.  Target lost when far -> lower it.

KERNEL = np.ones((3, 3), np.uint8)   # 3x3 square used to erase specks from the mask.


# ---- Face models (step 5) ----------------------------------------------------
MODELS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")   # pi/models/
DETECT_MODEL = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")     # YuNet (needed)
RECOG_MODEL = os.path.join(MODELS, "face_recognition_sface_2021dec.onnx")    # SFace (for SMART)

SCORE_MIN = 0.7         # How sure (0 to 1) the detector must be before something counts as a face.
                        #   Real faces get missed (dim light, far away) -> lower it, e.g. 0.6
                        #   Random things get boxed as faces           -> raise it, e.g. 0.8


# ---- SMART mode: staying on the same face ------------------------------------
SMOOTH = 0.4            # Smoothing: each frame, the smoothed x and w move 40 % of the way toward the
                        # new measurement. e.g. smoothed w = 40, new w = 50 -> 44.
                        #   Steering still jittery -> lower it (0.2 = smoother)
                        #   Reacts too late when you move -> raise it (1.0 = no smoothing)

LOCK_TIMEOUT = 15       # Frames (~1 s) the locked face may be missing before we stop looking for it
                        # near its last spot. (With recognition, we still know who you are after that.)

LOCK_REACH_MIN = 80     # How far (px) your face may move between two frames and still count as
LOCK_REACH = 3          # "the same face": at least 80 px, or 3x the face's width.
                        # Big on purpose: when the robot turns, the whole picture shifts.
                        #   Lock lost when the robot spins      -> raise it
                        #   Lock jumps to a person next to you  -> lower it

LOCK_SIZE_MIN = 0.6     # The same face can't suddenly change size a lot: a face only counts
LOCK_SIZE_MAX = 1.6     # if it's 0.6x to 1.6x the locked face's width.


# ---- SMART mode: recognizing YOU ------------------------------------------------
MATCH = 0.363           # How alike (0 to 1) two face fingerprints must be to be the same person.
                        # OpenCV's recommended value. Tested: same person 0.88-0.96, different people 0.20.
                        #   Doesn't recognize you (other angle, light)  -> lower it a little, e.g. 0.30
                        #   Mistakes someone else for you              -> raise it, e.g. 0.45

TRUST_FRAMES = 2        # If your face was missing for more than 2 frames, don't trust "it's the face
                        # near where you were" any more - check the fingerprint first.

LEARN_EVERY = 5         # While following you, take another fingerprint every 5 frames. Each one is also
                        # a check: if it doesn't match you, we drifted onto someone else.
                        #   Lower = catches mix-ups sooner, but more work for the Pi.
LEARN_MAX = 5           # Keep up to 5 fingerprints of you (different angles = more reliable).
                        # Speed: one fingerprint takes ~5-10 ms on a laptop, ~65 ms on the Pi 4 (measured).


# ---- Face details ----------------------------------------------------------------
HEAD_TURN = 0.15        # How far the nose must be off the middle of the eyes (as a fraction of the eye
                        # gap) to count as "head turned". Lower = notices smaller turns.

FACE_WIDTH_M = 0.15     # A typical face is about 15 cm wide - used for the distance estimate.
FOCAL = (W / 2) / math.tan(math.radians(60) / 2)   # ~416 px for a 60 degree webcam.
                        # Distance = FOCAL x FACE_WIDTH_M / w. If "~m" is off, change the 60 to your
                        # camera's field of view.


# =============================================================================
class Camera:
    """The webcam, read on a background thread.
    Why a thread: faces take longer to process than colors. If we only read the camera when
    the loop is ready, OpenCV hands us OLD frames from its queue and the robot reacts to where
    you WERE. The thread keeps reading all the time, so read() always gives the newest frame."""

    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE[1])
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)            # keep at most one old frame waiting
        if not self.cap.isOpened():
            raise SystemExit(f"Camera {index} not found - try --camera 1")
        self.frame = None
        self.fresh = threading.Event()                      # "a new frame has arrived"
        self.running = True
        self.thread = threading.Thread(target=self._grab, daemon=True)
        self.thread.start()

    def _grab(self):
        """Runs on the background thread: read frames as fast as the camera gives them."""
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                self.frame = frame
                self.fresh.set()
            else:
                time.sleep(0.1)                             # camera hiccup: don't spin the CPU

    def read(self, timeout=1.0):
        """The newest frame, shrunk to W x H - or None if the camera stopped sending."""
        if not self.fresh.wait(timeout):
            return None
        self.fresh.clear()
        frame = self.frame
        if frame.shape[:2] != (H, W):
            frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)
        return frame

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.cap.release()


def find_color(frame):
    """Returns (box, mask).
    box  = (x, y, w, h) of the biggest COLOR blob, or None if there isn't one
    mask = black and white picture: white = matches the color"""
    lo, hi = COLORS[COLOR]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)                 # to HSV
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))           # white where it matches
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)         # erase tiny specks
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, mask
    biggest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(biggest) < MIN_AREA:
        return None, mask
    return cv2.boundingRect(biggest), mask


class FaceTools:
    """The two face models.
    YuNet finds faces. For every face it gives 15 numbers:
      [0-3]   the box: x, y, w, h
      [4-13]  5 landmarks, (x, y) each: right eye, left eye, nose tip,
              right mouth corner, left mouth corner ("right" = the person's right)
      [14]    how sure it is that this is a face, 0 to 1
    SFace recognizes faces: it turns a face into a "fingerprint" of 128 numbers. The same
    person gives similar numbers. Everything runs on this computer; nothing is saved to disk."""

    def __init__(self):
        if not os.path.exists(DETECT_MODEL):
            raise SystemExit("Face detection model not found - see pi/models/README.md")
        # YuNet is told the picture size (W, H), so every frame must be that size.
        self.detector = cv2.FaceDetectorYN.create(DETECT_MODEL, "", (W, H), score_threshold=SCORE_MIN)
        self.recognizer = None      # without SFace, SMART still works, but only by position
        if os.path.exists(RECOG_MODEL):
            self.recognizer = cv2.FaceRecognizerSF.create(RECOG_MODEL, "")
        else:
            print("Face recognition model not found - SMART will follow by position only. "
                  "See pi/models/README.md")

    def find(self, frame):
        """All faces in the frame, widest (= closest) first. Each face is a dictionary:
          "box" (x, y, w, h), "points" five (x, y) landmarks, "score" 0-1,
          "row" YuNet's raw 15 numbers (the recognizer needs them)"""
        _, rows = self.detector.detect(frame)       # one row of 15 numbers per face, or None
        if rows is None:
            return []
        faces = []
        for f in sorted(rows, key=lambda f: f[2], reverse=True):     # by width, biggest first
            faces.append({
                "box": tuple(int(v) for v in f[:4]),
                "points": [(int(f[4 + 2 * i]), int(f[5 + 2 * i])) for i in range(5)],
                "score": float(f[14]),
                "row": f,
            })
        return faces

    def fingerprint(self, frame, face):
        """The face's fingerprint: 128 numbers from SFace.
        alignCrop first uses the 5 landmarks to straighten the face and cut it out."""
        aligned = self.recognizer.alignCrop(frame, face["row"])
        return self.recognizer.feature(aligned).copy()      # .copy(): keep our own copy of the numbers

    def similarity(self, print_a, print_b):
        """How alike two fingerprints are: about 1 = same person, about 0 = different people."""
        return self.recognizer.match(print_a, print_b, cv2.FaceRecognizerSF_FR_COSINE)


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
    - Long term (fingerprints): the first time it locks on, it remembers what your face looks
      like, and learns a few more fingerprints as you move. If you were gone for more than
      TRUST_FRAMES frames, it only accepts a face that matches you - anywhere in the picture.
    Without the SFace model it only has the short-term part (follows by position)."""

    def __init__(self, tools):
        self.tools = tools          # a FaceTools (for the fingerprints)
        self.reset()

    def reset(self):
        """Forget everything, including who you are."""
        self.face = None            # your face, as last seen
        self.missing = 0            # frames since we last saw it
        self.x = self.w = None      # smoothed center x and width (what the brain gets)
        self.click = None           # (x, y) of a click to handle: "this face is me"
        self.prints = []            # your fingerprints (up to LEARN_MAX)
        self.since_learn = 0        # frames since the last fingerprint
        self.checked = []           # (face, similarity) of faces compared with you this frame
        self.similarity = None      # how well the last check matched you

    def knows_you(self):
        return len(self.prints) > 0

    def update(self, frame, faces):
        """Find YOU among this frame's faces. Returns your face, or None if you're not there."""
        self.checked = []

        # -- A click on a face: that person is "you" from now on --
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
            sim = max(self.tools.similarity(self.tools.fingerprint(frame, f), p) for p in self.prints)
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
        if self.tools.recognizer is None:
            return True                                 # no recognition: nothing to check
        self.since_learn += 1
        if self.prints and self.since_learn < LEARN_EVERY:
            return True                                 # not time for a check yet
        self.since_learn = 0
        new = self.tools.fingerprint(frame, face)
        if self.prints:
            self.similarity = max(self.tools.similarity(new, p) for p in self.prints)
            if self.similarity < MATCH:
                return False                            # not you!
        if len(self.prints) < LEARN_MAX:
            self.prints.append(new)
        return True


def head_turn(face):
    """Which way the head is turned, as seen in the picture.
    Looking straight at the camera, the nose sits halfway between the eyes; turning the head
    moves the nose toward one side. Returns ("straight" / "left" / "right", offset), where
    offset = how far the nose is off, as a fraction of the gap between the eyes."""
    right_eye, left_eye, nose = face["points"][:3]
    eye_middle = (right_eye[0] + left_eye[0]) / 2
    eye_gap = math.dist(right_eye, left_eye) or 1   # "or 1": never divide by zero
    offset = (nose[0] - eye_middle) / eye_gap
    if offset > HEAD_TURN:
        return "right", offset
    if offset < -HEAD_TURN:
        return "left", offset
    return "straight", offset
