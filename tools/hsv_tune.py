# =============================================================================
# HSV tuner - find the HSV range of your target color under the current lighting
# =============================================================================
# How to use:
#   1. Hold your object in front of the camera, in the light you'll really use.
#   2. Click on the object: its HSV value appears in red at the bottom.
#      That's the middle your range should cover.
#   3. Drag the six sliders until ONLY the object is white in the mask (right half):
#        white specks in the background -> raise "S low" first, then narrow H
#        black holes in the object      -> lower "S low" or "V low", or widen H
#   4. Press q: the numbers are printed, ready to paste into COLORS in step 2.
#
# Run:  .venv\Scripts\python tools\hsv_tune.py        (add 1 for the second camera)
# =============================================================================
import sys

import cv2
import numpy as np


# ---- Settings ----------------------------------------------------------------
CAMERA = int(sys.argv[1]) if len(sys.argv) > 1 else 0   # camera number from the command line, else 0
W, H = 480, 360                 # same size as the robot, so the numbers match exactly
WINDOW = "HSV tuner"

# Where the sliders start: the yellow range from steps/02_color_detect.py
START = {"H low": 22, "S low": 120, "V low": 100, "H high": 38, "S high": 255, "V high": 255}
TOP = {"H": 179, "S": 255, "V": 255}      # slider maximums: OpenCV hue goes 0-179, S and V 0-255

clicked = None                  # (x, y) of the last mouse click, or None


def on_click(event, x, y, flags, param):
    """OpenCV calls this on every mouse event in the window."""
    global clicked
    if event == cv2.EVENT_LBUTTONDOWN:
        clicked = (x % W, y)    # "% W": a click on the mask half maps to the same spot


# ---- Open the camera (same as step 1) ------------------------------------------
cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try: python tools\\hsv_tune.py 1")

# The window, its mouse handler, and the six sliders
cv2.namedWindow(WINDOW)
cv2.setMouseCallback(WINDOW, on_click)
for name, value in START.items():
    # createTrackbar(name, window, start value, maximum, function called on change - not needed)
    cv2.createTrackbar(name, WINDOW, value, TOP[name[0]], lambda v: None)

lo = [START["H low"], START["S low"], START["V low"]]      # current range (so it can be printed
hi = [START["H high"], START["S high"], START["V high"]]   # even if the loop ends right away)


# ---- The loop ------------------------------------------------------------------
while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # Read the six sliders
    lo = [cv2.getTrackbarPos(n, WINDOW) for n in ("H low", "S low", "V low")]
    hi = [cv2.getTrackbarPos(n, WINDOW) for n in ("H high", "S high", "V high")]

    # Same test as step 2: white where all three values are inside the range
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))

    # One window, two halves - left: camera, right: mask (turned into 3 channels so they fit side by side)
    view = np.hstack([frame, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)])
    cv2.putText(view, f"low {tuple(lo)}   high {tuple(hi)}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    if clicked is not None:             # show the HSV value where you clicked
        x, y = clicked
        h, s, v = hsv[y, x]             # note: images are indexed [row, column] = [y, x]
        cv2.circle(view, (x, y), 5, (0, 0, 255), 2)
        cv2.putText(view, f"clicked HSV = ({h}, {s}, {v})", (10, H - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow(WINDOW, view)
    if (cv2.waitKey(1) & 0xFF) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# Print the final range in the exact format COLORS uses
print("Paste this into COLORS in steps/02_color_detect.py:")
print(f'    "yellow": ({tuple(lo)}, {tuple(hi)}),')
