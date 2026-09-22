# Step 1 - live camera feed
# Shows the webcam at 480x360 (the size the robot works at) with an FPS counter.
# Run:  .venv\Scripts\python steps\01_live_feed.py      Quit: press q in the video window
import sys
import time

import cv2

CAMERA = 0             # which camera? 0 = first, 1 = second (try 1 if you see the laptop camera)
W, H = 480, 360        # size the robot works at

cap = cv2.VideoCapture(CAMERA)

# Ask the camera for 640x480 in MJPG (compressed) - most webcams are much faster this way
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not cap.isOpened():
    sys.exit("Camera not found - try CAMERA = 1")

fps = 0.0              # the number shown on screen
frames = 0             # frames counted since the last FPS update
t0 = time.time()       # when the last FPS update happened

while True:
    ok, frame = cap.read()             # grab one frame from cap
    if not ok:
        break                          # no frame: get out of the loop

    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)   # shrink to the robot's size

    # FPS: count frames; once every second, work out frames per second
    frames = frames + 1
    now = time.time()
    if now - t0 >= 1:
        fps = frames / (now - t0)
        frames = 0
        t0 = now
    cv2.putText(frame, f"{fps:.1f} fps", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("Live feed", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):                # q quits
        break

cap.release()                          # release the camera
cv2.destroyAllWindows()                # close the windows
