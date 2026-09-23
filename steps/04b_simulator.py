# =============================================================================
# Step 4b - robot simulator (top view)
# =============================================================================
# A virtual robot shaped like the real one - wheels at the front, camera at the
# front, free wheel at the back - driven by the SAME brain as the robot (pi/brain.py).
#
# The loop it runs, 30 times a second (like the real robot will):
#   1. SEE     work out where each person would appear in the robot's camera (x, w)
#   2. PICK    who to follow:  SIMPLE = the biggest person it sees, whoever it is
#                              SMART  = only YOU (recognition is perfect in here)
#   3. DECIDE  brain.py turns (x, w) into a command (fwd, turn) - or, when nobody
#              is picked, sweeps left and right to search
#   4. DRIVE   move the robot with those wheel speeds ... then see again, and so on.
#
# Try this: turn the stranger on (n), then drag yourself behind the robot.
#   SIMPLE sweeps and follows the stranger. SMART ignores the stranger and keeps
#   sweeping until it finds you.
#
# On screen:
#   orange wedge    what the camera can see (outside it, the robot is blind)
#   3 rings         the resume / stop / back-up distances around you
#   blue line       the robot's path
#   "robot camera"  what its camera sees - same x and w as the webcam in step 4
#
# Simplified: flat floor, no wheel slip, motors react instantly, top view only.
#
# Run:   .venv\Scripts\python steps\04b_simulator.py
# Mouse: drag = move you   right-drag = move the stranger
# Keys:  s = simple / smart   n = stranger on / off   a = you walk around by yourself
#        m = color / face mode   r = reset   space = pause   q = quit
#        1 = spin   2 = dance   3 = nod   4 = shake   (the tricks, from pi/moves.py)
# =============================================================================
import math
import os
import sys
from collections import deque

import cv2
import numpy as np

# Use the robot's own brain (pi/brain.py): tune it there and the simulator shows the effect
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi"))
from brain import W, BANDS, DEAD_ZONE, ALIGN_ZONE, Follower, wheels, describe
import moves                                # the tricks: spin, dance, nod, shake


# ---- The virtual room --------------------------------------------------------
SCALE = 220                     # screen pixels per meter (bigger = everything drawn bigger)
WORLD_W, WORLD_H = 4.0, 3.0     # room size in meters
FPS = 30                        # simulation steps per second
DT = 1 / FPS                    # seconds per step


# ---- The virtual robot (sizes in meters, matching your drawing) ------------------
MAX_SPEED = 0.45        # how fast one wheel moves at 100 %, in m/s (estimate: TT motor + 65 mm wheel).
                        # Measure the real robot later and put the real number here.
TRACK = 0.14            # distance between the two wheels. Wider = turns more slowly.
CAMERA_AHEAD = 0.03     # the camera sits this far in front of the wheel axle
HFOV = math.radians(60)                   # webcam field of view, left edge to right edge (typical: 60 degrees)
FOCAL = (W / 2) / math.tan(HFOV / 2)      # ~416 px: the camera's "zoom" - turns meters into pixels
LATENCY = 3             # frames (0.1 s) between the camera seeing and the wheels reacting,
                        # like the real robot. More latency = more overshoot when turning.


# ---- The people / targets --------------------------------------------------------
TARGET = {              # (real width in m, smallest width the detector can find in px, drawing color)
    "color": (0.20, 20, (0, 220, 255)),      # yellow object, 20 cm
    "face":  (0.15, 26, (140, 180, 230)),    # a face, ~15 cm wide (smaller than 26 px isn't detected)
}
STRANGER_COLOR = (150, 150, 150)             # the other person is drawn gray


# ---- Colors (Blue, Green, Red) and text --------------------------------------------
BG, GRID, GRID_1M = (245, 245, 245), (228, 228, 228), (205, 205, 205)
FRAME_LINE, FRAME_FILL = (30, 30, 30), (255, 255, 255)
BLUE, ORANGE, RED = (232, 162, 0), (39, 127, 255), (36, 28, 237)     # wheels, camera, free wheel
TEXT = (40, 40, 40)
# Color of the state text, by what the brain is doing (see brain.py, Follower.status)
STATE_COLORS = {"follow": (0, 150, 0), "hold": (0, 140, 230), "back": (0, 0, 220),
                "search": (0, 110, 255), "lost": (120, 120, 120), "idle": (120, 120, 120),
                "move": (250, 139, 167)}      # tricks (violet, like the dashboard)
FONT = cv2.FONT_HERSHEY_SIMPLEX
WIN = "Robot simulator"


def to_px(x, y):
    """Room position in meters -> screen pixel. y is flipped: on screen, up = +y in the room."""
    return int(round(x * SCALE)), int(round((WORLD_H - y) * SCALE))


class Robot:
    """The robot's position (x, y) = middle of the wheel axle, in meters,
    and heading = which way it faces, in radians (0 = right, pi/2 = up)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.x, self.y, self.heading = WORLD_W / 2, 0.5, math.pi / 2    # bottom middle, facing up
        self.trail = deque(maxlen=500)                                  # last 500 positions, for the path

    def local(self, u, v):
        """A point on the robot (u = meters forward, v = meters to the left) -> its room position.
        Used to draw the robot's parts and to find where the camera is."""
        c, s = math.cos(self.heading), math.sin(self.heading)
        return self.x + u * c - v * s, self.y + u * s + v * c

    def drive(self, left, right):
        """Move for one time step with the given wheel speeds (-100..100 %).
        This is how any two-wheeled robot moves:
          speed    = average of the two wheels (both same speed -> straight line)
          turning  = difference between them / distance between the wheels
                     (left faster than right -> turns right)"""
        vl, vr = MAX_SPEED * left / 100, MAX_SPEED * right / 100    # % -> m/s
        speed = (vl + vr) / 2                                       # forward speed of the axle
        self.heading += (vr - vl) / TRACK * DT                      # how much it turns in this step
        # move along the heading; min/max keep it inside the room (the walls)
        self.x = min(max(self.x + speed * math.cos(self.heading) * DT, 0.15), WORLD_W - 0.15)
        self.y = min(max(self.y + speed * math.sin(self.heading) * DT, 0.15), WORLD_H - 0.15)
        self.trail.append(to_px(self.x, self.y))


def see(robot, tx, ty, mode):
    """The simulated camera: what it reports about a person/target at (tx, ty).
    Returns (x, w) in pixels - the same numbers the webcam gives in step 4 -
    or None if the robot can't see it.
    A camera works like this ("pinhole camera"):
      x = picture center + FOCAL x (meters to the right / meters ahead)
      w = FOCAL x (real width / meters ahead)    -> twice as far = half as wide"""
    size, min_w, _ = TARGET[mode]
    cx, cy = robot.local(CAMERA_AHEAD, 0)       # where the camera is
    dx, dy = tx - cx, ty - cy                   # from the camera to the target
    c, s = math.cos(robot.heading), math.sin(robot.heading)
    ahead = dx * c + dy * s                     # meters straight ahead of the camera
    right = dx * s - dy * c                     # meters to the right of it
    if ahead < 0.05 or abs(math.atan2(right, ahead)) > HFOV / 2:
        return None                             # behind the robot, or outside the 60 degree view
    w = FOCAL * size / ahead
    if w < min_w:
        return None                             # too far: too small for the detector to find
    return round(W / 2 + FOCAL * right / ahead), round(w)


def pick(seen_you, seen_stranger, who):
    """Who the robot follows this frame - the same rule as step 5.
    SIMPLE: the biggest (closest) person it can see, whoever it is.
    SMART:  only you. (In the simulator recognition is perfect; the real one uses SFace.)
    Returns (seen, "you" / "stranger") or (None, None)."""
    if who == "smart":
        return (seen_you, "you") if seen_you is not None else (None, None)
    visible = [(s, name) for s, name in ((seen_you, "you"), (seen_stranger, "stranger")) if s is not None]
    return max(visible, key=lambda v: v[0][1]) if visible else (None, None)   # v[0][1] = width w


# ---- Drawing -----------------------------------------------------------------------
def draw_room(img):
    """Grid lines every 0.5 m (darker every 1 m) and a 1 m scale bar."""
    for i in range(int(WORLD_W * 2) + 1):
        x = int(i * 0.5 * SCALE)
        cv2.line(img, (x, 0), (x, img.shape[0]), GRID_1M if i % 2 == 0 else GRID, 1)
    for i in range(int(WORLD_H * 2) + 1):
        y = int(i * 0.5 * SCALE)
        cv2.line(img, (0, y), (img.shape[1], y), GRID_1M if i % 2 == 0 else GRID, 1)
    x0, y0 = img.shape[1] - SCALE - 20, img.shape[0] - 58
    cv2.line(img, (x0, y0), (x0 + SCALE, y0), TEXT, 2)
    cv2.putText(img, "1 m", (x0 + SCALE // 2 - 12, y0 - 6), FONT, 0.45, TEXT, 1, cv2.LINE_AA)


def draw_view_cone(img, robot):
    """Light orange wedge = what the camera can see (60 degrees wide, drawn 3.5 m long)."""
    cx, cy = robot.local(CAMERA_AHEAD, 0)
    pts = [to_px(cx, cy)]
    for a in (HFOV / 2, -HFOV / 2):             # left edge, right edge of the view
        pts.append(to_px(cx + 3.5 * math.cos(robot.heading + a), cy + 3.5 * math.sin(robot.heading + a)))
    overlay = img.copy()
    cv2.fillPoly(overlay, [np.array(pts, np.int32)], (180, 215, 255))
    cv2.addWeighted(overlay, 0.35, img, 0.65, 0, img)       # 35 % see-through


def draw_person(img, tx, ty, mode, label, color, rings, followed):
    """A person/target from above. rings=True adds the resume / stop / back-up distances
    (green / orange / red) where the brain's thresholds kick in. followed=True: green outline."""
    size, _, _ = TARGET[mode]
    center = to_px(tx, ty)
    if rings:
        resume_w, stop_w, backup_w = BANDS[mode]
        for w, name, ring in ((resume_w, "resume", (0, 150, 0)),
                              (stop_w, "stop", (0, 140, 230)),
                              (backup_w, "back up", (0, 0, 220))):
            r = int(FOCAL * size / w * SCALE)   # the distance at which the camera sees width w
            cv2.circle(img, center, r, ring, 1, cv2.LINE_AA)
            # put the label on the first free spot of the ring: top, bottom, left, right
            # (on screen, and not on top of the text panel in the top-left corner)
            cx, cy = center
            for lx, ly in ((cx - 22, cy - r - 4), (cx - 22, cy + r + 14), (cx - r - 58, cy), (cx + r + 4, cy)):
                on_screen = 0 <= lx <= img.shape[1] - 60 and 14 <= ly <= img.shape[0] - 70
                if on_screen and not (lx < 270 and ly < 215):
                    cv2.putText(img, name, (lx, ly), FONT, 0.4, ring, 1, cv2.LINE_AA)
                    break
    radius = max(4, int(size / 2 * SCALE))
    cv2.circle(img, center, radius, color, -1, cv2.LINE_AA)
    cv2.circle(img, center, radius + (2 if followed else 0), (0, 170, 0) if followed else TEXT,
               2 if followed else 1, cv2.LINE_AA)
    cv2.putText(img, label, (center[0] - 24, center[1] + radius + 16), FONT, 0.45, TEXT, 1, cv2.LINE_AA)


def draw_robot(img, robot):
    """The robot from above, like your drawing. Each part is a list of corner points in
    robot coordinates (meters forward, meters left), turned into screen pixels."""
    def shape(points, color, outline=None):
        pts = np.array([to_px(*robot.local(u, v)) for u, v in points], np.int32)
        cv2.fillPoly(img, [pts], color, cv2.LINE_AA)
        if outline is not None:
            cv2.polylines(img, [pts], True, outline, 2, cv2.LINE_AA)

    shape([(0.04, 0.06), (0.04, -0.06), (-0.18, -0.06), (-0.18, 0.06)], FRAME_FILL, FRAME_LINE)   # frame
    for side in (1, -1):                                                                        # wheels (left, right)
        shape([(0.033, side * 0.062), (0.033, side * 0.09), (-0.033, side * 0.09), (-0.033, side * 0.062)], BLUE)
    shape([(0.035, 0.03), (0.035, -0.03), (0.005, -0.03), (0.005, 0.03)], ORANGE)             # camera
    cv2.circle(img, to_px(*robot.local(-0.15, 0)), max(3, int(0.018 * SCALE)), RED, -1, cv2.LINE_AA)  # free wheel


def draw_camera_view(img, people):
    """Small window (top right): what the robot's camera sees, at half size, with the same
    dead zone / align zone lines as step 4. people = list of (seen, color, followed)."""
    iw, ih = W // 2, 180
    x0, y0 = img.shape[1] - iw - 12, 12
    view = np.full((ih, iw, 3), 45, np.uint8)
    cv2.rectangle(view, ((W // 2 - DEAD_ZONE) // 2, 0), ((W // 2 + DEAD_ZONE) // 2, ih), (95, 95, 95), 1)
    for x in (W // 2 - ALIGN_ZONE, W // 2 + ALIGN_ZONE):
        cv2.line(view, (x // 2, 0), (x // 2, ih), (70, 70, 70), 1)
    texts = []
    for seen, color, followed in people:
        if seen is None:
            continue
        x, w = seen
        half = w // 4                           # half of w, at half size
        cv2.rectangle(view, (x // 2 - half, ih // 2 - half), (x // 2 + half, ih // 2 + half), color, -1)
        if followed:                            # green box = the one being followed
            cv2.rectangle(view, (x // 2 - half, ih // 2 - half), (x // 2 + half, ih // 2 + half), (0, 255, 0), 2)
            texts.append(f"x={x} w={w}")
    cv2.putText(view, texts[0] if texts else "nobody followed", (6, ih - 8), FONT, 0.45,
                (0, 255, 0) if texts else (160, 160, 160), 1, cv2.LINE_AA)
    img[y0:y0 + ih, x0:x0 + iw] = view          # paste it into the corner
    cv2.rectangle(img, (x0 - 1, y0 - 1), (x0 + iw, y0 + ih), TEXT, 1)
    cv2.putText(img, "robot camera", (x0, y0 + ih + 16), FONT, 0.45, TEXT, 1, cv2.LINE_AA)


def draw_panel(img, ui, bot, following, fwd, turn, distance):
    """Text in the top-left corner, the two wheel bars, and the help lines at the bottom."""
    state, kind = player.status(sim_time) or bot.status()
    who = "SMART - follows only you" if ui["who"] == "smart" else "SIMPLE - follows whoever it sees"
    lines = [
        (f"{ui['mode'].upper()} mode   {who}" + ("   [PAUSED]" if ui["paused"] else ""), TEXT),
        (f"state: {state}" + (f"   (following: {following})" if following else ""), STATE_COLORS[kind]),
        (f"fwd {fwd}  turn {turn}   ->  {describe(fwd, turn)}", (150, 70, 0)),
        (f"distance to you: {distance:.2f} m" + ("   [you: auto-walk]" if ui["auto"] else ""), TEXT),
    ]
    for i, (text, c) in enumerate(lines):
        cv2.putText(img, text, (12, 26 + i * 24), FONT, 0.55, c, 1 if i else 2, cv2.LINE_AA)

    left, right = wheels(fwd, turn)                         # bars: up = forward, down = reverse
    cv2.putText(img, "wheels", (14, 130), FONT, 0.45, TEXT, 1, cv2.LINE_AA)
    for i, (label, speed) in enumerate((("L", left), ("R", right))):
        x, base = 20 + i * 50, 200
        top = base - int(speed * 0.4)                       # 100 % = 40 px
        bar = (0, 170, 0) if speed >= 0 else (0, 0, 220)
        cv2.rectangle(img, (x, min(base, top)), (x + 18, max(base, top)), bar, -1)
        cv2.line(img, (x - 4, base), (x + 22, base), TEXT, 1)
        cv2.putText(img, f"{label} {speed}", (x - 4, base - 46), FONT, 0.45, TEXT, 1, cv2.LINE_AA)

    help1 = "drag = move you   right-drag = move stranger   n = stranger on/off   s = simple/smart"
    help2 = "a = you walk around   m = color/face   r = reset   space = pause   q = quit"
    help3 = "tricks:  1 = spin   2 = dance   3 = nod   4 = shake"
    cv2.putText(img, help1, (12, img.shape[0] - 52), FONT, 0.45, (110, 110, 110), 1, cv2.LINE_AA)
    cv2.putText(img, help2, (12, img.shape[0] - 32), FONT, 0.45, (110, 110, 110), 1, cv2.LINE_AA)
    cv2.putText(img, help3, (12, img.shape[0] - 12), FONT, 0.45, (150, 110, 130), 1, cv2.LINE_AA)


# ---- Setup ------------------------------------------------------------------------
robot = Robot()
bot = Follower()                            # the same brain as step 4
player = moves.Player()                     # the same tricks as the robot (pi/moves.py)
you = [WORLD_W / 2 + 0.6, 2.2]              # you start ahead and a bit to the right (meters)
stranger = [0.7, 1.4]                       # the other person, off to the left
ui = {"mode": "color", "who": "smart", "stranger": False, "auto": False, "paused": False}
camera_delay = deque(maxlen=LATENCY + 1)    # the last few things the camera saw (for the delay)
sim_time = 0.0                              # the simulator's own clock (seconds) - the brain uses it
walk_time = 0.0                             # clock for auto-walk
seen, following, fwd, turn = None, None, 0, 0


def on_mouse(event, x, y, flags, param):
    """Left click/drag = move you there. Right click/drag = move the stranger there."""
    pos = [min(max(x / SCALE, 0.1), WORLD_W - 0.1), min(max(WORLD_H - y / SCALE, 0.1), WORLD_H - 0.1)]
    if event == cv2.EVENT_LBUTTONDOWN or (event == cv2.EVENT_MOUSEMOVE and flags & cv2.EVENT_FLAG_LBUTTON):
        you[:] = pos
        ui["auto"] = False                  # the mouse takes over from auto-walk
    if event == cv2.EVENT_RBUTTONDOWN or (event == cv2.EVENT_MOUSEMOVE and flags & cv2.EVENT_FLAG_RBUTTON):
        stranger[:] = pos


cv2.namedWindow(WIN)
cv2.setMouseCallback(WIN, on_mouse)


# ---- The loop: see -> pick -> decide -> drive -> draw ------------------------------------
while True:
    if not ui["paused"]:
        sim_time += DT
        if ui["auto"]:                      # you walk an oval around the room (~0.2 m/s)
            walk_time += DT
            you[0] = WORLD_W / 2 + 1.3 * math.cos(0.2 * walk_time)
            you[1] = WORLD_H / 2 + 0.8 * math.sin(0.2 * walk_time)

        seen_stranger = see(robot, stranger[0], stranger[1], ui["mode"]) if ui["stranger"] else None
        camera_delay.append((see(robot, you[0], you[1], ui["mode"]), seen_stranger))    # 1. see
        seen_you, seen_stranger = camera_delay[0]    # the brain gets a slightly old picture, like the real one
        seen, following = pick(seen_you, seen_stranger, ui["who"])                    # 2. pick
        trick = player.update(sim_time)                                                # 3. decide
        if trick is not None:                       # a trick is playing: it owns the wheels
            fwd, turn = trick
        else:
            fwd, turn = bot.update(seen, ui["mode"], now=sim_time)
        robot.drive(*wheels(fwd, turn))                                                # 4. drive

    # draw everything, back to front
    img = np.full((int(WORLD_H * SCALE), int(WORLD_W * SCALE), 3), BG, np.uint8)
    draw_room(img)
    draw_view_cone(img, robot)
    if len(robot.trail) > 1:
        cv2.polylines(img, [np.array(robot.trail, np.int32)], False, (215, 185, 140), 2, cv2.LINE_AA)
    you_label = "you" if ui["mode"] == "face" else "target"
    if ui["stranger"]:
        draw_person(img, stranger[0], stranger[1], ui["mode"],
                    "stranger" if ui["mode"] == "face" else "other", STRANGER_COLOR, False, following == "stranger")
    draw_person(img, you[0], you[1], ui["mode"], you_label, TARGET[ui["mode"]][2], True, following == "you")
    draw_robot(img, robot)
    draw_camera_view(img, [(seen_you, TARGET[ui["mode"]][2], following == "you"),
                           (seen_stranger, STRANGER_COLOR, following == "stranger")])
    cam_x, cam_y = robot.local(CAMERA_AHEAD, 0)
    distance = math.hypot(you[0] - cam_x, you[1] - cam_y)           # camera to you, in meters
    draw_panel(img, ui, bot, following, fwd, turn, distance)
    cv2.imshow(WIN, img)

    # waitKey also sets the speed: ~33 ms per step = 30 steps per second
    key = cv2.waitKey(int(1000 * DT)) & 0xFF
    if key == ord('q') or cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:   # q, or window closed
        break
    if key == ord('a'):
        ui["auto"] = not ui["auto"]
    if key == ord('n'):                     # stranger on / off
        ui["stranger"] = not ui["stranger"]
    if key == ord('s'):                     # SIMPLE / SMART
        ui["who"] = "simple" if ui["who"] == "smart" else "smart"
        bot.reset()
        camera_delay.clear()
    if key == ord('m'):                     # switch color / face (different target size and thresholds)
        ui["mode"] = "face" if ui["mode"] == "color" else "color"
        bot.reset()
        camera_delay.clear()
    if key == ord('r'):
        robot.reset()
        bot.reset()
        camera_delay.clear()
    if key == ord(' '):
        ui["paused"] = not ui["paused"]
    for k, name in ((ord('1'), "spin"), (ord('2'), "dance"),
                    (ord('3'), "nod"), (ord('4'), "shake")):
        if key == k:                        # play a trick (same ones as the dashboard)
            player.start(name, sim_time)

cv2.destroyAllWindows()
