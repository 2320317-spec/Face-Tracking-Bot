# LLM companion — idea, not built yet

Written 24 September 2026. A program on the **laptop** that runs a local language model and
talks to the robot through the web API it already has. Nothing here is implemented; this is
the plan so the idea survives.

## The one rule

**The LLM commands. It never drives.**

The robot decides 10–20 times a second. A 7B model on a laptop answers in 1–3 seconds — that
is 20 to 60 frames of lag. So the model is a person pressing buttons on the dashboard, not a
replacement for `brain.py`. Steering, distance keeping and the failsafes stay exactly where
they are.

Everything below obeys that rule. Nothing in this document goes inside the control loop.

## How it plugs in

```
   you speak or type
          │
          ▼
  ┌──────────────────┐   HTTP    ┌────────────────────┐
  │ laptop           │  :11434   │ Ollama             │  local model, no internet
  │  bridge program  │◄─────────►│ qwen2.5 / moondream│
  └──────────────────┘           └────────────────────┘
          │  HTTP to 10.42.0.1:8000  (the robot's own hotspot)
          ▼
  ┌──────────────────────────────────────────────┐
  │ the robot — unchanged                        │
  │ /api/status /api/mode /api/run /api/move ... │
  └──────────────────────────────────────────────┘
```

The robot does not know the companion exists. If the laptop crashes mid-demo the robot keeps
following, and the dashboard still works. That is the whole reason for this shape.

**Every feature shares one loop:** read status → take input → ask the model → **validate** →
POST to the robot. Build that once and each feature below is a small addition to it.

## The features

Ordered by what to build first. The "robot changes" column is the important one — most of
these need none at all.

| # | Feature | What it does | Robot changes needed |
|---|---|---|---|
| 1 | **Natural language → commands** | "follow me", "stop", "back off a bit", "spin twice" become `/api/mode`, `/api/run`, `/api/move`, `/api/drive` calls | **None** — the API is already the tool list |
| 2 | **"Why did you do that?"** | Reads the status plus the rules from `brain.py` and explains its own decision in plain words | **None** (a short recent-events endpoint would help) |
| 3 | **Trick composer** | "do a happy dance" → the model writes a routine as `(fwd, turn, seconds)` steps, validated, then played | Small: `/api/move` must accept a one-off routine, not just a name |
| 5 | **Live narration** | Watches the status and speaks a line whenever something changes: "lost her… searching left… found her" | **None** |
| 6 | **Seeing what's there** | A vision model describes a frame from `/frame.jpg` on demand | **None** |
| 4 | **Naming people** | Several stored identities with names: "this is Kuya", then "follow Kuya, ignore me" | **Large** — `FaceLock` holds one person today; it would need a named set |

Feature 4 is listed last on purpose: it is the only one that changes how the robot itself
works, so it carries the only real risk of breaking something that already works.

### Why these two are the strongest

**#1 is the flagship** because it is the interaction everyone will try, and because your API
already *is* the tool list — the model picks from eight verbs it cannot exceed.

**#2 is the one a panel remembers.** Most student robots cannot say why they did anything.
Yours knows: the state machine, the measured face width, the thresholds it crossed. The model
only has to put that into a sentence.

## Safety

- **Validate everything before it reaches the robot.** The model emits JSON; the bridge checks
  the action is one of the known ones and every number is in range. A confused model then
  produces a *rejected command*, not a runaway robot.
- **STOP stays a hard rule.** Never route an emergency stop through a language model. The
  dashboard's STOP button and the Uno's 500 ms failsafe are worth more than any model.
- **Routines get checked too** (#3): nothing over ±100, no step under 0.15 s, no routine longer
  than ~10 s, and it must end with a stop.
- The model may **suggest** tuning changes but must never write to the robot's settings by
  itself. Tuning needs measurement, not prose.

## The hardware it would run on

Laptop: Intel Core 5 210H, 16 GB RAM, **RTX 4050 Laptop GPU, 6 GB VRAM**. Windows keeps about
0.5–1 GB of that, so budget ~5 GB.

| Model | 4-bit size | Speed | Use |
|---|---|---|---|
| Qwen2.5 3B Instruct | ~2.0 GB | ~90 tok/s | Commands, JSON — snappy |
| Qwen2.5 7B Instruct | ~4.7 GB | ~40 tok/s | Explanations, writing routines |
| moondream2 | ~1.8 GB | <1 s per image | "What do you see?" |
| faster-whisper small | ~0.5 GB | 0.3 s per 3 s clip | Speech → text |
| Piper | CPU | instant | Speaking back |

**They do not all fit at once.** 7B + vision + whisper is about 7 GB. Two options:

- **Small and always loaded** (recommended for a demo): 3B + moondream + whisper ≈ 4.3 GB, all
  resident, everything instant and predictable.
- **Swap on demand:** keep the 7B loaded, let Ollama unload it when the vision model is needed.
  Costs 2–3 seconds on each switch.

Spoken command round trip with the first option: speech → text 0.3 s, model → JSON 0.5 s, POST
instant. **Under a second.**

## Practical notes for demo day

- Everything is **local** — no internet, no API key to expire. That matters, because at the demo
  the Pi is a hotspot with no internet anyway.
- The laptop must join **FollowBot** to reach the robot, so it cannot be on school WiFi at the
  same time.
- **Plug the laptop in.** The GPU throttles hard on battery.

## Still to decide

- Which feature to build first (the user liked all six).
- Typing or speaking as the main input.
- Whether the companion gets its own window, or becomes a panel on the existing dashboard —
  which would fold neatly into the planned all-in-one page.
