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
# ---- HOW the robot judges distance -------------------------------------------
# Two ways, and they fail differently:
#
#   "width"   How WIDE the target looks. Simple, works for any camera angle - but
#             it shrinks when you turn your head, and the robot reads that as you
#             stepping away and creeps toward you.
#
#   "height"  How HIGH UP the target sits in the picture. With the camera fixed,
#             something far away appears low in the frame and something near
#             appears high. Turning your head does not move it, so it does not
#             drift - but it assumes the camera does not get knocked, and it is
#             calibrated for one person's height and posture.
#
#             The live view draws the three thresholds as horizontal lines, so
#             "on the line" really does mean "at the right distance".
#
# Both feed the SAME follow / hold / back logic below. Whichever is chosen, the
# number given to the brain gets bigger as the target gets nearer.
MEASURE = "height"

_BANDS_WIDTH = {                # how wide the target looks, in pixels
    "color": (89, 104, 130),    # 20 cm target:     ~0.94 m / 0.80 m / 0.64 m
    "face":  (57, 66, 79),      # a face:  35 in / 30 in / 25 in  =  0.89 / 0.76 / 0.64 m
                                # Measured, not calculated: w=66 was read on the bar
                                # at a tape-measured 30 inches.
}

_BANDS_HEIGHT = {               # how far the target's BOTTOM edge is above the
                                # bottom of the picture, in pixels (0 = at the very
                                # bottom = right in front of the robot)
    # The middle number is where it parks, and 180 puts that line exactly halfway
    # down the picture (the frame is 360 tall, and these count UP from the bottom).
    # Chin on the middle line = the right distance. Below it = too far, it comes to
    # you. Above it = too close, it backs off.
    #   Parks too far away  -> raise all three
    #   Parks too close     -> lower all three
    #   Fusses over nothing -> spread them further apart
    "color": (145, 180, 225),
    "face":  (145, 180, 225),
}

BANDS = _BANDS_WIDTH if MEASURE == "width" else _BANDS_HEIGHT
# NOTE for face mode: following this close only works if the camera can SEE your face
# from there. On a table, level with a seated person, it is fine - that is how these
# numbers were set. On the floor at 20 cm tilted 30 deg, the frame at 0.55 m covers
# only 0.27-1.0 m above the ground (your hip, not your head), so a STANDING person
# would drop out of shot as the robot closed in. For that, the camera needs to be
# about 45-50 cm up and tilted ~45 deg. See section 4.4 of the build plan.
#
# To re-measure these: run face mode, stand where you want it to stop, and read the
# distance bar at the bottom of the live view - the marker's w is your STOP number.


# ---- 2. STEERING: zones across the picture (pixels from the center) --------
#
#   |  curve hard   |  curve toward  | straight |  curve toward  |  curve hard   |
#   0              120              210   240  270              360            480
#        (slowest)                       center                        (slowest)
DEAD_ZONE = 30      # Within +-30 px of the center counts as "centered": no turning.
                    #   Wiggles left-right when you stand still -> make it bigger.
                    #   Doesn't point straight at you           -> make it smaller.

ALIGN_ZONE = 120    # Where the slowdown below reaches its minimum. Past this, the robot
                    # is turning about as hard as it will, and driving at its slowest.

TURN_SLOWDOWN = 0.45  # How much it slows down while turning toward you.
                    # The further off-center you are, the slower it drives - at
                    # ALIGN_ZONE or beyond it drives at 45% of SPEED_FWD, so it
                    # CURVES round toward you instead of stopping to pivot.
                    #   1.0  = never slows down (wide, lazy curves; may drive past you)
                    #   0.45 = the current balance
                    #   0.0  = stops dead and spins on the spot (the old behaviour)

KP = 35             # How hard to turn: the turn % when the target is at the very edge.
                    #   turn = KP x (how far off-center / half the picture width)
                    #   e.g. target at x=300: 60 px off -> 35 x 60/240 = 9 % turn
                    #   Overshoots and wobbles -> lower it. Turns too lazily -> raise it.

TURN_MAX = 25       # Never turn harder than this %, however far off-center.


# ---- Turning in short bursts -------------------------------------------------
# The motors cannot rotate slowly. The Uno's MIN_PWM is 90, so turn=5 and turn=25
# both come out near the same wheel speed - there is a floor below which the wheels
# just buzz. The only way to turn SLOWLY is to turn in short bursts and pause
# between them, which is also what gives the camera sharp pictures to work with.
#
#   burst   pause   burst   pause  ...
#   0.15 s  0.25 s
#
# The effect: it creeps in small steps instead of sweeping, and every pause is
# 2-3 clean frames at 10 fps.
#
# This applies to DRIVING as well as turning, and that matters more than it sounds:
# a robot that drives continuously never gets a sharp picture of the person it is
# driving toward, so it cannot tell when it has arrived. Stepping forward and
# pausing to look is what lets it stop at the right distance instead of creeping
# into you.
#   Still blurry / overshoots you -> shorter PULSE_ON, or longer PULSE_OFF
#   Too slow                      -> longer PULSE_ON, or shorter PULSE_OFF
#   Want the old continuous motion -> PULSE_TURN = False
PULSE_TURN = True
PULSE_ON = 0.25     # seconds of actually moving
PULSE_OFF = 0.22    # seconds of standing still and looking. Must be long enough for
                    # 2-3 camera frames: at 12 fps that is about 0.2 s.


# ---- Speeds (% of full motor speed) ------------------------------------------
SPEED_FWD = 30      # driving toward the target. Note this is the speed DURING a step -
                    # the pauses mean the robot actually closes at a bit over half of it.
                    # Real approach speed is roughly SPEED_FWD x PULSE_ON/(PULSE_ON+PULSE_OFF).
                    # Originally: Kept deliberately low: the robot acts on
                    # pictures up to 100 ms old at 10 fps, so a fast robot overshoots and
                    # then hunts back and forth. Raise it once the room is bright and the
                    # camera manages ~20 fps.
SPEED_BACK = 22     # backing away when it's too close (it cannot see behind itself, so
                    # this is always gentler than driving forward)


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
SEARCH_TURN = 28        # Turn speed while searching, %. Brisker than the gentle turning it
                        # uses to follow you (TURN_MAX), and that is on purpose: while
                        # searching it only has to SPOT you, and it does that during the
                        # standing-still pauses below, so a faster burst costs nothing.
                        # Each burst moves ~26 deg and the camera sees 60 deg, so it still
                        # cannot skip past you between looks.
                        #   Misses you while sweeping past -> lower it, or lengthen SEARCH_LOOK
                        #   Takes too long to look around  -> raise it

# The robot searches in little steps: turn a bit, STOP AND LOOK, turn a bit more.
# Why not just spin slowly and evenly? Because the camera only manages 10-20 pictures
# a second, and while the robot is turning every one of them is smeared and taken from
# a different angle - so the face detector misses you even though you are right there.
# Standing still for a moment gives it a few clean, sharp pictures to work with.
#   Still sweeping past you   -> longer SEARCH_LOOK, or smaller SEARCH_STEP
#   Too slow to look around   -> longer SEARCH_STEP, or shorter SEARCH_LOOK
SEARCH_STEP = 0.25      # seconds of turning in each little step
SEARCH_LOOK = 0.50      # seconds standing still afterwards, looking. Needs to be long enough
                        # for 3-4 camera frames: at 10 fps that is 0.3-0.4 s.
SEARCH_SWEEP = 1.0      # Seconds of the first sweep (must be more than 0). Every next sweep is
                        # that much longer. Bigger = wider first look before turning back.
                        # (In the simulator 1.0 s = ~90 degrees, so sweep 3 already looks behind.)
SEARCH_GIVE_UP = 35     # Seconds: stop searching after this long and wait. 0 = never give up.
                        # It sweeps at about 22 deg/s now (gentle, in bursts), so it needs
                        # longer than it used to. 35 s reaches roughly 120 deg either side.


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
            if self.lost <= LOST_GRACE:
                # Just a flicker - keep TURNING the way we were, but stop driving.
                # Repeating the last forward command while blind is how a follower
                # walks into the person it is following: moving blurs the picture,
                # the blur loses the face, and "keep doing the last thing" then means
                # "keep driving at them". Turning blind is harmless; driving is not.
                self.cmd = (0, self.cmd[1])
                return self.cmd
            if self.state not in ("search", "idle"):     # really gone: start searching
                self.state, self.search_start = "search", now
            turn = self.search_turn(now - self.search_start) if self.state == "search" else None
            if turn is None:                            # searching is off, or we gave up: stop and wait
                self.state, turn = "idle", 0
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

            # Slow down while turning, the further off-center the slower - so the robot
            # CURVES toward you instead of stopping to spin. It never stops driving.
            lean = min(1.0, abs(err) / ALIGN_ZONE)
            fwd = round(fwd * (1 - (1 - TURN_SLOWDOWN) * lean))

        # -- 3. Move in steps, with a pause to look --
        # Both wheels stop during the pause, so the camera gets a sharp picture of
        # where you are before the next step. Without this the robot is blurring its
        # own view every moment it is moving.
        if PULSE_TURN and (now % (PULSE_ON + PULSE_OFF)) >= PULSE_ON:
            fwd = turn = 0

        self.cmd = (fwd, turn)
        return self.cmd

    def search_turn(self, elapsed):
        """The turn % while searching, `elapsed` seconds into the search.

        Returns 0 during the standing-still half of a step - that is a PAUSE, not the
        end of the search - and None only when the search is over (switched off, or
        given up). Those two must stay different: treating a pause as "give up" makes
        the robot freeze after its very first burst and never look again."""
        if not SEARCH or (SEARCH_GIVE_UP and elapsed > SEARCH_GIVE_UP):
            return None
        sweep, t = 1, elapsed
        while t >= sweep * SEARCH_SWEEP:        # which sweep are we in? sweep n lasts n x SEARCH_SWEEP
            t -= sweep * SEARCH_SWEEP
            sweep += 1
        side = self.last_side if sweep % 2 == 1 else -self.last_side   # odd sweeps: toward the last-seen side

        # Inside the sweep, alternate: turn for SEARCH_STEP, then hold still for
        # SEARCH_LOOK so the camera gets sharp pictures to search in.
        if t % (SEARCH_STEP + SEARCH_LOOK) >= SEARCH_STEP:
            return 0                            # the looking half of the step: wheels still
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
