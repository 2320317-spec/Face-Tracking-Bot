# pi/ — the robot program

Runs on the Raspberry Pi, and on the PC with `--dry` (no Uno needed). You'll write these files in roadmap step 6, combining your scripts from [`steps/`](../steps/).

| File | What it does |
|---|---|
| `follow.py` | Main program: camera → detection → decision → sends `fwd turn` to the Uno every frame |
| `web.py` | Phone dashboard server (Flask): live view, mode buttons, Start / STOP, joystick |
| `templates/index.html` | The phone page |
| `models/` | Face detection model — downloaded, not stored on GitHub ([how to get it](models/README.md)) |

Delete `templates/.gitkeep` once `index.html` is in that folder.

## Run

On the PC, from the project root:

```bash
.venv\Scripts\python pi\follow.py --dry
```

Then open http://localhost:8000.

On the Pi: see the build plan, sections 5.2–5.3 and 5.12.
