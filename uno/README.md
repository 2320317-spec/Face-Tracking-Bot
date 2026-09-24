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
| `c` | **Find the slowest PWM that actually moves it.** Creeps the power up in steps of 5, announcing each one. Runs twice: driving (gives `MIN_PWM`) then pivoting (gives `MIN_PWM_TURN`). **Wheels ON the floor** for this one — friction is what you're measuring. |
| `t` | The wheel test: left forward, left back, right forward, right back, both forward, spin right — each for about a second, announced in the monitor |
| `50 0` | Both wheels forward |
| `0 50` | Spins right on the spot (left wheel forward, right wheel back) |
| `0 0` | Stop |

**If a wheel turns the wrong way**, flip that side's `FWD_L` or `FWD_R` in the sketch (`HIGH` ↔ `LOW`), upload again, and run `t` again. Do this before anything else: one reversed motor turns "curve left" into "spin right", and it is nearly impossible to diagnose once the Pi is driving.

The Uno's own LED is lit whenever the wheels are being driven — handy when the motors are quiet or unplugged.

Stop typing for half a second and the motors stop by themselves. That is the failsafe that protects you if the Pi crashes.

Settings you may need to change (all at the top of the sketch): `FWD_L` / `FWD_R` directions, `MIN_PWM` (the slowest speed that actually moves the robot), `MAX_PWM` (capped at 200 to keep the motors near 6 V).

## Battery monitor (optional — two resistors)

The robot cannot tell you it is running flat, and a flat pack looks exactly like bad tuning: everything gets slow and weak before it stops. Two resistors fix that.

**Why resistors at all.** The Uno's analog pins read 0–5 V. A charged 2-cell pack is 8.4 V, which would damage one. Two **equal** resistors in a line from + to GND put exactly half the voltage at the point between them — and half of 8.4 is 4.2, safely inside range.

```
   battery +  ---[ R1 10k ]---+---[ R2 10k ]---  GND
                              |
                              +------------->  A0
```

Any equal pair from 4.7k to 47k works; 10k draws 0.4 mA, nothing next to the amps the motors pull. Battery GND and Uno GND must be the same ground — on this build the shield already joins them.

> **Never run the battery straight into A0.** The resistors are the whole protection.

Then in the sketch set `BATTERY = true` and upload. The reading appears on the dashboard by itself.

**Checking it.** Put a multimeter across the pack and compare. If the Uno is off by a little, set `BATT_TRIM` to `multimeter volts ÷ reported volts` and upload again. Most of any error comes from the resistors not being exactly equal, and this cancels it out.

**What the numbers mean**, for 2 × 18650 in series:

| Reading | Meaning |
|---|---|
| 8.4 V | fully charged |
| 7.6 V and up | good |
| 7.0–7.6 V | fine, most of the discharge sits here |
| 6.6–7.0 V | low — expect it to feel sluggish |
| below 6.6 V | charge it; below 6.0 V damages lithium cells |

**It is only measured while the wheels are stopped.** A pack sags under load — one resting at 7.4 V can read 6.8 V with both motors pulling — and the sagging number says more about how hard the motors are working than about how much charge is left. The Uno waits 0.4 s after stopping, averages 8 readings, and sends `B 7.82` every two seconds.

**Calibrate on a charged pack.** Running `c` on a flat battery measures a `MIN_PWM` that is far too high, and the robot will then lurch once it is charged.

Pin map, wiring and calibration: build plan sections 4.1, 5.10 and 7.1–7.2.
