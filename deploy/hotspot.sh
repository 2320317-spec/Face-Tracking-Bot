#!/usr/bin/env bash
# =============================================================================
# hotspot.sh - turn the Pi into its own WiFi access point for the demo.
# =============================================================================
# School WiFi usually blocks one device from reaching another, and often needs
# a login page. So at the demo the robot makes its OWN WiFi and your phone joins
# that instead. No school network, no laptop, no internet needed.
#
#   sudo bash deploy/hotspot.sh on         switch to the robot's own WiFi now
#   sudo bash deploy/hotspot.sh off        go back to your home WiFi
#   sudo bash deploy/hotspot.sh boot-on    make the Pi boot straight into hotspot mode
#   sudo bash deploy/hotspot.sh boot-off   boot into home WiFi again (the normal setting)
#   sudo bash deploy/hotspot.sh status     what is it on right now?
#   sudo bash deploy/hotspot.sh remove     delete the hotspot completely
#
# Then, on your phone: join the WiFi named below and open   http://10.42.0.1:8000
#
# ---- IMPORTANT --------------------------------------------------------------
# Anyone who joins this WiFi can drive your robot. Change the password below
# before the demo, and don't tell the whole room.
#
# Turning the hotspot ON drops any SSH session you have over your home WiFi -
# that is normal and expected, not a crash. To get back in afterwards, either
# join the "FollowBot" network and  ssh <user>@10.42.0.1, or plug in a network
# cable, or just run  boot-off  before you reboot.
# =============================================================================
set -euo pipefail

# ---- Settings ---------------------------------------------------------------
SSID="${HOTSPOT_SSID:-FollowBot}"            # the WiFi name your phone will see
PASSWORD="${HOTSPOT_PASS:-followbot2026}"    # CHANGE THIS. At least 8 characters.
PROFILE="followbot-ap"                       # the name NetworkManager stores it under
AP_IP="10.42.0.1"                            # fixed by NetworkManager's "shared" mode
PORT=8000                                    # the dashboard's port

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
say()  { echo "${BOLD}$*${OFF}"; }
ok()   { echo "  ${GREEN}OK${OFF}  $*"; }
warn() { echo "  ${YELLOW}!${OFF}   $*"; }
die()  { echo "${RED}Stopped:${OFF} $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run it with sudo:  sudo bash $0 ${1:-status}"
command -v nmcli >/dev/null || die "NetworkManager (nmcli) not found - this needs Raspberry Pi OS Bookworm or newer"

# ---- Helpers ----------------------------------------------------------------

# Create the access-point profile, once. Nothing is switched on here.
make_profile() {
  if nmcli -t -f NAME connection show | grep -qx "$PROFILE"; then
    return
  fi
  [ ${#PASSWORD} -ge 8 ] || die "the WiFi password must be at least 8 characters"
  say "Creating the hotspot profile \"$PROFILE\" (WiFi name: $SSID)"
  nmcli connection add type wifi ifname wlan0 con-name "$PROFILE" ssid "$SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.pairwise ccmp \
    wifi-sec.group ccmp \
    wifi-sec.psk "$PASSWORD" \
    connection.autoconnect no >/dev/null
  ok "created"
}

# The name of your normal (home / phone) WiFi profile - anything that isn't the hotspot.
home_wifi() {
  nmcli -t -f NAME,TYPE connection show \
    | awk -F: -v ap="$PROFILE" '$2 == "802-11-wireless" && $1 != ap {print $1; exit}'
}

# ---- The commands -----------------------------------------------------------
case "${1:-status}" in

  on)
    make_profile
    # Is the country set? Without it the Pi's WiFi chip refuses to be an access
    # point, because the legal channels depend on the country.
    if iw reg get 2>/dev/null | grep -q "country 00"; then
      warn "WiFi country is not set - the hotspot may fail to start."
      warn "Fix it with:  sudo raspi-config  ->  Localisation Options  ->  WLAN Country"
    fi
    say "Switching to the robot's own WiFi..."
    warn "your SSH session over the home WiFi will freeze here - that is expected"
    sleep 1
    # Run the switch detached, so it finishes even though it cuts off the very
    # SSH connection that started it (otherwise you can end up half-switched).
    if command -v systemd-run >/dev/null; then
      systemd-run --collect --unit followbot-hotspot-on --quiet \
        nmcli connection up "$PROFILE"
      sleep 6
    else
      nmcli connection up "$PROFILE" || true
    fi
    exec "$0" status
    ;;

  off)
    HOME_WIFI="$(home_wifi || true)"
    say "Turning the hotspot off"
    nmcli connection down "$PROFILE" 2>/dev/null || true
    nmcli connection modify "$PROFILE" connection.autoconnect no
    if [ -n "$HOME_WIFI" ]; then
      if command -v systemd-run >/dev/null; then
        systemd-run --collect --unit followbot-hotspot-off --quiet \
          nmcli connection up "$HOME_WIFI"
        sleep 8
      else
        nmcli connection up "$HOME_WIFI" || true
      fi
      ok "back on \"$HOME_WIFI\""
    else
      warn "no other WiFi is saved on this Pi - add one with:"
      warn "  sudo nmcli device wifi connect \"<network name>\" password \"<password>\""
    fi
    exec "$0" status
    ;;

  boot-on)
    make_profile
    nmcli connection modify "$PROFILE" connection.autoconnect yes connection.autoconnect-priority 100
    ok "from the next reboot the Pi starts its own WiFi \"$SSID\" by itself"
    echo "     Demo day: power the Pi from the power bank, wait ~40 s, join $SSID on your phone,"
    echo "     open http://$AP_IP:$PORT - no laptop needed."
    warn "remember to run  boot-off  afterwards, or the Pi will stop joining your home WiFi"
    ;;

  boot-off)
    nmcli connection modify "$PROFILE" connection.autoconnect no 2>/dev/null \
      || die "no hotspot profile yet - nothing to turn off"
    ok "on the next boot the Pi joins your home WiFi again"
    ;;

  remove)
    nmcli connection down "$PROFILE" 2>/dev/null || true
    nmcli connection delete "$PROFILE" 2>/dev/null || warn "there was no hotspot profile"
    ok "removed"
    ;;

  status)
    ACTIVE="$(nmcli -t -f NAME,DEVICE connection show --active | awk -F: '$2 == "wlan0" {print $1}')"
    AUTO="$(nmcli -g connection.autoconnect connection show "$PROFILE" 2>/dev/null || echo "not set up")"
    IP="$(hostname -I | awk '{print $1}')"
    echo
    say "WiFi right now"
    if [ "$ACTIVE" = "$PROFILE" ]; then
      ok "the robot's own hotspot \"$SSID\" is ON"
      echo "     phone: join $SSID  ->  http://$AP_IP:$PORT"
      echo "     ssh:   ssh $(logname 2>/dev/null || echo "<user>")@$AP_IP"
    elif [ -n "$ACTIVE" ]; then
      ok "joined \"$ACTIVE\" (a normal WiFi network)"
      echo "     dashboard: http://${IP:-?}:$PORT   or   http://$(hostname).local:$PORT"
    else
      warn "wlan0 is not connected to anything"
    fi
    echo "     starts the hotspot on boot: $AUTO"
    echo
    ;;

  *)
    die "unknown command \"$1\". Use: on | off | boot-on | boot-off | status | remove"
    ;;
esac
