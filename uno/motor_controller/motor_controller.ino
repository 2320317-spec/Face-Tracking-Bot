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

// The little LED soldered onto the Uno itself, next to the USB socket. We light it
// whenever the wheels are being driven, which is a handy check when the motors are
// unplugged or quiet. Written as 13 rather than LED_BUILTIN because some board
// settings in the Arduino IDE don't define that name, and then nothing compiles.
const int LED = 13;

// ---- Settings you may need to change ----------------------------------------

// Which direction level drives each wheel FORWARD. The two motors face opposite
// ways on the chassis, so one side is HIGH and the other LOW. These values follow
// LAFVIN's own sample code; the "t" test tells you if yours are the other way round.
const bool FWD_L = HIGH, FWD_R = LOW;

// The slowest PWM that actually moves the robot. Below this the motors just buzz
// and get warm. Too low -> the robot stalls on carpet; too high -> it can't creep.
// Find it on the floor: send "20 0" and raise MIN_PWM until it just crawls.
// This is also why a small number from the Pi still moves the robot: "fwd 25" does
// not mean a quarter power, it means MIN_PWM plus a quarter of the way to MAX_PWM.
const int MIN_PWM = 70;              // 0-255

// The fastest PWM allowed. NOT 255 on purpose: the TB6612 passes almost the whole
// battery voltage through, so at 255 the motors would see ~7.4-8.4 V while these
// TT motors are rated 3-6 V. Lowered from 200 to 140 to stop the robot lurching:
// 140/255 of 7.4 V is about 4 V, which is a walking pace rather than a jump.
//   Too weak to move on carpet -> raise both numbers
//   Still too sudden           -> lower MAX_PWM, or slow the ramp below
const int MAX_PWM = 140;             // 0-255

// ---- A SEPARATE, GENTLER RANGE FOR TURNING ON THE SPOT -----------------------
// Driving and pivoting are different jobs and they do not want the same power.
// Sharing one range is why the robot snapped round whenever it needed to turn:
// the floor that lets it drive was also the slowest it could ever turn.
//
// These only apply when the robot is turning in place (no forward command). When
// it is driving AND turning, the two wheels just run at slightly different speeds
// and the curve is gentle anyway.
//
// Find the real numbers with the "c" command - it sweeps the PWM up and tells you
// the value at each step, so you can see exactly where the wheels start to move.
//   Won't pivot at all   -> raise MIN_PWM_TURN
//   Still snaps round    -> lower MAX_PWM_TURN
const int MIN_PWM_TURN = 65;         // slowest that still pivots the robot
const int MAX_PWM_TURN = 95;         // fastest it may ever pivot - well under MAX_PWM

// ---- Ramping: how fast the wheels are allowed to CHANGE speed ----------------
// Without this, a new command hits the motors instantly and the robot jumps -
// it "bursts out" on every move. The ramp spreads the change over a moment, so
// the robot leans into it instead. Measured in command units (-100..100) per second.
//
// Speeding up and slowing down are deliberately NOT the same:
//
//   RAMP_UP    gentle. This is the one that stops the lurch - a standing start to
//              full speed takes about half a second.
//   RAMP_DOWN  quick. Braking never feels like a lurch, and there are two good
//              reasons to be fast about it: the robot should stop promptly when
//              told, and the Pi turns in short bursts with pauses for the camera
//              to get a sharp picture. A slow wind-down would eat those pauses.
//
//   Still jumpy when starting -> lower RAMP_UP (120, 90)
//   Sluggish, or the little turn bursts don't register -> raise RAMP_UP (250)
const float RAMP_UP = 180.0;
const float RAMP_DOWN = 700.0;

// Failsafe. No command for this long -> stop. Must be longer than the time between
// commands from the Pi (it sends one per camera frame, ~20 per second = every 50 ms).
const unsigned long TIMEOUT_MS = 500;

// ---- Working memory ---------------------------------------------------------
char line[24];                       // the command being typed/received, one character at a time
byte len = 0;                        // how much of it we have so far
unsigned long lastCmd = 0;           // when the last good command arrived (millis)
bool stopped = true;                 // are the motors currently stopped?

bool pivoting = false;               // turning on the spot? (then the gentler range is used)
int targetL = 0, targetR = 0;        // the speed each wheel is being asked for (-100..100)
float curL = 0, curR = 0;            // the speed each wheel is actually at, right now
unsigned long lastRamp = 0;          // when the ramp last moved them

// =============================================================================
// One wheel. v is -100..100. Any non-zero v gets at least MIN_PWM, so a small
// number still produces movement instead of a buzz.
// =============================================================================
void motor(int dirPin, int pwmPin, bool fwdLevel, int v, int lo, int hi) {
  digitalWrite(dirPin, v >= 0 ? fwdLevel : !fwdLevel);
  analogWrite(pwmPin, v == 0 ? 0 : map(abs(v), 1, 100, lo, hi));
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

  // Turning on the spot gets its own, gentler power range.
  pivoting = (fwd == 0 && turn != 0);

  // Only ASK for these speeds. ramp() below walks the wheels toward them.
  targetL = l;
  targetR = r;
}


// One wheel's speed, moved a little closer to what was asked for. Speeding up is
// limited to RAMP_UP, slowing down to the much quicker RAMP_DOWN.
float eased(float now_v, int want, float dt) {
  bool slowing = abs(want) < abs(now_v) || (want < 0) != (now_v < 0);
  float step = (slowing ? RAMP_DOWN : RAMP_UP) * dt;
  return now_v + constrain(want - now_v, -step, step);
}


// =============================================================================
// Called constantly. Moves each wheel a little closer to the speed it was asked
// for, never faster than the ramps allow - that is what stops the robot lurching.
// =============================================================================
void ramp() {
  unsigned long now = millis();
  float dt = (now - lastRamp) / 1000.0;
  lastRamp = now;
  if (dt <= 0 || dt > 0.5) dt = 0.02;          // first time through, or a long gap

  curL = eased(curL, targetL, dt);
  curR = eased(curR, targetR, dt);

  int lo = pivoting ? MIN_PWM_TURN : MIN_PWM;
  int hi = pivoting ? MAX_PWM_TURN : MAX_PWM;
  motor(DIR_L, PWM_L, FWD_L, (int)curL, lo, hi);
  motor(DIR_R, PWM_R, FWD_R, (int)curR, lo, hi);

  stopped = ((int)curL == 0 && (int)curR == 0);
  digitalWrite(LED, !stopped);                 // the Uno's own LED = "wheels are driving"
}


// Stop NOW, no ramp. Used by the failsafe - if the Pi has gone quiet, the robot
// should not keep coasting while a ramp politely winds it down.
void stopNow() {
  targetL = targetR = 0;
  curL = curR = 0;
  pivoting = false;
  motor(DIR_L, PWM_L, FWD_L, 0, MIN_PWM, MAX_PWM);
  motor(DIR_R, PWM_R, FWD_R, 0, MIN_PWM, MAX_PWM);
  stopped = true;
  digitalWrite(LED, LOW);
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
    Serial.print(F("  "));
    Serial.println(s.what);
    motor(DIR_L, PWM_L, FWD_L, s.l, MIN_PWM, MAX_PWM);   // straight to the wheels, no mixer
    motor(DIR_R, PWM_R, FWD_R, s.r, MIN_PWM, MAX_PWM);
    delay(HOLD);
    drive(0, 0);
    delay(400);
  }
  Serial.println(F("  done - any wheel going the wrong way? flip FWD_L / FWD_R in the sketch"));
  stopNow();                                   // the test drove the motors directly
  lastCmd = millis();
}

// =============================================================================
// The "c" command: creep the PWM upward and say what it is at each step, so you
// can SEE the number where the wheels first move instead of guessing it.
//
// Run it twice over: the first half drives both wheels forward (that gives
// MIN_PWM), the second half pivots on the spot (that gives MIN_PWM_TURN).
// Wheels ON THE FLOOR for this - friction is the whole point of the measurement.
// =============================================================================
void calibrate() {
  for (byte part = 0; part < 2; part++) {
    Serial.println();
    Serial.println(part == 0 ? F("  DRIVING - watch for the first PWM that rolls it forward")
                             : F("  PIVOTING - watch for the first PWM that turns it on the spot"));
    for (int pwm = 40; pwm <= 150; pwm += 5) {
      Serial.print(F("    pwm "));
      Serial.println(pwm);
      digitalWrite(DIR_L, FWD_L);
      digitalWrite(DIR_R, part == 0 ? FWD_R : !FWD_R);    // same way, then opposite
      analogWrite(PWM_L, pwm);
      analogWrite(PWM_R, pwm);
      delay(900);
      analogWrite(PWM_L, 0);
      analogWrite(PWM_R, 0);
      delay(500);                                          // a gap, so each step is separate
    }
  }
  Serial.println(F("  done - put the two numbers into MIN_PWM and MIN_PWM_TURN"));
  stopNow();
  lastCmd = millis();
}


// =============================================================================
void setup() {
  pinMode(DIR_L, OUTPUT); pinMode(PWM_L, OUTPUT);
  pinMode(DIR_R, OUTPUT); pinMode(PWM_R, OUTPUT);
  pinMode(LED, OUTPUT);
  drive(0, 0);                                 // never move on power-up
  Serial.begin(115200);                        // must match BAUD in pi/follow.py
  // The version line is here so you can always tell WHICH sketch is on the board.
  // Bump it whenever you change the motor settings.
  Serial.println(F("FollowBot motor controller  v3 - soft ramp, separate turning power"));
  Serial.println(F("Type TWO NUMBERS, for example:"));
  Serial.println(F("  50 0  forward     0 50  spin right     0 -50  spin left"));
  Serial.println(F("  -40 0 backwards   50 30 curve right    0 0    stop"));
  Serial.println(F("  t     test each wheel on its own"));
  Serial.println(F("  c     find the slowest PWM that moves it (wheels ON the floor)"));
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
      } else if (len == 1 && (line[0] == 'c' || line[0] == 'C')) {
        calibrate();
      } else if (len > 0 && sscanf(line, "%d %d", &fwd, &turn) == 2) {
        drive(fwd, turn);
        lastCmd = millis();
      } else if (len > 0) {
        // Not two numbers and not "t". Say so instead of silently doing nothing -
        // otherwise a typo looks exactly like broken hardware. The wheels are left
        // alone on purpose: a line we don't understand must never move the robot.
        Serial.println(F("  ? I need two numbers, like \"50 0\"  (forward, turn), or t, or c"));
      }
      len = 0;                                 // ready for the next line
    } else if (len < sizeof(line) - 1) {
      line[len++] = c;
    }
  }

  // Failsafe: nothing heard from the Pi for TIMEOUT_MS -> stop, immediately.
  if (!stopped && millis() - lastCmd > TIMEOUT_MS) {
    stopNow();
  } else {
    ramp();                                    // otherwise ease toward the asked-for speed
  }
}
