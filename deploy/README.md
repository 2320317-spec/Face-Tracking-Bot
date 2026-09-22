# deploy/ — Raspberry Pi setup for the demo

Files that make the Pi run the robot on its own, without a laptop. You'll add these near the end (build plan, section 7, step 12).

| File | What it does | Plan |
|---|---|---|
| `setup_pi.sh` | **Installs everything on a fresh Pi** in one go: system update, packages, Python environment, face models, serial port access. Safe to run again. Full walkthrough: [docs/pi-setup.md](../docs/pi-setup.md) | 5.2 |
| `followbot.service` | *(later)* systemd unit: starts `pi/follow.py` at boot and restarts it if it crashes | 5.12 |

Install the service on the Pi, from the project root (edit `<user>` in the file first):

```bash
sudo cp deploy/followbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now followbot
```

The WiFi hotspot ("FollowBot") needs no file — it's a one-time `nmcli` command, in plan section 5.13.
