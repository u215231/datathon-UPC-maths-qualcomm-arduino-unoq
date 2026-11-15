"""The owl's eyes: the board's 8x13 LED matrix, behind the glasses of the 3D-printed owl.

One set of animations for the whole product: the frames and timings are in owl_eyes/eyes.py,
the sketch (sketch/sketch.ino, generated from it) plays them, and this app lets the web
servers choose the state over HTTP. The owl on the web page (web3/public/owl.js) shows the
same states.

    GET /eyes/idle/0        open eyes that blink and glance (the resting state)
    GET /eyes/sleeping/0    eyes closed, a z drifting away
    GET /eyes/thinking/0    a light runs round each eye, while the model works
    GET /eyes/hint/0        leans in, raises a brow, winks
    GET /eyes/correct/0     happy eyes, bouncing (back to idle after 7 s)
    GET /eyes/wrong/0       worried, kind (back to idle after 9 s)
    GET /eyes/listening/0   wide awake, looking at the student
    GET /eyes/boot/0        the wake-up animation

When nothing has asked for anything for SLEEP_AFTER seconds, the owl falls asleep: its eyes
close completely. Any request wakes it.

The Coach's first protocol still works (coach/server.py sends it):

    GET /led/tick/0  -> correct      GET /led/cross/0 -> wrong      GET /led/think/0 -> thinking
    GET /led/hint/2  -> hint         GET /led/face/0  -> idle       GET /led/level/5 -> idle
    GET /led/letter/C  the solution's letter, for a few seconds, then idle
"""
import time

import numpy as np
from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge, Frame

STATES = ("idle", "boot", "thinking", "hint", "correct", "wrong", "listening", "sleeping")
# Seconds a state stays before the eyes go back to idle (0 = until the next request)
HOLD = {"correct": 7.0, "wrong": 9.0, "hint": 12.0, "listening": 30.0, "boot": 5.5}
FROM_LED = {"tick": "correct", "cross": "wrong", "hint": "hint", "think": "thinking", "face": "idle", "level": "idle"}
SLEEP_AFTER = 120.0  # seconds without a request before the owl falls asleep
LETTER_HOLD = 5.0
ON = 7

# 5x7 letters, for the solution
FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
}

state = {"eyes": "boot", "asked": time.time(), "until": time.time() + HOLD["boot"]}


def show(name):
    """Play one eye state. Returns False if the sketch didn't take it."""
    try:
        ok = bool(Bridge.call("eyes", name))
    except Exception:  # noqa: BLE001 - a busy or missing microcontroller must not stop the app
        ok = False
    if ok:
        state["eyes"] = name
        state["until"] = time.time() + HOLD[name] if name in HOLD else 0.0
    return ok


def letter(char):
    grid = np.zeros((8, 13), dtype=np.uint8)
    for r, line in enumerate(FONT[char]):
        for c, pixel in enumerate(line):
            if pixel == "#":
                grid[r, 4 + c] = ON
    try:
        Bridge.call("draw", Frame(grid).to_board_bytes())
    except Exception:  # noqa: BLE001
        return False
    state["eyes"] = "letter"
    state["until"] = time.time() + LETTER_HOLD
    return True


def eyes(name: str, value: str = "0"):
    name = name.strip().lower()
    if name not in STATES:
        return {"error": "unknown state", "states": list(STATES)}
    state["asked"] = time.time()
    return {"ok": show(name), "eyes": state["eyes"]}


def led(kind: str, value: str = "0"):
    """The Coach's first protocol, shown with the owl's eyes."""
    state["asked"] = time.time()
    if kind == "letter" and value.upper() in FONT:
        return {"ok": letter(value.upper()), "shown": "letter"}
    if kind not in FROM_LED:
        return {"error": "unknown picture"}
    name = FROM_LED[kind]
    # "level" follows every answer and every model call: it only ends thinking, or wakes the owl
    if kind == "level" and state["eyes"] not in ("thinking", "sleeping", "boot"):
        return {"ok": True, "shown": state["eyes"]}
    return {"ok": show(name), "shown": name}


def loop():
    now = time.time()
    if state["until"] and now > state["until"]:
        show("idle")
    elif state["eyes"] == "idle" and now - state["asked"] > SLEEP_AFTER:
        show("sleeping")
    time.sleep(0.2)


ui = WebUI()
ui.expose_api("GET", "/eyes/{name}/{value}", eyes)
ui.expose_api("GET", "/led/{kind}/{value}", led)
ui.expose_api("GET", "/status", lambda: state)

App.run(user_loop=loop)
