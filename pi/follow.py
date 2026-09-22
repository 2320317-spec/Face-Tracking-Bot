# =============================================================================
# follow.py - the robot program (roadmap step 6)
# =============================================================================
# Steps 1-5 in one program, plus the phone dashboard. Every frame:
#   1. SEE     grab the newest camera frame                        (vision.Camera)
#   2. FIND    the target: a color, a face - or nothing (manual)    (vision.py)
#   3. DECIDE  forward speed + turn, or search when it's lost       (brain.py)
#   4. ACT     send "fwd turn" to the Arduino Uno over USB          (step 7 is the Uno side)
#   5. SHOW    status + live view for the web page                  (web.py)
#
# Modes (chosen on the web page):
#   color   follow the colored target (COLOR / COLORS in vision.py)
#   face    follow a face - Simple = whoever it sees, Smart = only you
#   manual  drive with the on-screen joystick
# The robot starts STOPPED: nothing moves until you press Start on the page.
#
# Settings live where they belong: brain.py = driving decisions, vision.py = camera,
# colors and faces, this file = manual driving, the Uno link and the live view.
#
# Run on the robot (Pi, Uno plugged in):  ~/robot-venv/bin/python pi/follow.py
# Run without the Uno (laptop, or the Pi before the Uno is ready):
#                                         python pi/follow.py --dry        (add --camera 1 if needed)
# Then open the dashboard: http://followbot.local:8000 (Pi)  or  http://localhost:8000 (laptop)
# Stop the program: Ctrl+C
# =============================================================================
import argparse
import glob
import time

import cv2

import web
from brain import W, H, DEAD_ZONE, ALIGN_ZONE, Follower, describe
from vision import Camera, find_color, FaceTools, FaceLock, head_turn, LEARN_MAX, FOCAL, FACE_WIDTH_M


# ---- Settings ---------------------------------------------------------------------
MANUAL_FWD = 70         # joystick pushed fully up = this % forward speed
MANUAL_TURN = 50        # joystick pushed fully sideways = this % turn
MANUAL_TIMEOUT = 0.5    # seconds without a joystick update -> stop (phone locked, WiFi dropped)

BAUD = 115200           # serial speed to the Uno - must match Serial.begin() in the Uno sketch
STREAM_QUALITY = 70     # live view JPEG quality, 0-100. Lower = less WiFi traffic, blurrier picture.

BUTTON_PIN = 17         # optional backup Start/Stop button on the Pi:
                        # GPIO17 (pin 11) -> button -> GND (pin 9). Works even if the WiFi doesn't.

FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN, CYAN, YELLOW, ORANGE, PINK, GRAY, WHITE = ((0, 255, 0), (255, 255, 0), (0, 220, 255),
                                                  (0, 165, 255), (255, 0, 255), (160, 160, 160), (255, 255, 255))


# ---- The Uno link --------------------------------------------------------------------
def open_uno(port=None):
    """Open the USB serial link to the Uno. On the Pi it finds the Uno by itself."""
    import serial                                       # pyserial
    if port is None:
        ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))   # Uno = ttyACM0 or ttyUSB0
        if not ports:
            raise SystemExit("Uno not found - plug it in (with a data USB cable), or run with --dry")
        port = ports[0]
    uno = serial.Serial(port, BAUD, timeout=0)
    time.sleep(2)                                       # opening the port restarts the Uno: let it boot
    print(f"Uno connected on {port}")
    return uno


def send(uno, fwd, turn):
    """One line per frame: "fwd turn\\n". The Uno stops the motors by itself if these stop coming."""
    if uno is not None:
        uno.write(f"{fwd} {turn}\n".encode())


def setup_button(shared):
    """Optional backup Start/Stop button on the Pi's GPIO pins. Does nothing on a laptop."""
    try:
        from gpiozero import Button
        button = Button(BUTTON_PIN, bounce_time=0.1)
    except Exception:                                   # laptop, or no GPIO library
        return None

    def toggle():
        shared.running = not shared.running
    button.when_pressed = toggle
    return button                                       # keep it: if it's thrown away, it stops working


# ---- The live view picture -------------------------------------------------------------
def put_label(frame, text, x, y, color, size=0.5, thickness=2):
    """Write text at (x, y), but pushed back inside the picture if it would run off the edge."""
    (tw, th), _ = cv2.getTextSize(text, FONT, size, thickness)
    x = max(2, min(x, W - tw - 2))
    y = max(th + 2, min(y, H - 4))
    cv2.putText(frame, text, (x, y), FONT, size, color, thickness)


def draw_face(frame, face, color, text, landmarks):
    """A face box with a label above it; landmarks=True adds all 5 points and the head-turn arrow."""
    x, y, w, h = face["box"]
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    if text:
        put_label(frame, text, x, y - 8, color)
    if landmarks:
        right_eye, left_eye, nose, right_mouth, left_mouth = face["points"]
        cv2.line(frame, right_eye, left_eye, CYAN, 1)
        cv2.line(frame, right_mouth, left_mouth, PINK, 1)
        for p, c in ((right_eye, CYAN), (left_eye, CYAN), (nose, ORANGE), (right_mouth, PINK), (left_mouth, PINK)):
            cv2.circle(frame, p, 3, c, -1)
        turn_text, offset = head_turn(face)
        if turn_text != "straight":
            cv2.arrowedLine(frame, nose, (int(nose[0] + offset * w * 0.8), nose[1]), ORANGE, 2, tipLength=0.4)


def live_view(frame, mode, who, box, faces, followed, lock, state_text, fwd, turn):
    """Draw what the robot sees and decides onto the frame, and return it as a JPEG picture."""
    # steering zones from brain.py: gray band = dead zone, dark lines = align zone
    cv2.rectangle(frame, (W // 2 - DEAD_ZONE, 0), (W // 2 + DEAD_ZONE, H), (90, 90, 90), 1)
    for x in (W // 2 - ALIGN_ZONE, W // 2 + ALIGN_ZONE):
        cv2.line(frame, (x, 0), (x, H), (60, 60, 60), 1)

    if mode == "color" and box is not None:
        x, y, w, h = box
        cv2.rectangle(frame, (x, y), (x + w, y + h), GREEN, 2)
        put_label(frame, f"x={x + w // 2}  w={w}", x, y - 8, GREEN)

    if mode == "face":
        checked = {id(f): sim for f, sim in lock.checked} if who == "smart" else {}
        for f in faces:                                 # faces we are NOT following: gray
            if f is not followed:
                text = f"not you {checked[id(f)]:.2f}" if id(f) in checked else ""
                draw_face(frame, f, GRAY, text, landmarks=False)
        if followed is not None and who == "simple":
            x, y, w, h = followed["box"]
            draw_face(frame, followed, GREEN, f"x={x + w // 2}  w={w}  {followed['score']:.0%}", landmarks=False)
        elif followed is not None:                      # smart: details, distance and match
            name = "YOU" if lock.knows_you() else "LOCKED"
            draw_face(frame, followed, GREEN, f"{name}  x={round(lock.x)} w={round(lock.w)}", landmarks=True)
            x, y, w, h = followed["box"]
            cv2.drawMarker(frame, (int(lock.x), y + h // 2), YELLOW, cv2.MARKER_CROSS, 14, 2)   # what it steers by
            details = f"~{FOCAL * FACE_WIDTH_M / lock.w:.1f} m  face {followed['score']:.0%}"
            if lock.similarity is not None:
                details += f"  match {lock.similarity:.2f}"
            put_label(frame, details, x, min(y + h + 18, H - 30), YELLOW, 0.45, 1)
        elif who == "smart" and lock.face is not None:  # just lost you: where you were
            fx, fy, fw, fh = lock.face["box"]
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), YELLOW, 1)
            put_label(frame, "last seen", fx, fy - 8, YELLOW, 0.45, 1)

    put_label(frame, f"{state_text}  |  {describe(fwd, turn)}", 8, H - 10, WHITE, 0.5, 1)
    return cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY])[1].tobytes()


# ---- The program --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="FollowBot - the robot program")
    ap.add_argument("--dry", action="store_true", help="no Uno: run everything but send nothing to the motors")
    ap.add_argument("--port", help="the Uno's serial port (default: find it; on Windows e.g. COM5)")
    ap.add_argument("--camera", type=int, default=0, help="camera number (default 0)")
    ap.add_argument("--web-port", type=int, default=8000, help="dashboard port (default 8000)")
    ap.add_argument("--mode", choices=["color", "face", "manual"], default="color", help="mode at start")
    args = ap.parse_args()

    cam = Camera(args.camera)
    uno = None if args.dry else open_uno(args.port)
    tools = FaceTools()                     # the face models
    lock = FaceLock(tools)                  # Smart mode's memory: where you are, and who you are
    bot = Follower()                        # the brain
    shared = web.Shared(args.mode)          # shared with the web page
    web.start(shared, args.web_port)
    button = setup_button(shared)
    print(f"Dashboard on port {args.web_port}. The robot is STOPPED until you press Start.")

    mode, who = shared.mode, shared.who
    fps, frames, t0 = 0.0, 0, time.time()
    try:
        while True:
            # ---- 1. SEE ----
            frame = cam.read()
            if frame is None:                           # camera stopped sending: stop the wheels
                send(uno, 0, 0)
                shared.status = shared.status | {"state": "CAMERA NOT SENDING", "kind": "lost"}
                continue

            # ---- changes from the web page ----
            if (shared.mode, shared.who) != (mode, who):    # new mode: start fresh
                mode, who = shared.mode, shared.who
                bot.reset()
                lock.reset()
            if shared.forget:                           # "Forget me"
                lock.reset()
                shared.forget = False
            if shared.click is not None:                # tap on a face: "this is me"
                lock.click, shared.click = shared.click, None

            # ---- 2. FIND the target: (center x, width w), or None ----
            box, faces, followed, target = None, [], None, None
            if mode == "color":
                box, _ = find_color(frame)
                if box is not None:
                    target = (box[0] + box[2] // 2, box[2])
            elif mode == "face":
                faces = tools.find(frame)
                if who == "simple":                     # whoever is biggest
                    followed = faces[0] if faces else None
                    if followed is not None:
                        x, y, w, h = followed["box"]
                        target = (x + w // 2, w)
                else:                                   # only you, smoothed
                    followed = lock.update(frame, faces)
                    if followed is not None:
                        target = (round(lock.x), round(lock.w))

            # ---- 3. DECIDE ----
            if not shared.running:                      # STOPPED: wheels still, brain waits
                bot.reset()
                fwd, turn = 0, 0
                state_text, kind = "STOPPED - press Start", "idle"
            elif mode == "manual":                      # the joystick drives
                fresh = time.time() - shared.joystick_t < MANUAL_TIMEOUT
                jf, jt = shared.joystick if fresh else (0, 0)
                fwd, turn = round(jf * MANUAL_FWD / 100), round(jt * MANUAL_TURN / 100)
                state_text, kind = "MANUAL", "manual"
            else:                                       # the brain decides (follow / hold / back / search)
                fwd, turn = bot.update(target, mode)
                state_text, kind = bot.status()

            # ---- 4. ACT ----
            send(uno, fwd, turn)

            # ---- 5. SHOW ----
            frames += 1
            now = time.time()
            if now - t0 >= 1:                           # once a second: fps, and a line on the terminal
                fps, frames, t0 = frames / (now - t0), 0, now
                print(f"{fps:4.1f} fps  {mode}{'/' + who if mode == 'face' else ''}  {state_text}  "
                      f"w={target[1] if target else '-'}  cmd={fwd} {turn}")
            shared.status = {
                "state": state_text, "kind": kind, "w": target[1] if target else None,
                "cmd": f"{fwd} {turn}", "fps": round(fps, 1), "faces": len(faces),
                "knows_you": lock.knows_you(), "prints": len(lock.prints), "learn_max": LEARN_MAX,
                "recognizer": tools.recognizer is not None, "uno": uno is not None,
            }
            if shared.viewers:                          # only draw the live view if someone is watching
                shared.jpeg = live_view(frame, mode, who, box, faces, followed, lock,
                                        state_text, fwd, turn)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        send(uno, 0, 0)                                 # always leave the wheels stopped
        cam.close()
        if uno is not None:
            uno.close()


if __name__ == "__main__":
    main()
