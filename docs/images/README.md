# docs/images/

Photos and diagrams for the README and the build plan: wiring, the finished robot, screenshots of the dashboard.

Don't upload photos of people's faces without their permission — this repository is public if you make it public.

## Diagrams

Drawn during the 25 September walkthrough. Each one is a **standalone SVG** — its styles are inside the file, so it renders anywhere (GitHub, a browser, a slide) with no stylesheet and no internet. They follow the system light/dark setting, so they stay readable on either.

| File | What it shows |
|---|---|
| [`01-system-architecture.svg`](01-system-architecture.svg) | The whole chain: one frame through the Pi's four steps, across USB to the Uno, out to the motors — with the dashboard on its own path |
| [`02-facelock-ladder.svg`](02-facelock-ladder.svg) | How Smart mode decides which face is you: three tests in order of cost, cheapest first, audited every 5th frame |
| [`03-distance-by-height.svg`](03-distance-by-height.svg) | The three horizontal lines, and why there are three and not one |
| [`04-steering-by-duration.svg`](04-steering-by-duration.svg) | One 0.47 s cycle: driving is continuous, turning happens in nudges of 0.06–0.20 s |

To use one in a document: `![](docs/images/01-system-architecture.svg)`

To change one, edit the `<svg>` directly — the shapes are plain rects, lines and text, and the `<style>` block at the top defines every class and colour used.
