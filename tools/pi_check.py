# =============================================================================
# pi_check.py - is this computer ready for FollowBot, and how fast is it?
# =============================================================================
# Checks, in order:
#   1. Python and OpenCV versions   (OpenCV must be 4.8 or newer, but not 5)
#   2. the two face models          (pi/models/)
#   3. SPEED: how long each part of the vision takes on THIS computer
#             (color detection, face detection, face recognition)
#   4. the webcam: does it open, what size and frame rate it really gives
#   5. serial ports: is the Arduino Uno plugged in?
#   6. Raspberry Pi health: temperature, and "throttling" (the Pi slowing itself
#      down because it's too hot or the power supply is too weak)
# No windows - it only prints a report, so it works over SSH on the Pi.
#
# Run:  ~/robot-venv/bin/python tools/pi_check.py        (on the Pi)
#       .venv\Scripts\python tools\pi_check.py           (on the PC, to compare)
# Options:  --camera 1     test the second camera
#           --no-camera    skip the webcam test
# =============================================================================
import argparse
import os
import platform
import subprocess
import sys
import time

import cv2
import numpy as np


# ---- Settings ----------------------------------------------------------------
W, H = 480, 360                      # the size the robot works at (same as brain.py)
RUNS = 20                            # how many times to repeat each speed test (then take the average)
CAMERA_FRAMES = 60                   # how many frames to grab for the webcam test
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MODELS = os.path.join(ROOT, "pi", "models")
DETECT_MODEL = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")
RECOG_MODEL = os.path.join(MODELS, "face_recognition_sface_2021dec.onnx")

problems = []                        # everything that's wrong, repeated at the end


def ok(text):
    print(f"  OK       {text}")


def warn(text):
    print(f"  PROBLEM  {text}")
    problems.append(text)


def timed(function, runs=RUNS):
    """Run function() a few times and return the average time in milliseconds."""
    function()                                       # first run is always slower (warm-up): not counted
    start = time.perf_counter()
    for _ in range(runs):
        function()
    return (time.perf_counter() - start) / runs * 1000


# ---- 1. Versions -----------------------------------------------------------------
def check_versions():
    print("\n1. Versions")
    ok(f"computer: {pi_model() or platform.platform()}")
    ok(f"Python {platform.python_version()}")
    major, minor = (int(v) for v in cv2.__version__.split(".")[:2])
    if major == 4 and minor >= 8:
        ok(f"OpenCV {cv2.__version__}")
    else:
        warn(f"OpenCV {cv2.__version__} - needs 4.8 to 4.x (reinstall from the requirements file)")


# ---- 2. Models -------------------------------------------------------------------
def check_models():
    print("\n2. Face models (pi/models/)")
    for path, what in ((DETECT_MODEL, "YuNet - face detection"), (RECOG_MODEL, "SFace - face recognition")):
        if os.path.exists(path):
            ok(f"{what}: {os.path.getsize(path) / 1e6:.1f} MB")
        else:
            warn(f"{what}: missing - see pi/models/README.md")


# ---- 3. Speed --------------------------------------------------------------------
def check_speed():
    """Time each vision part on a test picture: noise plus a yellow ball."""
    print(f"\n3. Speed at {W}x{H} (average of {RUNS} runs)")
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    cv2.circle(frame, (240, 180), 40, (0, 255, 255), -1)
    camera_frame = cv2.resize(frame, (640, 480))
    kernel = np.ones((3, 3), np.uint8)

    def color():                                     # the same steps as steps/02_color_detect.py
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array((22, 120, 100)), np.array((38, 255, 255)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = {}
    results["resize"] = timed(lambda: cv2.resize(camera_frame, (W, H), interpolation=cv2.INTER_AREA))
    results["color"] = timed(color)
    print(f"  {results['resize']:6.1f} ms  shrinking the camera frame to {W}x{H}")
    print(f"  {results['color']:6.1f} ms  color detection")

    if os.path.exists(DETECT_MODEL):
        detector = cv2.FaceDetectorYN.create(DETECT_MODEL, "", (W, H), score_threshold=0.7)
        results["face"] = timed(lambda: detector.detect(frame))
        print(f"  {results['face']:6.1f} ms  face detection (YuNet)")
    if os.path.exists(RECOG_MODEL):
        recognizer = cv2.FaceRecognizerSF.create(RECOG_MODEL, "")
        # a made-up face row: box + 5 landmarks in plausible places (only the timing matters here)
        row = np.array([200, 130, 80, 100, 220, 165, 260, 165, 240, 190, 225, 210, 255, 210, 0.9], np.float32)
        results["recog"] = timed(lambda: recognizer.feature(recognizer.alignCrop(frame, row)), runs=10)
        print(f"  {results['recog']:6.1f} ms  face recognition, per face (SFace)")

    # What that means for frames per second (the camera itself usually tops out at 30)
    print("  -> best case, not counting the camera and drawing:")
    color_fps = 1000 / (results["resize"] + results["color"])
    print(f"     color mode  ~{min(color_fps, 30):.0f} fps" + ("  (camera-limited)" if color_fps > 30 else ""))
    if "face" in results:
        face_fps = 1000 / (results["resize"] + results["face"])
        print(f"     face mode   ~{min(face_fps, 30):.0f} fps" + ("  (camera-limited)" if face_fps > 30 else ""))
        if face_fps < 10:
            warn(f"face mode only ~{face_fps:.0f} fps - check cooling / throttling below")
    return results


# ---- 4. Webcam -------------------------------------------------------------------
def check_camera(index):
    print(f"\n4. Webcam (camera {index})")
    cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        warn(f"camera {index} doesn't open - is it plugged in? Try --camera 1 (Pi: check 'v4l2-ctl --list-devices')")
        return
    ok_frames, shape = 0, None
    cap.read()                                       # first frame can be slow: not counted
    start = time.perf_counter()
    for _ in range(CAMERA_FRAMES):
        got, frame = cap.read()
        if got:
            ok_frames += 1
            shape = frame.shape
    seconds = time.perf_counter() - start
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    fmt = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4))   # the 4-letter format code, e.g. MJPG
    backend = cap.getBackendName()                   # how OpenCV talks to the camera (V4L2 on the Pi)
    cap.release()
    if ok_frames == 0:
        warn("camera opens but gives no frames")
        return
    ok(f"frames: {shape[1]}x{shape[0]}, format {fmt!r}, backend {backend}")
    fps = ok_frames / seconds
    if fps >= 20:
        ok(f"camera speed: {fps:.1f} fps ({ok_frames}/{CAMERA_FRAMES} frames)")
    else:
        warn(f"camera speed only {fps:.1f} fps - check the MJPG format, the USB port, or more light")


# ---- 5. Serial ports (Arduino Uno) -------------------------------------------------
def check_serial():
    print("\n5. Serial ports (Arduino Uno)")
    try:
        from serial.tools import list_ports          # part of pyserial
    except ImportError:
        warn("pyserial not installed - install the requirements file")
        return
    ports = list(list_ports.comports())
    if not ports:
        print("  --       no serial ports (fine for now - plug the Uno in later)")
    for p in ports:
        ok(f"{p.device}  {p.description}")
        # on Linux you need permission to use a serial port (the "dialout" group)
        if platform.system() == "Linux" and not os.access(p.device, os.R_OK | os.W_OK):
            warn(f"no permission for {p.device} - run: sudo usermod -aG dialout $USER, then log in again")


# ---- 6. Raspberry Pi health ------------------------------------------------------------
def pi_model():
    try:
        with open("/proc/device-tree/model") as f:
            return f.read().strip("\x00\n ")
    except OSError:
        return None                                   # not a Raspberry Pi


def check_pi_health():
    if not pi_model() or not os.path.exists("/usr/bin/vcgencmd"):
        return                                        # only on a Raspberry Pi
    print("\n6. Raspberry Pi health")
    temp = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True).stdout.strip()
    celsius = float(temp.split("=")[1].split("'")[0])    # "temp=48.3'C" -> 48.3
    if celsius < 70:
        ok(f"temperature {celsius:.0f} C")
    else:
        warn(f"temperature {celsius:.0f} C - hot: add a heatsink / fan (the Pi slows down above ~80 C)")

    raw = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True).stdout.strip()
    bits = int(raw.split("=")[1], 16)
    # The bits of get_throttled: low bits = happening NOW, bits 16+ = happened since boot
    meaning = {0: "under-voltage (power supply too weak)", 1: "CPU speed capped",
               2: "throttled (slowed down)", 3: "temperature limit reached"}
    if bits == 0:
        ok("throttled=0x0 - no power or heat problems since boot")
    for bit, text in meaning.items():
        if bits & (1 << bit):
            warn(f"NOW: {text}")
        elif bits & (1 << (bit + 16)):
            warn(f"since boot: {text}")


# ---- Run everything ---------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Is this computer ready for FollowBot?")
    ap.add_argument("--camera", type=int, default=0, help="camera number (default 0)")
    ap.add_argument("--no-camera", action="store_true", help="skip the webcam test")
    args = ap.parse_args()

    print("FollowBot system check")
    check_versions()
    check_models()
    check_speed()
    if not args.no_camera:
        check_camera(args.camera)
    check_serial()
    check_pi_health()

    print("\n" + ("All good!" if not problems else f"{len(problems)} problem(s):"))
    for p in problems:
        print(f"  - {p}")
    sys.exit(1 if problems else 0)
