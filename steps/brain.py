# brain.py - the robot's decision logic, shared by step 4 (webcam) and step 4b (simulator).
# Change a setting here and both use it.
#   fwd  = forward speed  -100..100   (+ forward, - reverse)
#   turn = turn rate      -100..100   (+ right,   - left)

W, H = 480, 360        # camera image size the robot works at

# Distance bands per mode: (resume, stop, backup) = target width w in pixels.
# resume < stop < backup. To set them: hold your object where the robot should
# stop, read w on screen, use it as stop; resume ~0.8x stop, backup ~1.25x stop.
BANDS = {
    "color": (64, 83, 104),     # 20 cm target: ~1.3 m / 1.0 m / 0.8 m
    "face":  (33, 42, 54),      # face: ~1.9 m / 1.5 m / 1.15 m
}
DEAD_ZONE  = 30    # px either side of the center line that counts as "centered"
ALIGN_ZONE = 120   # px; further off-center than this -> turn in place, don't drive
KP         = 60    # turn % when the target is at the very edge of the frame
TURN_MAX   = 60    # never turn harder than this %
SPEED_FWD  = 50    # forward speed %
SPEED_BACK = 40    # reverse speed %
LOST_GRACE = 5     # frames to keep going when the target flickers out, then stop


class Follower:
    """The robot's brain: turns (target center x, target width w) into (fwd, turn)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "follow"                   # follow | hold | back
        self.lost = 0                           # frames since the target was last seen
        self.cmd = (0, 0)

    def update(self, target, mode):
        """target = (x, w) in pixels, or None. Returns (fwd, turn), each -100..100."""
        if target is None:
            self.lost += 1
            if self.lost > LOST_GRACE:          # really gone: stop and re-arm
                self.state, self.cmd = "follow", (0, 0)
            return self.cmd                     # brief flicker: keep going
        self.lost = 0
        x, w = target
        resume_w, stop_w, backup_w = BANDS[mode]

        # Distance: three states with hysteresis (gaps between the thresholds)
        if w > backup_w:
            self.state = "back"
        elif self.state == "follow" and w >= stop_w:
            self.state = "hold"
        elif self.state == "hold" and w <= resume_w:
            self.state = "follow"
        elif self.state == "back" and w <= stop_w:
            self.state = "hold"
        fwd = {"follow": SPEED_FWD, "hold": 0, "back": -SPEED_BACK}[self.state]

        # Steering: proportional to how far off-center the target is
        err = x - W // 2
        turn = 0
        if abs(err) > DEAD_ZONE:
            turn = round(KP * err / (W / 2))
            turn = max(-TURN_MAX, min(TURN_MAX, turn))
        if abs(err) > ALIGN_ZONE:
            fwd = 0                             # center first, then drive

        self.cmd = (fwd, turn)
        return self.cmd


def wheels(fwd, turn):
    """Left and right wheel speeds - the same mixing the Uno will do."""
    left, right = fwd + turn, fwd - turn
    biggest = max(abs(left), abs(right))
    if biggest > 100:                           # scale both down, keep the curve
        left, right = int(left * 100 / biggest), int(right * 100 / biggest)
    return left, right


def describe(fwd, turn):
    """The command in plain English."""
    if fwd == 0 and turn == 0:
        return "STOP"
    side = "right" if turn > 0 else "left"
    if fwd == 0:
        return f"SPIN {side.upper()} in place"
    move = "FORWARD" if fwd > 0 else "BACK UP"
    return move if turn == 0 else f"{move} + curve {side}"
