# =============================================================================
# web.py - the phone dashboard (a small web server that runs inside follow.py)
# =============================================================================
# Open http://<robot>:8000 on a phone or laptop on the same WiFi:
#   live view    what the robot sees, with boxes and labels drawn in
#   buttons      Color / Face / Manual,  Simple / Smart,  Start / STOP,  Forget me
#   joystick     drive it yourself (Manual mode)
#   tap a face in the live view (Face + Smart) = "this is me"
#
# How it talks to follow.py: they share ONE Shared object. The page changes it
# (mode, Start/STOP, joystick...); follow.py reads it every frame, and writes back
# the status and the newest live-view picture.
# =============================================================================
import logging
import threading
import time

from flask import Flask, Response, jsonify, render_template, request

from brain import W, H


# ---- Settings ---------------------------------------------------------------------
STREAM_FPS = 15         # live-view pictures per second sent to the browser. The robot itself runs
                        # faster; this only sets how smooth the video on the phone looks.
                        #   Video laggy over WiFi -> lower it (e.g. 10)


class Shared:
    """Everything the web page and the robot loop share."""

    def __init__(self, mode="color"):
        self.mode = mode            # color | face | manual
        self.who = "smart"          # face mode: simple (whoever it sees) | smart (only you)
        self.running = False        # starts STOPPED: nothing moves until Start is pressed
        self.joystick = (0, 0)      # last (fwd, turn) from the joystick, -100..100
        self.joystick_t = 0.0       # when it arrived (the robot stops if it gets too old)
        self.click = None           # (x, y) in the robot's picture: "this face is me"
        self.forget = False         # "Forget me" was pressed
        self.jpeg = None            # newest live-view picture (JPEG bytes), made by follow.py
        self.viewers = 0            # how many live views are open (0 = follow.py skips making pictures)
        self.status = {}            # what follow.py reports: state, fps, ... (shown on the page)


def create_app(shared):
    """The web server: which address does what."""
    app = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)      # don't print every single request

    def body():
        """The JSON the page sent, or {} if it sent nothing."""
        return request.get_json(force=True, silent=True) or {}

    @app.get("/")
    def index():
        return render_template("index.html")                    # templates/index.html

    @app.get("/stream")
    def stream():
        """The live view: a never-ending series of JPEG pictures (called MJPEG) - an <img> shows it as video."""
        def pictures():
            shared.viewers += 1
            try:
                while True:
                    jpg = shared.jpeg
                    if jpg is not None:
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    time.sleep(1 / STREAM_FPS)
            finally:
                shared.viewers -= 1                             # the page was closed
        return Response(pictures(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/status")
    def status():
        """Everything the page shows. It asks twice a second."""
        return jsonify(shared.status | {"mode": shared.mode, "who": shared.who, "running": shared.running})

    @app.post("/api/mode")
    def mode():
        if body().get("mode") in ("color", "face", "manual"):
            shared.mode = body()["mode"]
        return status()

    @app.post("/api/who")
    def who():
        if body().get("who") in ("simple", "smart"):
            shared.who = body()["who"]
        return status()

    @app.post("/api/run")
    def run():
        """Start ({"run": true}) or STOP ({"run": false})."""
        shared.running = bool(body().get("run"))
        return status()

    @app.post("/api/drive")
    def drive():
        """The joystick, about 10 times a second while you touch it: {"fwd": .., "turn": ..}."""
        d = body()
        clamp = lambda v: max(-100, min(100, int(v)))
        shared.joystick = (clamp(d.get("fwd", 0)), clamp(d.get("turn", 0)))
        shared.joystick_t = time.time()
        return "", 204

    @app.post("/api/click")
    def click():
        """A tap on the live view, as fractions (0 to 1) of its width and height -> robot picture pixels."""
        d = body()
        fraction = lambda v: max(0.0, min(1.0, float(v)))
        shared.click = (fraction(d.get("x", 0)) * W, fraction(d.get("y", 0)) * H)
        return "", 204

    @app.post("/api/forget")
    def forget():
        """ "Forget me": SMART forgets who you are; the next face becomes you."""
        shared.forget = True
        return "", 204

    return app


def start(shared, port=8000):
    """Run the web server on a background thread, so the robot loop keeps running."""
    app = create_app(shared)
    threading.Thread(target=app.run, daemon=True,
                     kwargs={"host": "0.0.0.0", "port": port, "threaded": True}).start()
