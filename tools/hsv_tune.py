# HSV tuner - find the HSV range of your target color under the current lighting.
# Drag the sliders until ONLY your target is white in the mask (right half),
# then press q: the numbers are printed, ready to paste into COLORS.
# Tip: click on your object to see its HSV value.
# Run:  .venv\Scripts\python tools\hsv_tune.py        (add 1 for the second camera)
import sys

import cv2
import numpy as np

CAMERA = int(sys.argv[1]) if len(sys.argv) > 1 else 0
W, H = 480, 360                 # same size as the robot, so the numbers match
WINDOW = "HSV tuner"

# Sliders start at the yellow range from steps/02_color_detect.py
START = {"H low": 22, "S low": 120, "V low": 100, "H high": 38, "S high": 255, "V high": 255}
TOP = {"H": 179, "S": 255, "V": 255}      # OpenCV hue goes 0-179, S and V go 0-255

clicked = None                  # (x, y) of the last mouse click


def on_click(event, x, y, flags, param):
    global clicked
    if event == cv2.EVENT_LBUTTONDOWN:
        clicked = (x % W, y)    # works on either half of the window


cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    sys.exit("Camera not found - try: python tools\\hsv_tune.py 1")

cv2.namedWindow(WINDOW)
cv2.setMouseCallback(WINDOW, on_click)
for name, value in START.items():
    cv2.createTrackbar(name, WINDOW, value, TOP[name[0]], lambda v: None)

lo = [START["H low"], START["S low"], START["V low"]]
hi = [START["H high"], START["S high"], START["V high"]]

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # Read the six sliders
    lo = [cv2.getTrackbarPos(n, WINDOW) for n in ("H low", "S low", "V low")]
    hi = [cv2.getTrackbarPos(n, WINDOW) for n in ("H high", "S high", "V high")]

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))

    # Left: camera. Right: mask (white = matches the range).
    view = np.hstack([frame, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)])
    cv2.putText(view, f"low {tuple(lo)}   high {tuple(hi)}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    if clicked is not None:
        x, y = clicked
        h, s, v = hsv[y, x]
        cv2.circle(view, (x, y), 5, (0, 0, 255), 2)
        cv2.putText(view, f"clicked HSV = ({h}, {s}, {v})", (10, H - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow(WINDOW, view)
    if (cv2.waitKey(1) & 0xFF) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

print("Paste this into COLORS in steps/02_color_detect.py:")
print(f'    "yellow": ({tuple(lo)}, {tuple(hi)}),')
