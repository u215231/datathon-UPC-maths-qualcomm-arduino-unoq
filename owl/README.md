# Uino, plug and play

Uino is the owl: a maths tutor for Kangaroo problems that runs on an Arduino UNO Q with no internet. After one install, it starts by itself every time the board gets power.

## What you need

A UNO Q 4 GB set up with steps 0–12 of the [setup guide](../docs/SETUP_GUIDE.md): llama.cpp built, the two model services running, and `data/index.db` built. Optional: the maths model file in `~/models` (see [machine/NOTES_MATH.md](../machine/NOTES_MATH.md)); without it, Reason answers with the 0.8B model.

## Install (once, on the board)

```bash
git clone -b plug-and-play https://github.com/u215231/datathon-UPC-maths-qualcomm-arduino-unoq.git ~/uino
cd ~/uino
bash owl/install.sh
```

It takes about 3 minutes and needs no sudo. You should see four steps, ending with the address of the page:

1. **Checking the board:** the two model servers answer, and it says which Reason model it found.
2. **The problem bank for Teach:** `data/teach.db`, built once (about 50 s).
3. **The eyes:** the LED-matrix sketch is compiled and flashed as the App Lab app `uino-eyes`, and set as the board's default app.
4. **The web page, at every boot:** one line in the `arduino` user's crontab runs `owl/start.sh`.

## Use

- Plug the board in. The eyes wake up; when the page is ready, open `http://<board-ip>:8000` from a laptop or phone on the same network.
- Over USB instead: `adb forward tcp:8000 tcp:8000`, then <http://127.0.0.1:8000>.
- **Teach:** pick a level and a language, answer, and climb the hint ladder when you're stuck.
- **Reason:** type or pick a problem and watch Uino write its program. To drop a *picture* of a problem, run the page from a laptop, which reads the picture (see below).
- **Stats:** what we measured.

## The picture reader (on a laptop)

Reading a photo needs RapidOCR, which we keep on the laptop. The laptop serves the same page and reads the picture; the board still does all the maths.

```bash
# on the laptop, in the repository folder, with the board on USB
python3 -m venv .venv && .venv/bin/pip install rapidocr_onnxruntime      # once
adb forward tcp:8081 tcp:8081; adb forward tcp:8082 tcp:8082; adb forward tcp:8084 tcp:8084; adb forward tcp:7000 tcp:7000
python3 coach/build_bank.py                                              # once
python3 web3/server.py --port 8010                                       # then open http://127.0.0.1:8010
```

## How it starts

| Piece | Started by | Where |
| --- | --- | --- |
| Language model (Qwen3.5 0.8B) and embeddings | systemd services `math-llm`, `math-embed` (setup guide, step 7) | ports 8081, 8082 |
| Maths model for Reason | `web3/server.py`, when it starts | port 8084 |
| Web page | cron `@reboot` → `owl/start.sh` → `web3/server.py` | port 8000 |
| LED eyes | App Lab default app `uino-eyes` | port 7000, the STM32 draws the matrix |

Logs: `results/owl-web.log`, and `arduino-app-cli app logs ~/ArduinoApps/uino-eyes`.

## Remove

```bash
bash owl/install.sh --remove
```

## Tested

On our UNO Q on 15 Nov 2026: the install from a fresh checkout; the eyes app answering every state; the Coach's 27 checks (`python3 coach/check.py http://127.0.0.1:8000 --api=/api/coach`) in Catalan; a Reason problem answered through the page in 33 s, with the program appearing after 20 s. Not timed yet: how long a cold boot takes until the page answers.
