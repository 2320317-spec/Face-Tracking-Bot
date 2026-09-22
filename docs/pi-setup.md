# Raspberry Pi setup — step by step

From a blank microSD card to a Pi that runs the FollowBot code, controlled from your laptop over WiFi. No monitor or keyboard needed for the Pi.

**Time:** about 45 minutes, most of it waiting for downloads.

---

## What you need

| Item | Notes |
|---|---|
| Raspberry Pi 4 Model B | |
| microSD card, 16 GB or more | 32 GB "A1" or "A2" rated is faster. **Everything on it will be erased.** |
| SD card reader for the laptop | Built-in slot or a USB reader |
| Power: 5 V **3 A** USB-C | The official Pi power supply, or a 5 V 3 A power bank + USB-C cable. Weak phone chargers make the Pi slow down or reboot. |
| Your WiFi name and password | The laptop and the Pi must be on the same WiFi |
| The USB webcam | For the check at the end |

---

## Step 1 — Put the latest code on GitHub (laptop)

The Pi downloads the code from GitHub, so push everything first:

```bash
git add .
git commit -m "Pi setup script and system check"
git push
```

## Step 2 — Install Raspberry Pi Imager (laptop)

Download it from the official site, **raspberrypi.com/software**, and install it.

## Step 3 — Write Raspberry Pi OS to the SD card (laptop)

Put the SD card in the laptop, open Raspberry Pi Imager, and choose:

1. **Device:** Raspberry Pi 4
2. **Operating system:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**
   (Lite = no desktop. The robot doesn't need one, and it leaves more power for the camera work.)
3. **Storage:** your SD card — double-check it's the SD card, not another drive
4. **Customisation** (Imager asks before writing — say yes / edit settings):
   - **Hostname:** `followbot`
   - **Username and password:** pick your own and remember them
   - **WiFi:** your WiFi name (SSID) and password, **country: PH**
   - **Time zone:** Asia/Manila
   - **SSH / remote access:** **enabled**, with password authentication
5. **Write**, wait until it's done and verified, then take the card out.

## Step 4 — First boot (Pi)

1. Put the SD card in the Pi (slot underneath).
2. Plug in the webcam.
3. Plug in the power. The red LED stays on; the green one flickers while it works.
4. **Wait about 2 minutes** — the first start takes longer.

## Step 5 — Connect from the laptop

In the VS Code terminal (replace `<user>` with the username you picked):

```bash
ssh <user>@followbot.local
```

- The first time it asks *"Are you sure you want to continue connecting?"* → type `yes`.
- Then your Pi password. (Nothing appears while you type — that's normal.)
- You're in when the prompt looks like `<user>@followbot:~ $`. Everything you type now runs **on the Pi**.

`followbot.local` not found? Wait another minute and retry. Still nothing: look up the Pi's IP address in your WiFi router's list of connected devices and use `ssh <user>@192.168.x.x` instead.

## Step 6 — Get the code onto the Pi

Your GitHub repository is **private**, so the Pi has to prove it's allowed to read it. Pick one:

**Option A — make the repository public** (simplest). GitHub → your repository → *Settings* → *Danger Zone* → *Change visibility* → Public. Nothing secret is in it (the face models and your face data are never uploaded).

**Option B — keep it private and use a token.** On GitHub: your profile picture → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained tokens* → *Generate new token*. Give it access to **only this repository**, with **Contents: Read-only**. Copy the token. When `git clone` asks for a password below, paste the token (not your GitHub password).

Then, on the Pi — first make sure Git is installed (Lite may not have it), then download the code:

```bash
sudo apt install -y git
```

```bash
git clone https://github.com/2320317-spec/Face-Tracking-Bot.git ~/Face_Tracking_Bot
```

(The folder is named `Face_Tracking_Bot` on purpose — the rest of the plan uses that name.)

## Step 7 — Install everything (Pi)

One script does it all — system update, Python packages, face models, serial port access. The first run takes 10–20 minutes:

```bash
cd ~/Face_Tracking_Bot && bash deploy/setup_pi.sh
```

When it says **Done!**, log out and back in (needed once, for the serial port):

```bash
exit
```

…then `ssh <user>@followbot.local` again.

## Step 8 — Check everything (Pi)

```bash
cd ~/Face_Tracking_Bot && ~/robot-venv/bin/python tools/pi_check.py
```

It checks the versions, the face models, the webcam, and the Pi's temperature and power, and it **measures how fast the Pi really is** for color and face detection. It should end with **All good!** Copy the whole output and send it to Claude — those speed numbers replace the estimates in the plan.

Webcam not found? Try `--camera 1`, and list the cameras with `v4l2-ctl --list-devices`.

---

## Everyday use

| To... | Run (on the Pi) |
|---|---|
| Connect from the laptop | `ssh <user>@followbot.local` |
| Get your latest code | `cd ~/Face_Tracking_Bot && git pull` |
| Check the Pi | `~/robot-venv/bin/python tools/pi_check.py` |
| **Switch it off safely** | `sudo shutdown now` — then wait until the green LED stops blinking before unplugging |

**Always shut down before pulling the power.** Pulling the plug while it's writing can corrupt the SD card, and then you're back to step 3.

## Troubleshooting

| Problem | Fix |
|---|---|
| `followbot.local` not found | Wait 2–3 min after power-on. Laptop on the same WiFi? Use the IP address from your router instead. |
| `Permission denied` when logging in | Wrong username or password — they're the ones you set in Imager. |
| `git clone` asks for a password and fails | Private repo: use a token (step 6, option B), not your GitHub password. |
| setup_pi.sh stops with an error | Run it again — it skips what's already done. If it stops at the same place, send the error to Claude. |
| Red `ERROR: pip's dependency resolver...` about `types-flask-migrate` / `types-seaborn` | Harmless — system packages FollowBot doesn't use. If the script ends with **Done!** and you see `Successfully installed ... opencv-python-headless`, it worked. |
| pi_check: "under-voltage" | Power supply too weak — use a 5 V 3 A supply. |
| pi_check: temperature above 70 C | Add the heatsink / fan. |
| pi_check: face mode below 10 fps | Usually heat or power — see the two rows above. |
