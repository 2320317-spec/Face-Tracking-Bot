# =============================================================================
# moves.py - the robot's tricks: spin, dance, nod, shake
# =============================================================================
# These are canned routines: a fixed list of "drive like this for this long"
# steps. Nothing to do with following - while a trick plays, it takes over the
# wheels completely, then hands them back to brain.py.
#
# A trick only ever runs because YOU pressed its button on the dashboard (or a
# key in the simulator). The robot never starts one by itself, and pressing STOP
# cancels whatever is playing.
#
# ---- How a move is written --------------------------------------------------
# Each step is (fwd, turn, seconds), using the same numbers as the brain:
#     fwd   -100..100   + forward, - backwards
#     turn  -100..100   + right,   - left
#     seconds           how long to hold it
# (0, 0, 0.1) is a short pause, which is what makes a rhythm feel crisp.
#
# ---- Tuning them ------------------------------------------------------------
# The timings below are guesses until the real robot drives. On the floor:
#   spins more/less than one full turn -> change SPIN_TIME
#   the dance drifts across the room   -> the left and right steps aren't equal;
#                                         make the times match exactly
#   it barely moves                    -> the turn values are below the Uno's
#                                         MIN_PWM, so raise them
# Try them in the simulator first (steps/04b_simulator.py, keys 1-4).
# =============================================================================
import time


# ---- Settings ---------------------------------------------------------------
# TEMPO is the one number that makes every trick quicker or slower. Everything
# below is written at the original pace and divided by TEMPO, so this is the only
# line you need to touch.
#   1.00  the pace the tricks were first written at
#   1.15  15% faster - where they are now
# Careful going much past this: see the frame-rate note at the bottom of the
# settings. The robot only decides ~12 times a second, and a step shorter than
# one decision can be stretched or skipped entirely.
TEMPO = 1.15

# Spinning is the one trick where "faster" cannot mean "stop sooner" - it has to
# come back round to face you. So TEMPO spins it HARDER and it finishes earlier,
# and the two cancel out to the same one full turn.
SPIN_TURN = round(60 * TEMPO)   # how hard it spins on the spot, %
SPIN_TIME = 1.63 * 60 / SPIN_TURN
                        # seconds for ONE full turn at SPIN_TURN. The 1.63 came out of
                        # the simulator's motion model (0.45 m/s wheels, 14 cm apart),
                        # so it is a good starting point - but check it on the floor.

BEAT = 0.30 / TEMPO     # the dance's rhythm: seconds per "step". Smaller = faster dancing.
BEAT_TURN = 55          # how hard it turns on each dance step, %
GAP = 0.08 / TEMPO      # tiny pause between steps, so they read as separate moves

NOD_FWD = 45            # how hard it bumps forward and back when nodding, %
NOD_TIME = 0.22 / TEMPO # seconds per bump - short, or it drives across the room

SHAKE_TURN = 45         # how hard it flicks left/right when shaking, %
SHAKE_TIME = 0.18 / TEMPO   # seconds per flick - short, that's what makes it a shake

HOLD = 0.20 / TEMPO     # the pause each trick ends on

# ---- The frame-rate ceiling -------------------------------------------------
# A step only exists if the robot is awake to run it. In a dim room it decides
# about 12 times a second, so one decision is 83 ms, and a step of 0.13 s is
# 1.6 decisions - it may be sampled once or twice, which is what makes a rhythm
# come out lopsided. At TEMPO 1.15 the shortest steps are:
#
#   GAP        (the pause between steps)  0.07 s   0.8 decisions   under one
#   BEAT / 2   (the dance's double steps) 0.13 s   1.6 decisions   marginal
#   SHAKE_TIME (one flick of the shake)   0.16 s   1.9 decisions   marginal
#
# GAP has been under one decision since the tricks were written, so the dance
# steps have never been reliably separated - this does not make it worse. The
# real fix for both is more frames (see docs/progress.md, "chase the frame rate"),
# not a slower TEMPO. If the dance looks ragged on the floor, try TEMPO = 1.10.


def _step(turn, seconds):
    """One turning step, followed by the small gap."""
    return [(0, turn, seconds), (0, 0, GAP)]


# ---- The tricks -------------------------------------------------------------
# left = negative turn, right = positive turn.
MOVES = {
    # One full turn on the spot, then stop.
    "spin": [
        (0, SPIN_TURN, SPIN_TIME),
        (0, 0, HOLD),
    ],

    # "single single double double": one step left, one right,
    # then two lefts and two rights - a rhythm, not just wagging.
    "dance": (
        _step(-BEAT_TURN, BEAT) +                       # single left
        _step(+BEAT_TURN, BEAT) +                       # single right
        _step(-BEAT_TURN, BEAT / 2) * 2 +               # double left  (two quick ones)
        _step(+BEAT_TURN, BEAT / 2) * 2 +               # double right
        [(0, 0, HOLD * 1.25)]                           # hold the ending
    ),

    # "Yes": short forward-and-back bumps.
    "nod": [
        (+NOD_FWD, 0, NOD_TIME), (-NOD_FWD, 0, NOD_TIME),
        (0, 0, HOLD / 2),
        (+NOD_FWD, 0, NOD_TIME), (-NOD_FWD, 0, NOD_TIME),
        (0, 0, HOLD),
    ],

    # "No": quick little flicks left and right, staying on the spot.
    "shake": [
        (0, -SHAKE_TURN, SHAKE_TIME), (0, +SHAKE_TURN, SHAKE_TIME),
        (0, -SHAKE_TURN, SHAKE_TIME), (0, +SHAKE_TURN, SHAKE_TIME),
        (0, -SHAKE_TURN, SHAKE_TIME), (0, +SHAKE_TURN, SHAKE_TIME),
        (0, 0, HOLD),
    ],
}

# What each one is called on screen.
NAMES = {"spin": "SPIN", "dance": "DANCE", "nod": "NOD", "shake": "SHAKE"}


def length(name):
    """How many seconds the whole trick takes."""
    return sum(seconds for _, _, seconds in MOVES[name])


class Player:
    """Plays one trick, step by step.

    Used the same way by the robot and by the simulator:
        player.start("dance", now)      begin
        cmd = player.update(now)        every frame: (fwd, turn), or None when it has finished
        player.stop()                   cancel it (STOP does this)

    `now` is seconds from any clock. follow.py leaves it out and gets the real
    time; the simulator passes its own clock so tricks run at simulator speed."""

    def __init__(self):
        self.name = None            # which trick is playing, or None
        self.started = 0.0          # when it started, in whatever clock was used

    def start(self, name, now=None):
        """Begin a trick. An unknown name is ignored rather than crashing the robot."""
        if name not in MOVES:
            return False
        self.name = name
        self.started = time.time() if now is None else now
        return True

    def stop(self):
        self.name = None

    def playing(self):
        return self.name is not None

    def update(self, now=None):
        """The command for this frame: (fwd, turn) - or None when the trick is over
        (and then the robot goes back to following)."""
        if self.name is None:
            return None
        if now is None:
            now = time.time()

        # Walk through the steps, subtracting each one's length, until we land in
        # the step that is playing right now.
        elapsed = now - self.started
        for fwd, turn, seconds in MOVES[self.name]:
            if elapsed < seconds:
                return (fwd, turn)
            elapsed -= seconds

        self.name = None                                # ran off the end: finished
        return None

    def status(self, now=None):
        """(text, kind) for the dashboard - e.g. ("DANCE 1.2s", "move")."""
        if self.name is None:
            return None
        if now is None:
            now = time.time()
        left = max(0.0, length(self.name) - (now - self.started))
        return f"{NAMES[self.name]}  {left:.1f}s", "move"
