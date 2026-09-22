#!/usr/bin/env bash
# =============================================================================
# install_service.sh - make the robot start by itself when the Pi boots.
# =============================================================================
# Run it on the Pi, from anywhere:
#
#     sudo bash ~/Face_Tracking_Bot/deploy/install_service.sh
#
# It works out your username and where the code lives, fills those into
# followbot.service, installs it, and starts it. Safe to run again after you
# move the code or change the options.
#
# Undo it all with:  sudo bash ~/Face_Tracking_Bot/deploy/install_service.sh --remove
# =============================================================================
set -euo pipefail

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
say()  { echo "${BOLD}$*${OFF}"; }
ok()   { echo "  ${GREEN}OK${OFF}  $*"; }
warn() { echo "  ${YELLOW}!${OFF}   $*"; }
die()  { echo "${RED}Stopped:${OFF} $*" >&2; exit 1; }

SERVICE=followbot
UNIT=/etc/systemd/system/$SERVICE.service
DEFAULTS=/etc/default/$SERVICE

# ---- 1. Checks --------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "run it with sudo:  sudo bash $0"
command -v systemctl >/dev/null || die "this Pi has no systemd - are you on Raspberry Pi OS?"

# Who is the robot going to run as? Not root: the normal user owns the code,
# the venv, and the dialout group that allows talking to the Uno.
USER_NAME="${SUDO_USER:-${1:-}}"
[ -n "$USER_NAME" ] && [ "$USER_NAME" != "root" ] \
  || die "could not tell which user to run as - call it as:  sudo bash $0 <username>"

REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
VENV="$HOME_DIR/robot-venv"

# ---- Remove mode ------------------------------------------------------------
if [ "${1:-}" = "--remove" ]; then
  say "Removing the service"
  systemctl disable --now $SERVICE 2>/dev/null || true
  rm -f "$UNIT"
  systemctl daemon-reload
  ok "gone. The code and $DEFAULTS are untouched."
  exit 0
fi

say "Installing the FollowBot service"
echo "  user:     $USER_NAME"
echo "  code:     $REPO"
echo "  python:   $VENV/bin/python"
echo

[ -x "$VENV/bin/python" ] || die "no Python environment at $VENV - run deploy/setup_pi.sh first"
[ -f "$REPO/pi/follow.py" ] || die "no $REPO/pi/follow.py - is this the project folder?"
[ -f "$REPO/deploy/followbot.service" ] || die "deploy/followbot.service is missing"

# ---- 2. The options file ----------------------------------------------------
# Only written the first time, so a later run never overwrites your choice.
if [ ! -f "$DEFAULTS" ]; then
  # No Uno plugged in? Start with --dry so the service doesn't crash-loop
  # looking for a serial port that isn't there.
  if ls /dev/ttyACM* /dev/ttyUSB* >/dev/null 2>&1; then
    ARGS=""
    FOUND="an Uno is plugged in, so it will drive the motors"
  else
    ARGS="--dry"
    FOUND="no Uno found, so --dry is set (vision + dashboard only)"
  fi
  cat > "$DEFAULTS" <<EOF
# Options passed to pi/follow.py by the followbot service.
#   --dry           don't talk to the Uno (no motors)
#   --camera 1      use a different camera
#   --mode face     start in face mode instead of color
#   --web-port 80   serve the dashboard on the normal web port
# After changing this:  sudo systemctl restart followbot
FOLLOWBOT_ARGS="$ARGS"
EOF
  ok "wrote $DEFAULTS - $FOUND"
else
  ok "kept your existing $DEFAULTS ($(grep -h '^FOLLOWBOT_ARGS' "$DEFAULTS"))"
fi

# ---- 3. The service file ----------------------------------------------------
sed -e "s|__USER__|$USER_NAME|g" \
    -e "s|__REPO__|$REPO|g" \
    -e "s|__VENV__|$VENV|g" \
    "$REPO/deploy/followbot.service" > "$UNIT"
ok "wrote $UNIT"

systemctl daemon-reload
systemctl enable $SERVICE >/dev/null
ok "it will now start on every boot"

# ---- 4. Start it and see if it survives -------------------------------------
systemctl restart $SERVICE
sleep 4                                   # give the camera time to open

if systemctl is-active --quiet $SERVICE; then
  ok "running"
  # Read the port out of the FOLLOWBOT_ARGS line only - not out of the comments
  # above it, which mention --web-port as an example.
  ARGS_LINE="$(grep -h '^FOLLOWBOT_ARGS' "$DEFAULTS" || true)"
  PORT="$(printf '%s' "$ARGS_LINE" | grep -o -- '--web-port[= ][0-9]*' | grep -o '[0-9]*$' || true)"
  PORT="${PORT:-8000}"
  IP="$(hostname -I | awk '{print $1}')"
  echo
  say "Open the dashboard:  http://$IP:$PORT   (or http://$(hostname).local:$PORT)"
else
  warn "it did not stay running. The reason is in the log below:"
  journalctl -u $SERVICE -n 20 --no-pager || true
fi

cat <<EOF

${BOLD}Day-to-day commands${OFF}
  sudo systemctl stop followbot       free the camera and the Uno before running it by hand
  sudo systemctl start followbot      hand it back
  sudo systemctl restart followbot    after a git pull, or after changing $DEFAULTS
  systemctl status followbot          is it alive?
  journalctl -u followbot -f          watch it live: fps, mode, state, command
  sudo systemctl disable followbot    stop starting it on boot (leaves it running now)

${YELLOW}Remember:${OFF} while the service is running it holds the webcam and port 8000,
so running pi/follow.py by hand will fail until you stop it.
EOF
