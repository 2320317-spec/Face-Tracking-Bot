# uno/ — Arduino Uno motor controller

The Uno sits under the LAFVIN TB6612 shield and drives the two wheels. It gets one line per camera frame from the Pi over USB serial (115200 baud):

```
<fwd> <turn>      each -100..100     e.g.  "50 0" forward · "0 -30" spin left · "0 0" stop
```

It stops the motors on its own if no line arrives for 0.5 s.

| Path | What it is |
|---|---|
| `motor_controller/motor_controller.ino` | The sketch. The Arduino IDE requires the folder and the `.ino` file to have the same name. |

## Upload

1. Arduino IDE → open `motor_controller/motor_controller.ino`.
2. Board: **Arduino Uno**, and pick its port.
3. Before uploading: nothing plugged into the shield's Bluetooth socket (P2), and `follow.py` not running — only one program can use the port at a time.

## Bench test — wheels OFF the ground

Open the Serial Monitor at **115200 baud**, set the line ending to **Newline**, switch the shield's battery switch on, and type:

| You type | What should happen |
|---|---|
| `t` | The wheel test: left forward, left back, right forward, right back, both forward, spin right — each for about a second, announced in the monitor |
| `50 0` | Both wheels forward |
| `0 50` | Spins right on the spot (left wheel forward, right wheel back) |
| `0 0` | Stop |

**If a wheel turns the wrong way**, flip that side's `FWD_L` or `FWD_R` in the sketch (`HIGH` ↔ `LOW`), upload again, and run `t` again. Do this before anything else: one reversed motor turns "curve left" into "spin right", and it is nearly impossible to diagnose once the Pi is driving.

The Uno's own LED is lit whenever the wheels are being driven — handy when the motors are quiet or unplugged.

Stop typing for half a second and the motors stop by themselves. That is the failsafe that protects you if the Pi crashes.

Settings you may need to change (all at the top of the sketch): `FWD_L` / `FWD_R` directions, `MIN_PWM` (the slowest speed that actually moves the robot), `MAX_PWM` (capped at 200 to keep the motors near 6 V).

Pin map, wiring and calibration: build plan sections 4.1, 5.10 and 7.1–7.2.
