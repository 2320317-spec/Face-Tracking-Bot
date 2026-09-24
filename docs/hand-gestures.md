# Hand gesture control — idea, not built yet

Written 24 September 2026. Control the robot by showing it your hand: open palm to stop,
fist to hold, pointing to go, and so on. Nothing here is implemented; this is how it would
work and what it would cost.

## The pipeline

```
camera frame → find the hand → 21 points on it → name the gesture → hold it → command
                  (detector)     (landmark model)    (geometry)     (debounce)
```

It is the same shape as the face pipeline already in `pi/vision.py`: **detect a box, get
landmarks, do arithmetic on them.** YuNet gives 5 landmarks and `head_turn()` computes the
head direction from the nose position; a hand model gives 21 landmarks and the same kind of
arithmetic gives the gesture. Only the middle stage is new.

## Reading the hand

**Two models, in sequence — the same two-stage idea as detect-then-recognise:**

1. **Palm detection** finds boxes where hands are. It detects *palms*, not whole hands,
   because a palm is a rigid blob; fingers move too much to be a reliable detection target.
2. **Hand landmarks** looks only inside that box and returns **21 points** — the wrist, then
   four points per finger (knuckle, two joints, tip), each with x, y and rough depth.

```
        8   12  16  20      fingertips
        |   |   |   |
        7  11  15  19
        6  10  14  18
    4   5   9  13  17       knuckles
     \   \  |  /  /
      3   \ | /  /
       2   \|/  /
        1   +  /
         \  | /
          \ |/
            0               wrist
```

Everything after this is arithmetic on 21 coordinates. No further machine learning.

## Naming the gesture

A finger is extended if its **tip is further from the wrist than its middle joint is**:

```python
extended = distance(tip, wrist) > distance(middle_joint, wrist)
```

Curl a finger and the tip swings back toward the palm, so it ends up closer to the wrist than
the joint. Count the extended fingers:

| Fingers up | Gesture | Possible meaning |
|---|---|---|
| 0 | fist | hold position |
| 1 (index) | pointing | go that way |
| 2 | peace | switch mode |
| 5 | open palm | **STOP** |

The thumb needs its own rule: it bends sideways rather than curling, so it is compared across
the hand instead of along it.

**Use ratios, never pixels.** Divide every distance by the hand's own size (wrist to middle
knuckle) and the gesture reads the same whether the hand is 30 px or 300 px wide. Same
reasoning as the `w`-based distance estimate: scale is information, so don't let it leak into
the shape.

For direction (swipes, pointing left or right), take the vector from the wrist to the index
tip, or track the hand's movement across several frames.

## Three ways to detect a hand, and why only one is worth it

| Method | How it works | Verdict |
|---|---|---|
| **Landmark models** (MediaPipe-style) | Two small neural nets → 21 points | **Use this.** Robust to lighting, skin tone and background |
| **Skin colour + contours** | HSV mask → contour → count the valleys between fingertips | Literally `find_color()` with different HSV values. Cheap, but breaks on wooden doors, warm light, and any face in frame |
| **Image classifier** | Train a CNN on cropped hand photos | Needs a dataset. Most work, least robust |

## What it would cost here

**No new library.** OpenCV Zoo — the source of the YuNet and SFace models in `pi/models/` —
also publishes palm detection and hand landmark models in ONNX, loaded with the same
`cv2.dnn` calls already used in `vision.py`.

**Time is the problem.** The face pipeline already costs ~50 ms per frame, and a dim room
gives only 10-12 fps. A two-stage hand pipeline roughly doubles that. So it cannot run
continuously alongside face following. Options:

- a dedicated **gesture mode** (no face following while in it), or
- check for hands **every 5th frame**, the way Smart mode already spaces out its fingerprint
  checks.

**Range is fine.** A palm is about 9 cm wide, so at 1 m it is ~37 px — comfortably detectable
at the distances the robot follows from.

## The two rules that make it usable

- **Debounce.** A gesture must be held for several frames before it counts, or a hand passing
  through a fist shape on its way to a wave will stop the robot. The same idea as
  `TRUST_FRAMES` and `LOST_GRACE`.
- **Only obey the person it is locked onto.** Smart mode already knows which face is yours.
  Accept gestures only from a hand belonging to that person, and a classmate waving at the
  robot during the demo does nothing. This is the detail that would make this version stand
  out from every other gesture robot.

## Where it fits with everything else

Gestures are a **command channel**, exactly like the [LLM companion](llm-companion.md): they
choose what the robot should do, they never steer it frame by frame. `brain.py` keeps the
control loop. Both ideas answer the same question — how do I tell the robot what I want —
and could share the same command layer.

An open palm meaning STOP is intuitive and worth having, but it must never be the *only* stop.
The dashboard button and the Uno's 500 ms failsafe stay as they are.
