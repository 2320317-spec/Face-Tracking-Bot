# =============================================================================
# gestures.py - reading your hand (roadmap: gesture mode)
# =============================================================================
# Same shape as the face pipeline in vision.py, with more dots:
#
#   1. PALM DETECTOR   finds boxes where hands are, plus 7 rough points.
#                      It looks for PALMS, not whole hands - a palm is a rigid
#                      blob, while fingers move too much to detect reliably.
#   2. LANDMARK MODEL  looks inside that box and returns 21 points: the wrist,
#                      then four points per finger (knuckle, 2 joints, tip).
#   3. name_gesture()  plain arithmetic on those 21 points -> "fist", "palm"...
#      GestureReader   makes you hold a gesture before it counts.
#
# Both models come from the OpenCV Zoo, like YuNet and SFace, and load with the
# same cv2.dnn calls. No new library.
#
#   21 points:      8   12  16  20      fingertips
#                   |   |   |   |
#                   7  11  15  19
#                   6  10  14  18       <- the joint each "is it extended?"
#               4   5   9  13  17          test compares against
#                \   \  |  /  /
#                 3   \ | /  /
#                  2   \|/  /
#                   1   +  /
#                    \  | /
#                     \ |/
#                       0               wrist
# =============================================================================
import math
import os

import cv2
import numpy as np


# ---- Settings ---------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
PALM_MODEL = os.path.join(HERE, "models", "palm_detection_mediapipe_2023feb.onnx")
HAND_MODEL = os.path.join(HERE, "models", "handpose_estimation_mediapipe_2023feb.onnx")

PALM_SIZE = 192         # the palm detector always sees a 192x192 square
HAND_SIZE = 224         # the landmark model always sees a 224x224 crop

PALM_SCORE = 0.55       # how sure the detector must be. Lower = finds more hands and more
                        # imaginary ones. Raise it if it sees hands in the background.
MIN_PALM_PX = 45        # ignore palms narrower than this. A palm is ~9 cm across, so at
                        # 480 px wide this means "closer than about 0.8 m" - roughly where
                        # the landmark model stops being reliable anyway. It also saves
                        # running the second model on a hand waving at the back of the room.
NMS_IOU = 0.30          # two boxes overlapping more than this are treated as one hand
HAND_SCORE = 0.60       # how sure the landmark model must be that this really is a hand

CROP_SCALE = 2.6        # the palm box only covers the palm; the fingers need ~2.6x that
CROP_SHIFT = -0.5       # and the crop is shifted up (toward the fingers) by half a box

# How long you must hold a gesture before the robot acts on it. Without this, a hand
# passing through a "fist" shape on its way to a wave would drive the robot.
HOLD_FRAMES = 3         # frames in a row showing the same gesture before it counts
FORGIVE_FRAMES = 3      # keep obeying for this many frames if the hand flickers out of
                        # view, so one missed detection doesn't stutter the wheels
                        # (the same idea as LOST_GRACE in brain.py)

# ---- Driving by hand --------------------------------------------------------------
# These are the speeds used while a gesture is held, in the same -100..100 the brain
# and the Uno use. Kept gentle: you are steering by waving, not with a joystick.
GESTURE_FWD = 35        # pointing up
GESTURE_TURN = 30       # pointing left or right (turns on the spot)
GESTURE_BACK = 30       # two fingers = backwards

POINT_FLIP = False      # Which way is "left"?
                        # False: the way your finger points ON SCREEN is the way it turns.
                        #        Point at the left of the picture -> it turns left.
                        # True:  the opposite, if that feels backwards to you in practice.


# =============================================================================
# The palm detector's anchors.
#
# The model doesn't say "there is a hand at (x, y)". It says, for each of 2016
# fixed boxes spread over the picture, "how far is the hand from THIS box, and
# how sure am I". Those fixed boxes are the anchors, and both sides have to
# generate the same list or every position comes out wrong.
#
#   2016 = 24x24 cells x 2  +  12x12 cells x 6
#
# Two grids: a fine one (24x24, for small hands) and a coarse one (12x12, for
# big ones). Positions are 0..1 across the picture, not pixels.
# =============================================================================
def _anchors():
    out = []
    for grid, per_cell in ((PALM_SIZE // 8, 2), (PALM_SIZE // 16, 6)):
        for y in range(grid):
            for x in range(grid):
                cx, cy = (x + 0.5) / grid, (y + 0.5) / grid
                out.extend([(cx, cy)] * per_cell)
    return np.array(out, np.float32)


ANCHORS = _anchors()


def _sigmoid(x):
    """Turns the model's raw score into a 0..1 probability."""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


class HandTools:
    """Loads both models and finds hands in a picture."""

    def __init__(self):
        self.palm = self.hand = None
        self.loaded = False

    def load(self):
        """Read the two model files. Done on the first gesture frame rather than at
        startup, so a robot that never leaves face mode never pays for them."""
        if self.loaded:
            return self.palm is not None
        self.loaded = True
        if os.path.exists(PALM_MODEL) and os.path.exists(HAND_MODEL):
            self.palm = cv2.dnn.readNet(PALM_MODEL)
            self.hand = cv2.dnn.readNet(HAND_MODEL)
        else:
            print("Hand models missing from pi/models - gesture mode will see nothing.")
        return self.palm is not None

    # ---- step 1: where are the hands? ------------------------------------------
    def palms(self, frame):
        """Returns [(box, score)] - box is (x, y, w, h) in the frame's own pixels."""
        if not self.load():
            return []
        h, w = frame.shape[:2]

        # The model wants a square. Pad the short side with black, evenly on both
        # sides, so nothing is stretched - then remember the padding to undo later.
        side = max(h, w)
        pad_x, pad_y = (side - w) // 2, (side - h) // 2
        square = cv2.copyMakeBorder(frame, pad_y, side - h - pad_y, pad_x, side - w - pad_x,
                                    cv2.BORDER_CONSTANT, value=(0, 0, 0))
        small = cv2.resize(square, (PALM_SIZE, PALM_SIZE))

        # These models come from TensorFlow, so they want the colors in RGB order and
        # the picture as one 192x192x3 block (NHWC). OpenCV hands us BGR, hence the swap -
        # feed it BGR and the detector simply never sees a hand.
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        self.palm.setInput(rgb[np.newaxis, ...])
        raw, scores = self.palm.forward(self.palm.getUnconnectedOutLayersNames())
        raw, scores = raw[0], _sigmoid(scores[0, :, 0])

        keep = scores >= PALM_SCORE
        if not keep.any():
            return []
        raw, scores, anchors = raw[keep], scores[keep], ANCHORS[keep]

        # Decode: the model gives offsets from each anchor, in 192-pixel units.
        cx = raw[:, 0] / PALM_SIZE + anchors[:, 0]
        cy = raw[:, 1] / PALM_SIZE + anchors[:, 1]
        bw = raw[:, 2] / PALM_SIZE
        bh = raw[:, 3] / PALM_SIZE
        # the 7 rough keypoints, same units. We only need 0 (wrist) and 2 (middle knuckle).
        kp = raw[:, 4:18].reshape(-1, 7, 2) / PALM_SIZE + anchors[:, None, :]

        # Back to the real picture: undo the resize, then the padding.
        boxes = np.stack([(cx - bw / 2) * side - pad_x, (cy - bh / 2) * side - pad_y,
                          bw * side, bh * side], axis=1)
        kp = kp * side - np.array([pad_x, pad_y], np.float32)

        idx = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), PALM_SCORE, NMS_IOU)
        if len(idx) == 0:
            return []
        idx = np.array(idx).flatten()
        return [(boxes[i], kp[i], float(scores[i])) for i in idx
                if boxes[i][2] >= MIN_PALM_PX]              # too small = too far away

    # ---- step 2: the 21 points inside one palm box ------------------------------
    def points(self, frame, box, kp):
        """Returns (21x2 points in frame pixels, confidence) or (None, 0)."""
        if self.hand is None:
            return None, 0.0

        # The crop is ROTATED to stand the hand upright, because the model was
        # trained on upright hands. The angle comes from the wrist (point 0) to the
        # middle knuckle (point 2) - that line is the hand's own "up".
        wrist, knuckle = kp[0], kp[2]
        angle = math.degrees(math.atan2(knuckle[1] - wrist[1], knuckle[0] - wrist[0])) + 90

        # The palm box covers only the palm, so grow it to fit the fingers, and
        # shift it toward them.
        x, y, bw, bh = box
        size = max(bw, bh) * CROP_SCALE
        rad = math.radians(angle)
        cx = x + bw / 2 - math.sin(rad) * bh * CROP_SHIFT
        cy = y + bh / 2 - math.cos(rad) * bh * CROP_SHIFT

        # Rotate and cut out the square in one go.
        m = cv2.getRotationMatrix2D((cx, cy), angle, HAND_SIZE / size)
        m[0, 2] += HAND_SIZE / 2 - cx
        m[1, 2] += HAND_SIZE / 2 - cy
        crop = cv2.warpAffine(frame, m, (HAND_SIZE, HAND_SIZE))

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0   # RGB again
        self.hand.setInput(rgb[np.newaxis, ...])
        outs = self.hand.forward(self.hand.getUnconnectedOutLayersNames())
        pts = outs[0].reshape(21, 3)[:, :2]                 # 21 x (x, y) in crop pixels
        conf = float(outs[1].flatten()[0])
        if conf < HAND_SCORE:
            return None, conf

        # Undo the rotation and scaling, so the points land back on the real picture.
        inv = cv2.invertAffineTransform(m)
        pts = np.hstack([pts, np.ones((21, 1), np.float32)]) @ inv.T
        return pts.astype(np.float32), conf

    def find(self, frame):
        """Everything together: returns [{"points": 21x2, "box": ..., "score": ...}]."""
        hands = []
        for box, kp, score in self.palms(frame):
            pts, conf = self.points(frame, box, kp)
            if pts is not None:
                hands.append({"points": pts, "box": box, "score": conf})
        hands.sort(key=lambda h: -h["box"][2])              # widest (nearest) first
        return hands


# =============================================================================
# From 21 points to a gesture name. No machine learning here - just distances.
# =============================================================================
TIPS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
JOINTS = {"index": 6, "middle": 10, "ring": 14, "pinky": 18}


def fingers_up(points):
    """Which fingers are extended. Returns a dict of name -> True/False.

    The rule for the four fingers: a finger is extended when its TIP is further
    from the wrist than its middle JOINT is. Curl a finger and the tip swings
    back toward the palm, ending up closer to the wrist than its own joint.

    The thumb needs its own rule because it folds sideways across the palm
    instead of curling: it counts as out when the tip is further from the pinky
    knuckle than the thumb's lower joint is."""
    wrist = points[0]
    out = {name: (np.linalg.norm(points[tip] - wrist) >
                  np.linalg.norm(points[JOINTS[name]] - wrist))
           for name, tip in TIPS.items()}
    pinky_knuckle = points[17]
    out["thumb"] = (np.linalg.norm(points[4] - pinky_knuckle) >
                    np.linalg.norm(points[3] - pinky_knuckle))
    return out


def point_direction(points):
    """Which way the index finger is pointing: "left", "right", "up" or "down".

    It is the line from the index knuckle (point 5) to its tip (point 8). Screen y
    grows downwards, so it is flipped to get normal "up is up" angles."""
    dx = points[8][0] - points[5][0]
    dy = -(points[8][1] - points[5][1])
    angle = math.degrees(math.atan2(dy, dx))                # 0 = right, 90 = up, 180 = left

    # "Up" gets a narrow 60-degree wedge and sideways gets a wide 120-degree one,
    # because people point sideways with the finger tilted up. A wide "up" would
    # swallow half the sideways pointing and the robot would drive at you instead
    # of turning.
    if 60 <= angle < 120:
        return "up"
    if -120 <= angle < -60:
        return "down"
    side = "right" if -60 <= angle < 60 else "left"
    if POINT_FLIP:
        side = "left" if side == "right" else "right"
    return side


def name_gesture(points):
    """The gesture in this hand, as a name. Returns (name, which fingers are up).

    Names:  point-left / point-right / point-up / point-down   one finger, where it aims
            peace    two fingers          fist    none          palm    all five
            three    three fingers        thumb   thumb only    None    no name for it"""
    up = fingers_up(points)
    n = sum(up.values())
    if n == 0:
        return "fist", up
    if n == 5:
        return "palm", up
    if up["index"] and not up["middle"] and not up["ring"] and not up["pinky"]:
        return "point-" + point_direction(points), up       # the thumb may be out or in
    if up["index"] and up["middle"] and not up["ring"] and not up["pinky"]:
        return "peace", up
    if up["index"] and up["middle"] and up["ring"] and not up["pinky"]:
        return "three", up
    if up["thumb"] and n == 1:
        return "thumb", up
    return None, up                                         # a shape we don't have a name for


# =============================================================================
# What each gesture tells the wheels to do, as (fwd, turn) - the same two numbers
# everything else in this robot speaks in.
#
#   STOP is a special case: it doesn't mean "drive 0", it means "disengage", the
#   same as pressing STOP on the dashboard. You then have to press Engage to wake
#   it up again - which is exactly what you want from a raised palm.
# =============================================================================
STOP = "stop"                                               # the marker for "disengage"

COMMANDS = {
    "point-up":    (GESTURE_FWD, 0),        # one finger up        -> forward
    "point-left":  (0, -GESTURE_TURN),      # one finger left      -> turn left
    "point-right": (0, GESTURE_TURN),       # one finger right     -> turn right
    "peace":       (-GESTURE_BACK, 0),      # two fingers          -> backwards
    "fist":        (0, 0),                  # fist                 -> stay put, still watching
    "palm":        STOP,                    # open palm            -> STOP, like the button
}


class GestureReader:
    """Turns a stream of per-frame guesses into one steady answer.

    The robot obeys a gesture for as long as you HOLD it, like leaning on a joystick.
    Two guards, both needed:

      HOLD_FRAMES      a new gesture has to appear a few frames in a row before it
                       counts, so a hand passing through a fist shape on its way to
                       a wave doesn't drive the robot.
      FORGIVE_FRAMES   once a gesture is accepted, one or two missed detections don't
                       drop it - otherwise the wheels stutter every time you move.

    Show nothing (or take your hand away) and it lets go, which is the deadman: the
    robot stops when you stop telling it what to do."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.held = None            # the gesture we are currently obeying
        self.candidate = None       # a new gesture trying to take over
        self.count = 0              # frames the candidate has been seen
        self.missing = 0            # frames since we last saw the held gesture

    def update(self, gesture):
        """Call once per frame with the gesture seen this frame (or None).
        Returns the gesture to obey right now, or None."""
        if gesture is not None and gesture == self.held:
            self.missing = 0                                # still holding it: nothing to do
            self.candidate, self.count = None, 0
            return self.held

        if gesture is None:                                 # hand gone or unrecognised shape
            self.candidate, self.count = None, 0
            self.missing += 1
            if self.missing > FORGIVE_FRAMES:
                self.held = None                            # let go
            return self.held

        # A different gesture: it must prove itself before it takes over.
        if gesture != self.candidate:
            self.candidate, self.count = gesture, 0
        self.count += 1
        if self.count >= HOLD_FRAMES:
            self.held, self.missing = gesture, 0
            self.candidate, self.count = None, 0
        return self.held

    def progress(self):
        """0.0 to 1.0 - how far a new gesture is through proving itself, for the page."""
        return min(1.0, self.count / HOLD_FRAMES) if self.candidate else 0.0
