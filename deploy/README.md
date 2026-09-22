# deploy/ — Raspberry Pi setup for the demo

Files that make the Pi run the robot on its own, without a laptop.

| File | What it does |
|---|---|
| `setup_pi.sh` | **Installs everything on a fresh Pi** in one go: system update, packages, Python environment, face models, serial port access. Safe to run again. Walkthrough: [docs/pi-setup.md](../docs/pi-setup.md) |
| `install_service.sh` | **Makes the robot start on boot.** Works out your username and paths, fills them into `followbot.service`, installs and starts it. |
| `followbot.service` | The systemd unit itself, with `__MARKERS__` the installer fills in. Don't copy it by hand. |
| `hotspot.sh` | **The robot's own WiFi** for the demo: `on` / `off` / `boot-on` / `boot-off` / `status` / `remove`. |

Everything below runs **on the Pi**, from `~/Face_Tracking_Bot`.

## Start on boot

```bash
sudo bash deploy/install_service.sh
```

It picks `--dry` by itself if no Uno is plugged in, so it can't crash-loop looking for a serial port that isn't there. Change that later in `/etc/default/followbot`:

```bash
sudo nano /etc/default/followbot     # FOLLOWBOT_ARGS="" once the Uno is connected
sudo systemctl restart followbot
```

| Command | When you need it |
|---|---|
| `sudo systemctl stop followbot` | **Before running `pi/follow.py` by hand** — the service holds the webcam and port 8000 |
| `sudo systemctl restart followbot` | After a `git pull`, or after editing the options |
| `systemctl status followbot` | Is it alive? |
| `journalctl -u followbot -f` | Watch it live: fps, mode, state, command |
| `sudo bash deploy/install_service.sh --remove` | Undo the whole thing |

The robot still boots **STOPPED** — starting on boot only means the camera, the brain and the dashboard are running. Nothing moves until you press **Engage**.

## The robot's own WiFi

School WiFi usually blocks one device from reaching another, and often wants a login page. So the robot makes its own network instead — no school WiFi, no laptop, no internet.

```bash
sudo bash deploy/hotspot.sh status     # what is it on right now?
sudo bash deploy/hotspot.sh boot-on    # demo day: boot straight into the hotspot
sudo bash deploy/hotspot.sh boot-off   # afterwards: go back to joining your home WiFi
```

Phone: join **FollowBot**, open **http://10.42.0.1:8000**.

- **Change the password** at the top of `hotspot.sh` before the demo — anyone on that WiFi can drive the robot.
- `hotspot.sh on` switches over immediately, which **drops any SSH session you have over the home WiFi**. That's expected. To get back in: join `FollowBot` and `ssh <user>@10.42.0.1`, or plug in a network cable.
- `boot-on` / `boot-off` are the safer pair: they change what happens at the *next* boot and don't cut your connection now.
- The WiFi country must be set (Localisation Options in `raspi-config`), or the Pi refuses to be an access point.
