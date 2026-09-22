// =============================================================================
// motor_controller.ino - the wheels (roadmap step 7)
// Arduino Uno + LAFVIN TB6612FNG motor shield, 2 DC motors.
// =============================================================================
// The Pi does all the thinking. This sketch only listens on USB and turns each
// line into two wheel speeds:
//
//     "<fwd> <turn>\n"      both numbers -100..100
//       fwd  > 0 forward        < 0 reverse
//       turn > 0 turn right     < 0 turn left
//
//     "50 0"    drive straight, half speed
//     "0 -30"   turn left on the spot
//     "0 0"     stop
//
// Safety: if no command arrives for half a second (Pi crashed, USB unplugged,
// program stopped), the motors stop by themselves. See TIMEOUT_MS.
//
// ---- Testing it on the bench (wheels OFF the ground!) ------------------------
// 1. Upload from the Arduino IDE: Tools > Board = "Arduino Uno",
//    Tools > Port = the Uno's COM port. follow.py must NOT be running - only one
//    program at a time can hold the port.
// 2. Open Tools > Serial Monitor, set it to 115200 baud and "Newline".
// 3. Switch the shield's battery switch ON, then type commands:
//       t        run the wheel test: left forward, left back, right forward, right back
//       50 0     both wheels forward
//       0 50     turn right on the spot
//       0 0      stop
//    "t" is the one that matters: it tells you which wheel is which and whether
//    either one runs backwards. If a wheel spins the wrong way, flip that side's
//    FWD_L / FWD_R below (HIGH <-> LOW), upload again, and test again.
// =============================================================================

// ---- The shield's wiring. Fixed by the circuit board - do not change. --------
const int DIR_L = 2, PWM_L = 5;      // channel A = LEFT motor  (shield socket A1)
const int DIR_R = 4, PWM_R = 6;      // channel B = RIGHT motor (shield socket B1)

// ---- Settings you may need to change ----------------------------------------

// Which direction level drives each wheel FORWARD. The two motors face opposite
// ways on the chassis, so one side is HIGH and the other LOW. These values follow
// LAFVIN's own sample code; the "t" test tells you if yours are the other way round.
const bool FWD_L = HIGH, FWD_R = LOW;

// The slowest PWM that actually moves the robot. Below this the motors just buzz
// and get warm. Too low -> the robot stalls on carpet; too high -> it can't creep.
// Find it on the floor in step 10: send "20 0" and raise MIN_PWM until it crawls.
const int MIN_PWM = 90;              // 0-255

// The fastest PWM allowed. NOT 255 on purpose: the TB6612 passes almost the whole
// battery voltage through, so at 255 the motors would see ~7.4-8.4 V while these
// TT motors are rated 3-6 V. 200/255 keeps the average around 6 V.
const int MAX_PWM = 200;             // 0-255

// Failsafe. No command for this long -> stop. Must be longer than the time between
// commands from the Pi (it sends one per camera frame, ~20 per second = every 50 ms).
const unsigned long TIMEOUT_MS = 500;

// ---- Working memory ---------------------------------------------------------
char line[24];                       // the command being typed/received, one character at a time
byte len = 0;                        // how much of it we have so far
unsigned long lastCmd = 0;           // when the last good command arrived (millis)
bool stopped = true;                 // are the motors currently stopped?

// =============================================================================
// One wheel. v is -100..100. Any non-zero v gets at least MIN_PWM, so a small
// number still produces movement instead of a buzz.
// =============================================================================
void motor(int dirPin, int pwmPin, bool fwdLevel, int v) {
  digitalWrite(dirPin, v >= 0 ? fwdLevel : !fwdLevel);
  analogWrite(pwmPin, v == 0 ? 0 : map(abs(v), 1, 100, MIN_PWM, MAX_PWM));
}

// =============================================================================
// Both wheels, from one "fwd turn" command.
// Mixing: the left wheel does fwd+turn, the right wheel fwd-turn. So turning
// right speeds the left wheel up and slows the right one down.
// =============================================================================
void drive(int fwd, int turn) {
  fwd  = constrain(fwd, -100, 100);
  turn = constrain(turn, -100, 100);

  int l = fwd + turn;
  int r = fwd - turn;

  // "70 50" would ask for 120 on one wheel. Scale BOTH down by the same amount,
  // so the robot keeps driving the curve it was asked for, just slower.
  int m = max(abs(l), abs(r));
  if (m > 100) {
    l = l * 100 / m;
    r = r * 100 / m;
  }

  motor(DIR_L, PWM_L, FWD_L, l);
  motor(DIR_R, PWM_R, FWD_R, r);

  stopped = (l == 0 && r == 0);
  digitalWrite(LED_BUILTIN, !stopped);         // the Uno's own LED = "wheels are driving"
}

// =============================================================================
// The "t" bench test: one wheel at a time, so you can name them and catch a
// motor that is wired backwards. Wheels off the ground before running this.
// =============================================================================
void wheelTest() {
  const int SPEED = 60, HOLD = 1200;           // % speed, milliseconds per step
  struct { const char *what; int l; int r; } steps[] = {
    {"LEFT forward",   SPEED,  0},
    {"LEFT reverse",  -SPEED,  0},
    {"RIGHT forward",  0,  SPEED},
    {"RIGHT reverse",  0, -SPEED},
    {"BOTH forward",   SPEED,  SPEED},
    {"SPIN right",     SPEED, -SPEED},
  };

  for (auto &s : steps) {
    Serial.print("  ");
    Serial.println(s.what);
    motor(DIR_L, PWM_L, FWD_L, s.l);           // straight to the wheels, skipping the mixer
    motor(DIR_R, PWM_R, FWD_R, s.r);
    delay(HOLD);
    drive(0, 0);
    delay(400);
  }
  Serial.println("  done - any wheel going the wrong way? flip FWD_L / FWD_R in the sketch");
  lastCmd = millis();
}

// =============================================================================
void setup() {
  pinMode(DIR_L, OUTPUT); pinMode(PWM_L, OUTPUT);
  pinMode(DIR_R, OUTPUT); pinMode(PWM_R, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  drive(0, 0);                                 // never move on power-up
  Serial.begin(115200);                        // must match BAUD in pi/follow.py
  Serial.println("FollowBot motor controller ready. Send \"fwd turn\", or t to test the wheels.");
}

void loop() {
  // Collect characters until a whole line has arrived.
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {              // end of a line: act on it
      line[len] = '\0';
      int fwd, turn;

      if (len == 1 && (line[0] == 't' || line[0] == 'T')) {
        wheelTest();
      } else if (len > 0 && sscanf(line, "%d %d", &fwd, &turn) == 2) {
        drive(fwd, turn);
        lastCmd = millis();
      }
      len = 0;                                 // ready for the next line
                                               // (anything else is ignored on purpose:
                                               //  a half-received line must never move the robot)
    } else if (len < sizeof(line) - 1) {
      line[len++] = c;
    }
  }

  // Failsafe: nothing heard from the Pi for TIMEOUT_MS -> stop.
  if (!stopped && millis() - lastCmd > TIMEOUT_MS) drive(0, 0);
}
