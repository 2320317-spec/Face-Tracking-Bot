#!/usr/bin/env bash
# =============================================================================
# setup_pi.sh - installs everything FollowBot needs on a fresh Raspberry Pi
# =============================================================================
# Run it ON THE PI, from the project folder:
#     cd ~/Face_Tracking_Bot
#     bash deploy/setup_pi.sh
# Safe to run again - it skips what's already done.
#
# What it does:
#   1. updates the system                        (apt update + full-upgrade)
#   2. installs system packages                  (git, Python venv, camera tools, GPIO)
#   3. creates the Python environment            (~/robot-venv)
#   4. installs the Python packages              (requirements-pi.txt: OpenCV 4.x, Flask, pyserial)
#   5. downloads the two face models             (into pi/models/)
#   6. gives your user access to the serial port (for the Arduino Uno)
# =============================================================================
set -e                                  # stop at the first error

cd "$(dirname "$0")/.."                 # go to the project folder (this script lives in deploy/)
VENV="$HOME/robot-venv"                 # where the Python environment goes
ZOO="https://github.com/opencv/opencv_zoo/raw/main/models"     # OpenCV's model collection

echo "== 1/6  Updating the system (the first time can take 10-20 minutes) =="
sudo apt update
sudo apt full-upgrade -y

echo "== 2/6  System packages =="
sudo apt install -y git python3-venv v4l-utils
# GPIO is only needed for the optional backup Start/Stop button - don't stop if it's missing
sudo apt install -y python3-gpiozero python3-lgpio \
    || echo "   (GPIO packages not found - only needed for the optional backup button)"

echo "== 3/6  Python environment: $VENV =="
if [ ! -d "$VENV" ]; then
    # --system-site-packages: the venv can also see apt's Python packages (gpiozero)
    python3 -m venv --system-site-packages "$VENV"
fi

echo "== 4/6  Python packages (OpenCV is a ~40 MB download) =="
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements-pi.txt

echo "== 5/6  Face models =="
mkdir -p pi/models
for model in face_detection_yunet/face_detection_yunet_2023mar.onnx \
             face_recognition_sface/face_recognition_sface_2021dec.onnx; do
    name=$(basename "$model")
    if [ -s "pi/models/$name" ]; then
        echo "   $name - already there"
    else
        # download to a .part file first, so a broken download never looks finished
        wget -q --show-progress -O "pi/models/$name.part" "$ZOO/$model"
        mv "pi/models/$name.part" "pi/models/$name"
    fi
done

echo "== 6/6  Serial port access (for the Uno) =="
sudo usermod -aG dialout "$USER"

echo
echo "Done! Log out and back in once (so the serial port access takes effect), then check everything with:"
echo "    cd ~/Face_Tracking_Bot && $VENV/bin/python tools/pi_check.py"
