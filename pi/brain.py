# =============================================================================
# brain.py - the robot's decision logic ("the brain")
# =============================================================================
# Used by the robot program (follow.py) and by steps 4, 4b (simulator) and 5,
# so every setting below is changed in ONE place and all of them use it.
# Tune something here and the simulator shows you the effect right away.
#
# INPUT  - where the target is in the camera picture:
#            x = center of the target, in pixels from the left edge (0 .. 480)
#            w = width of the target, in pixels (bigger = closer)
#          or None when the target isn't in the picture.
#
# OUTPUT - the command for the wheels:
#            fwd  = forward speed  -100 .. 100 %   (+ forward, - reverse)
#            turn = turn rate      -100 .. 100 %   (+ right,   - left)
#
# Every frame it makes these decisions:
#   1. DISTANCE (from w): follow / hold / back up    -> fwd
#   2. STEERING (from x): how far off-center is it?  -> turn
#   3. SEARCHING (target lost): sweep left and right to find it again
# =============================================================================
import time


# ---- Camera picture size ----------------------------------------------------
# Every step shrinks the camera frame to this size before looking at it.
# All pixel numbers below (thresholds, zones) are measured in THIS picture,
# so if you ever change the size, re-check them.
W, H = 480, 360


# ---- 1. DISTANCE: three thresholds per mode ---------------------------------
# (RESUME, STOP, BACKUP) = target width w in pixels, from small (far) to big (near):
#
#     far (w small)                                            near (w big)
#     ---------------|---------------|-----------------|------------------->
#                  RESUME           STOP             BACKUP
#
#   FOLLOW  (drive forward)  until w reaches STOP            -> HOLD
#   HOLD    (stand still)    until w drops back to RESUME    -> FOLLOW
#   w above BACKUP (too close): BACK up until w is down to STOP -> HOLD
#
# Why three and not one? With a single threshold the robot jitters
# ("stop, go, stop, go") when you stand right on it. The gaps between the
# numbers ("hysteresis") mean you must move clearly away before it reacts.
#
# How to set them: hold the target where the robot should stop and read w on
# screen - that is STOP. Then RESUME ~ 0.8 x STOP and BACKUP ~ 1.25 x STOP.
#   Jitters between go and stop     -> make the RESUME-STOP gap bigger
#   Slow to start following again   -> make that gap smaller
#   Goes forward, back, forward...  -> move BACKUP further above STOP
#   Faces: keep RESUME at 30 or more (faces under ~26 px aren't detected)
BANDS = {
    "color": (64, 83, 104),     # 20 cm target:     ~1.3 m / 1.0 m / 0.8 m
    "face":  (33, 42, 54),      # face (~15 cm):    ~1.9 m / 1.5 m / 1.15 m
}


# ---- 2. STEERING: zones across the picture (pixels from the center) --------
#
#   | spin in place |  curve toward  | straight |  curve toward  | spin in place |
#   0              120              210   240  270              360            480
#                                         center
DEAD_ZONE = 30      # Within +-30 px of the center counts as "centered": no turning.
                    #   Wiggles left-right when you stand still -> make it bigger.
                    #   Doesn't point straight at you           -> make it smaller.

ALIGN_ZONE = 120    # More than 120 px off-center: turn in place first, don't drive.
                    # (Centering beats distance - otherwise it drives past you.)

KP = 60             # How hard to turn: the turn % when the target is at the very edge.
                    #   turn = KP x (how far off-center / half the picture width)
                    #   e.g. target at x=300: 60 px off -> 60 x 60/240 = 15 % turn
                    #   Overshoots and wobbles -> lower it. Turns too lazily -> raise it.

TURN_MAX = 60       # Never turn harder than this %, however far off-center.


# ---- Speeds (% of full motor speed) ------------------------------------------
SPEED_FWD = 50      # driving toward the target
SPEED_BACK = 40     # backing away when it's too close


# ---- Losing the target --------------------------------------------------------
LOST_GRACE = 5      # Detections flicker for a frame or two. Keep the last command for
                    # up to 5 frames (~0.2-0.3 s) before deciding it's really gone.
                    #   Starts searching too late -> lower it. Stutters -> raise it.


# ---- 3. SEARCHING: when the target is really gone ----------------------------
# The robot turns in place to look for it: first toward the side it was last
# seen on (you probably walked out that way), then back the other way - each
# sweep one step longer, so it looks further around every time:
#
#     sweep 1:  1 x SEARCH_SWEEP s  toward the side it was last seen
#     sweep 2:  2 x SEARCH_SWEEP s  the other way  (past the start, to the other side)
#     sweep 3:  3 x SEARCH_SWEEP s  back again     (further than sweep 1) ... and so on
#
# It stops searching the moment the target is seen again. WHO counts as the
# target is decided outside the brain: step 5 SIMPLE = anyone, SMART = only you.
SEARCH = True           # False = just stop when the target is lost (no searching)
SEARCH_TURN = 25        # Turn speed while searching, %.
                        #   Misses you while sweeping past -> lower it (more time to spot you, less blur)
                        #   Takes too long to look around  -> raise it
SEARCH_SWEEP = 1.0      # Seconds of the first sweep (must be more than 0). Every next sweep is
                        # that much longer. Bigger = wider first look before turning back.
                        # (In the simulator 1.0 s = ~90 degrees, so sweep 3 already looks behind.)
SEARCH_GIVE_UP = 20     # Seconds: stop searching after this long and wait. 0 = never give up.


# =============================================================================
class Follower:
    """The robot's brain: turns (target center x, target width w) into (fwd, turn)."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Start fresh (used when switching modes)."""
        self.state = "follow"       # follow | hold | back | search | idle
        self.lost = 0               # frames since the target was last seen
        self.cmd = (0, 0)           # the last command we gave
        self.last_side = 1          # which side the target was last seen on: +1 right, -1 left
        self.search_start = 0.0     # when the current search started (seconds)

    def update(self, target, mode, now=None):
        """Called once per frame.
        target = (x, w) in pixels, or None if nothing was found.
        mode   = "color" or "face" (picks the distance thresholds).
        now    = the time in seconds. Leave it out - the simulator passes its own clock.
        Returns (fwd, turn), each -100..100."""
        if now is None:
            now = time.time()

        # -- No target this frame --
        if target is None:
            self.lost += 1
            if self.lost <= LOST_GRACE:                 # just a flicker: keep doing the last thing
                return self.cmd
            if self.state not in ("search", "idle"):     # really gone: start searching
                self.state, self.search_start = "search", now
            turn = self.search_turn(now - self.search_start) if self.state == "search" else 0
            if turn == 0:                               # searching is off, or we gave up: stop and wait
                self.state = "idle"
            self.cmd = (0, turn)                        # search = turn in place, never drive
            return self.cmd

        # -- Target found --
        self.lost = 0
        x, w = target
        if self.state in ("search", "idle"):            # found it again: follow (the distance check
            self.state = "follow"                       # below turns this into hold/back if it's close)
        resume_w, stop_w, backup_w = BANDS[mode]

        # -- 1. Distance: which of the three states are we in? --
        if w > backup_w:                                    # too close, from any state
            self.state = "back"
        elif self.state == "follow" and w >= stop_w:        # arrived
            self.state = "hold"
        elif self.state == "hold" and w <= resume_w:        # target moved away again
            self.state = "follow"
        elif self.state == "back" and w <= stop_w:          # backed up far enough
            self.state = "hold"
        # (in every other case the state stays as it was - that's the hysteresis)
        fwd = {"follow": SPEED_FWD, "hold": 0, "back": -SPEED_BACK}[self.state]

        # -- 2. Steering: the further off-center, the harder the turn --
        err = x - W // 2                        # pixels off-center: + = target is to the right
        turn = 0
        if abs(err) > DEAD_ZONE:                # outside the dead zone: turn toward it
            turn = round(KP * err / (W / 2))
            turn = max(-TURN_MAX, min(TURN_MAX, turn))
            self.last_side = 1 if err > 0 else -1   # remember the side (the search starts that way)
        if abs(err) > ALIGN_ZONE:               # far off to the side: turn in place first
            fwd = 0

        self.cmd = (fwd, turn)
        return self.cmd

    def search_turn(self, elapsed):
        """The turn % while searching, `elapsed` seconds into the search. 0 = stop searching."""
        if not SEARCH or (SEARCH_GIVE_UP and elapsed > SEARCH_GIVE_UP):
            return 0
        sweep, t = 1, elapsed
        while t >= sweep * SEARCH_SWEEP:        # which sweep are we in? sweep n lasts n x SEARCH_SWEEP
            t -= sweep * SEARCH_SWEEP
            sweep += 1
        side = self.last_side if sweep % 2 == 1 else -self.last_side   # odd sweeps: toward the last-seen side
        return side * SEARCH_TURN

    def status(self):
        """What the brain is doing, for the screen. Returns (text, kind).
        kind is one of: follow, hold, back, lost, search, idle - use it to pick a color."""
        if self.lost == 0:
            return self.state.upper(), self.state
        if self.lost <= LOST_GRACE:
            return "LOST - keep going", "lost"
        if self.state == "search":
            return "SEARCHING " + ("right" if self.cmd[1] > 0 else "left"), "search"
        return "NO TARGET - waiting", "idle"


def wheels(fwd, turn):
    """Left and right wheel speeds (-100..100 %) - the same mixing the Uno will do.
    e.g. fwd 50, turn 15  -> left 65, right 35 : left is faster, so it curves right
         fwd 0,  turn 40  -> left 40, right -40: wheels opposite, so it spins in place"""
    left, right = fwd + turn, fwd - turn
    biggest = max(abs(left), abs(right))
    if biggest > 100:                           # over 100 %: scale BOTH down by the same
        left, right = int(left * 100 / biggest), int(right * 100 / biggest)   # amount, so the curve keeps its shape
    return left, right


def describe(fwd, turn):
    """The command in plain English, for the screen."""
    if fwd == 0 and turn == 0:
        return "STOP"
    side = "right" if turn > 0 else "left"
    if fwd == 0:
        return f"SPIN {side.upper()} in place"
    move = "FORWARD" if fwd > 0 else "BACK UP"
    return move if turn == 0 else f"{move} + curve {side}"
