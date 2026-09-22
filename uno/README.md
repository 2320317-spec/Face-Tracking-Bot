# uno/ — Arduino Uno motor controller

The Uno sits under the LAFVIN TB6612 shield and drives the two wheels. It gets one line per camera frame from the Pi over USB serial (115200 baud):

```
<fwd> <turn>      each -100..100     e.g.  "50 0" forward · "0 -30" spin left · "0 0" stop
```

It stops the motors on its own if no line arrives for 0.5 s.

| Path | What it is |
|---|---|
| `motor_controller/motor_controller.ino` | The sketch. The Arduino IDE requires the folder and the `.ino` file to have the same name. |

Delete `motor_controller/.gitkeep` once the sketch is in that folder.

## Upload

1. Arduino IDE → open `motor_controller/motor_controller.ino`.
2. Board: **Arduino Uno**, and pick its port.
3. Before uploading: nothing plugged into the shield's Bluetooth socket (P2), and `follow.py` not running — only one program can use the port at a time.

Pin map, bench test and calibration: build plan sections 4.1, 5.10 and 7.1–7.2.
