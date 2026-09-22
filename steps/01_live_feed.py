# =============================================================================
# Step 1 - live camera feed
# =============================================================================
# Shows the webcam at 480x360 (the size the robot works at) with an FPS counter.
#
# How it works - the same loop every later step uses:
#   1. open the camera
#   2. repeat: grab a frame -> shrink it -> draw on it -> show it -> check keys
#   3. clean up
#
# Run:  .venv\Scripts\python steps\01_live_feed.py
# Keys: q = quit (click the video window first)
# =============================================================================
import sys
import time

import cv2


# ---- Settings ----------------------------------------------------------------
CAMERA = 0             # Which camera: 0 = the first one, 1 = the second.
                       # Seeing the laptop's built-in camera instead of the webcam? Try 1.
W, H = 480, 360        # Size the robot works at. Big enough to see faces ~2 m away,
                       # small enough to stay fast on the Raspberry Pi.


# ---- 1. Open the camera ------------------------------------------------------
cap = cv2.VideoCapture(CAMERA)

# Ask for 640x480 in MJPG (compressed). Many webcams send uncompressed video by
# default, which is too much data for USB - they get stuck at 5-10 frames/second.
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not cap.isOpened():                  # no camera at that number: stop with a clear message
    sys.exit("Camera not found - try CAMERA = 1")

# FPS counter: count frames, and once a second work out frames per second
fps = 0.0              # the number shown on screen
frames = 0             # frames counted since the last update
t0 = time.time()       # time of the last update (seconds)


# ---- 2. The loop: one pass = one frame ---------------------------------------
while True:
    ok, frame = cap.read()             # grab one frame (ok = False if it failed)
    if not ok:
        break                          # camera unplugged or stopped sending: leave the loop

    # Shrink to the robot's size. INTER_AREA is the best method for shrinking.
    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)

    # FPS: count this frame; once a full second has passed, work out the rate
    frames = frames + 1
    now = time.time()
    if now - t0 >= 1:
        fps = frames / (now - t0)      # frames divided by seconds
        frames = 0
        t0 = now
    # Draw it: text, position (x, y), font, size, color (Blue, Green, Red), thickness
    cv2.putText(frame, f"{fps:.1f} fps", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("Live feed", frame)     # show it in a window called "Live feed"

    # waitKey(1): wait 1 ms for a key (it also lets the window redraw - needed!).
    # "& 0xFF" keeps just the key's code, so it can be compared with ord('q').
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):                # q quits
        break


# ---- 3. Clean up ---------------------------------------------------------------
cap.release()                          # free the camera for the next program
cv2.destroyAllWindows()                # close the windows
