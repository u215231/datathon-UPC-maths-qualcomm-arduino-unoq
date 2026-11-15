#!/usr/bin/env python3
"""The team's web app, served by the board: Teach (the coach), Reason (the solver) and Stats.

    python3 coach/build_bank.py            # once
    python3 web3/server.py --host 0.0.0.0  # then open http://<board-ip>:8000

Standard library only: the board has no Node.

- Teach: the routes of coach/server.py, under /api/coach/. While a student reads a problem, a
  background thread writes hints grounded in the board's own solution (coach/grounded.py).
- Reason: /api/reason/solve runs copilot.pipeline.solve, the function predict.py calls, so the page
  shows what the graded run does. A problem comes from the practice set, from typed text, or from a
  picture (RapidOCR, m3kang/image_to_json.py; where it isn't installed the page says so).
- The owl: /api/eyes tells the LED matrix which eyes to show (coach/applab, or owl_eyes inside an
  App Lab app). Without either, the page's own owl still follows along.
- The model has one slot: Reason pauses the background hints, and only one solve runs at a time.
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import datetime
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from copilot import pipeline, reason  # noqa: E402
from copilot.config import CONFIG, ROOT  # noqa: E402
from coach.coach import ask_model  # noqa: E402
from coach.core import Bank, Trainer  # noqa: E402
from coach.grounded import Grounder  # noqa: E402
from coach.server import make_handler as coach_handler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

ROOT = str(ROOT)
PUBLIC = os.path.join(HERE, "public")
SHELL_ROUTES = {"/", "/home", "/teach", "/coach", "/reason", "/solver", "/agent", "/uploader", "/stats", "/analytics"}
LLM = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
LETTERS = "ABCDE"
MAX_BODY = 15 * 1024 * 1024
TIME_LIMIT = float(CONFIG["TIME_LIMIT_SECONDS"])
UPLOADED = os.path.join(ROOT, "data", "uploaded.jsonl")
IMAGES = os.path.join(ROOT, "data", "images")
OCR_SCRIPT = os.path.join(HERE, "read_picture.py")  # RapidOCR, with m3kang/image_to_json.py's parsing
# RapidOCR lives in the laptop's virtual environment, when there is one
OCR_PYTHON = os.environ.get("OCR_PYTHON") or next(
    (p for p in (os.path.join(ROOT, ".venv", "bin", "python"), os.path.join(ROOT, ".venv", "Scripts", "python.exe"))
     if os.path.exists(p)), sys.executable)
EYE_STATES = ("idle", "boot", "thinking", "hint", "correct", "wrong", "listening", "sleeping")
# What the Coach's trainer says (coach/core.py: led(kind, value)) as owl eyes
EYES_FOR = {"tick": "correct", "cross": "wrong", "hint": "hint", "think": "thinking", "letter": "hint"}


class Refused(Exception):
    """A request we answer with an error message and a status code."""
    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code, self.extra = code, extra


def model_name():
    try:
        with urllib.request.urlopen(LLM + "/v1/models", timeout=2) as r:
            return os.path.basename(json.load(r)["data"][0]["id"])
    except (OSError, ValueError, KeyError, IndexError):
        return ""


def key_of(problem):
    return f"{problem['id']}_{problem.get('language', 'eng')}"


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- The owl's eyes on the LED matrix ---

def make_eyes(led_base):
    """Return eyes(state): tell the LED matrix, by whichever way exists. Never blocks, never raises.

    1. The LED app (coach/applab) listens on led_base: GET /eyes/<state>/0.
    2. Inside an App Lab app, owl_eyes/python/eyes_bridge.py talks to the sketch directly.
    """
    try:
        sys.path.insert(0, os.path.join(ROOT, "owl_eyes", "python"))
        from eyes_bridge import set_state as bridge  # type: ignore
    except Exception:  # noqa: BLE001 - a laptop, or not inside App Lab
        bridge = None
    last = {"state": "idle"}

    def send(state):
        if bridge:
            try:
                bridge(state)
            except Exception:  # noqa: BLE001 - the eyes must never break a lesson
                pass
        try:
            urllib.request.urlopen(f"{led_base}/eyes/{state}/0", timeout=1).read()
        except (OSError, ValueError):
            pass  # the LED app is optional

    def eyes(state):
        if state in EYE_STATES:
            last["state"] = state
            threading.Thread(target=send, args=(state,), daemon=True).start()

    eyes.last = last
    return eyes


# --- The problems of the Reason page ---

class Practice:
    """The organisers' practice set (data/demo/practice.jsonl) when it's there, else the sample problems."""
    def __init__(self):
        found = [(os.path.join(ROOT, "data", *parts), os.path.join(ROOT, "data", *images)) for parts, images in (
            (("demo", "practice.jsonl"), ("demo", "images")), (("sample_problems.jsonl",), ("images",)))]
        self.path, self.images = next(((p, i) for p, i in found if os.path.exists(p)), ("", ""))
        self.by_key = {key_of(p): p for p in read_jsonl(self.path)} if self.path else {}

    def image(self, key):
        path = os.path.join(self.images, key + ".png")
        return path if key in self.by_key and os.path.exists(path) else ""

    def listing(self):
        return [{"key": k, "id": p["id"], "language": p.get("language", "eng"), "level": p.get("level", 0),
                 "image": bool(self.image(k)), "start": " ".join(str(p.get("text", "")).split())[:60]}
                for k, p in self.by_key.items()]

    def public(self, key):
        return {**{k: v for k, v in self.by_key[key].items() if k != "label"}, "key": key,
                "image": bool(self.image(key))}


# --- Text to a structured problem (web1's parser, in Python) ---

LANGUAGE_WORDS = (
    ("cat", r"\b(què|quants|quantes|quin|quina|quins|quines|dels|pels|amb|això|és|són)\b"),
    ("esp", r"\b(qué|cuántos|cuántas|cuál|cuáles|los|las|del|con|una|está|son)\b"),
    ("fra", r"\b(quel|quelle|quels|quelles|combien|les|des|avec|dans|est|sont)\b"),
    ("deu", r"\b(welche|welcher|welches|wie viele|der|die|das|und|mit|ist|sind)\b"),
)
MARKER = re.compile(r"(?:^|[\s\n])[\(\[]?([A-E])[\)\]\.:]\s*")


def detect_language(text):
    lower = f" {str(text or '').lower()} "
    return next((lang for lang, words in LANGUAGE_WORDS if re.search(words, lower)), "eng")


def number(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def label_of(value):
    value = str(value or "").upper()
    return value if value in tuple(LETTERS) else ""


def this_year():
    return datetime.date.today().year


def normalize(problem):
    """Any JSON a person typed -> a problem with every M3Kang field."""
    options = problem.get("options") if isinstance(problem.get("options"), dict) else {}
    options = {l: str(options[l]).strip() for l in LETTERS if str(options.get(l, "")).strip()}
    text = str(problem.get("text") or "").strip()
    level = number(problem.get("level"), 0)
    return {"id": str(problem.get("id") or f"lvl-{level}_{this_year()}_custom").strip(),
            "language": str(problem.get("language") or detect_language(text)).lower(),
            "level": level, "year": number(problem.get("year"), this_year()),
            "text_only": len(options) == 5, "text": text, "options": options, "label": label_of(problem.get("label"))}


def structure(raw, given):
    """Split pasted text into the statement and the options A-E: the last run of markers A, B, C, D, E."""
    raw = str(raw or "").replace("\r\n", "\n").strip()
    marks = [(m.group(1), m.start(), m.end()) for m in MARKER.finditer(raw)]
    statement, options = raw, {}
    for i in range(len(marks) - 1, -1, -1):
        if marks[i][0] != "A":
            continue
        run = [marks[i]]
        for mark in marks[i + 1:]:
            if len(run) < 5 and mark[0] == LETTERS[len(run)]:
                run.append(mark)
        if len(run) == 5:
            ends = [mark[1] for mark in run[1:]] + [len(raw)]
            found = {LETTERS[k]: re.sub(r"\s+", " ", raw[run[k][2]:ends[k]]).strip() for k in range(5)}
            if all(found.values()):
                statement, options = raw[:run[0][1]].strip(), found
            break
    question = re.match(r"(\d{1,2})\s*[.)]\s+", statement)
    level = number(given.get("level"), 0)
    year = number(given.get("year"), this_year())
    language = str(given.get("language") or "auto").lower()
    return {"id": str(given.get("id") or "").strip() or f"lvl-{level}_{year}_{question.group(1) if question else 1}",
            "language": detect_language(statement) if language == "auto" else language,
            "level": level, "year": year, "text_only": len(options) == 5, "text": statement, "options": options,
            "label": label_of(given.get("label"))}


# --- A picture to a structured problem (m3kang/image_to_json.py, RapidOCR) ---

_ocr_ready = None


def ocr_ready():
    global _ocr_ready
    if _ocr_ready is None:
        try:
            _ocr_ready = os.path.exists(OCR_SCRIPT) and subprocess.run(
                [OCR_PYTHON, "-c", "import rapidocr_onnxruntime"], capture_output=True, timeout=60).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _ocr_ready = False
    return _ocr_ready


def decode_image(data_url, filename=""):
    match = re.match(r"data:image/([a-zA-Z0-9+.-]+);base64,(.+)$", str(data_url or ""), re.S)
    if not match:
        raise Refused(400, "That isn't a picture we can read. Upload a PNG, JPG or WEBP file.")
    kinds = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "webp": ".webp", "bmp": ".bmp"}
    try:
        return base64.b64decode(match.group(2)), kinds.get(match.group(1).lower()) or os.path.splitext(filename)[1] or ".png"
    except ValueError:
        raise Refused(400, "The picture arrived damaged. Try again.")


def ocr(body):
    """Read an uploaded picture. A file name like lvl-0_2026_1_eng.png gives the id, level, year and language."""
    if not ocr_ready():
        raise Refused(501, "This device can't read pictures: RapidOCR isn't installed here. "
                           "Type or paste the problem's text instead.")
    image, ext = decode_image(body.get("image_base64"), str(body.get("filename") or ""))
    stem = os.path.splitext(os.path.basename(str(body.get("filename") or "uploaded.png")))[0]
    named = re.match(r"(lvl-(\d+)_(\d{4})_([^_]+))_([a-z]{2,3})$", stem, re.I)
    year = number(body.get("year"), int(named.group(3)) if named else this_year())
    level = number(body.get("level") if body.get("level") not in (None, "") else None, int(named.group(2)) if named else 0)
    language = str(body.get("language") or "auto").lower()
    language = (named.group(5).lower() if named else "") if language == "auto" else language
    pid = str(body.get("id") or "").strip() or (
        named.group(1) if named else f"lvl-{level}_{year}_{re.sub(r'[^a-zA-Z0-9_-]', '', stem)[:20] or 'custom'}")

    with tempfile.TemporaryDirectory() as folder:
        picture = os.path.join(folder, "picture" + ext)
        with open(picture, "wb") as f:
            f.write(image)
        try:
            run = subprocess.run([OCR_PYTHON, OCR_SCRIPT, picture], capture_output=True, text=True, timeout=120)
            read = json.loads(run.stdout.strip().splitlines()[-1]) if run.returncode == 0 else None
        except subprocess.TimeoutExpired:
            raise Refused(500, "Reading the picture took more than 120 seconds.")
        except (ValueError, IndexError):
            read = None
    if not isinstance(read, dict):
        raise Refused(500, "Reading the picture failed: " + (run.stderr or run.stdout).strip()[-400:])
    text, options = str(read.get("text") or ""), read.get("options") or {}
    problem = {"id": pid, "language": language or detect_language(text), "level": level, "year": year,
               "text_only": len(options) == 5, "text": text, "options": options, "label": label_of(body.get("label"))}
    option_line = "   ".join(f"{l}) {options[l]}" for l in LETTERS if options.get(l))
    return {"problem": problem, "rawText": "\n".join(part for part in (text, option_line) if part)}


# --- Reason: the graded pipeline, one problem at a time ---

class Solver:
    """Runs copilot.pipeline.solve in a thread, so the page can show a countdown while it works."""
    def __init__(self, grounder, eyes):
        self.grounder, self.eyes = grounder, eyes
        self.busy = threading.Lock()  # the board's model has one slot
        self.jobs = {}
        self.count = 0
        self.reply = ""  # what the model wrote for the job that holds `busy`
        self.thread = None
        run_program = reason.run_program

        def recording(reply, *args, **kwargs):  # pipeline.solve doesn't return the program: keep it here
            if threading.get_ident() == self.thread:  # not the background hints' program
                self.reply = reply
            return run_program(reply, *args, **kwargs)
        reason.run_program = recording

    def start(self, problem):
        if self.busy.locked():
            raise Refused(429, "The owl is already solving a problem. Wait for it to finish.")
        self.count += 1
        job = {"id": f"job{self.count}", "state": "waiting", "problem": problem, "started": None}
        if len(self.jobs) > 20:
            self.jobs.clear()
        self.jobs[job["id"]] = job
        threading.Thread(target=self.run, args=(job,), daemon=True).start()
        return job

    def run(self, job):
        problem = job["problem"]
        with self.busy:
            self.eyes("thinking")
            if self.grounder:
                self.grounder.pause()  # the background hints give the model back
            try:
                self.reply, self.thread = "", threading.get_ident()
                job.update(state="solving", started=time.time())
                result = pipeline.solve({k: v for k, v in problem.items() if k != "label"})
                found = re.search(r"```(?:python|py)?\s*\n(.*?)(?:```|$)", self.reply, flags=re.S)
                program = (found.group(1) if found else self.reply).strip()
                lp = result.get("lp") or {}
                top = max(lp.values()) if lp else 0.0
                weights = {l: 2.718281828 ** (lp[l] - top) for l in LETTERS if l in lp}
                total = sum(weights.values()) or 1.0
                label = label_of(problem.get("label"))
                job["result"] = {
                    "answer": result.get("answer"), "how": result.get("how", "letter"),
                    "status": result.get("status", "ok"), "seconds": result.get("seconds"),
                    "program": program, "code_value": result.get("code_value"),
                    "code_reason": result.get("code_reason", ""),
                    "probabilities": {l: round(w / total, 3) for l, w in weights.items()},
                    "letter_guess": max(lp, key=lp.get) if lp else None,
                    "label": label, "correct": (result.get("answer") == label) if label else None,
                    "strategy": pipeline.STRATEGY, "limit": TIME_LIMIT}
                self.eyes("correct" if job["result"]["correct"] else "hint")
            except Exception as error:  # noqa: BLE001 - the page shows it
                job["error"] = f"{type(error).__name__}: {error}"
                self.eyes("idle")
            finally:
                job["state"] = "done"
                if self.grounder:
                    self.grounder.resume()

    def public(self, job):
        shown = {"id": job["id"], "state": job["state"], "limit": TIME_LIMIT,
                 "elapsed": round(time.time() - job["started"], 1) if job["started"] else 0.0}
        for field in ("result", "error"):
            if field in job:
                shown[field] = job[field]
        return shown


def make_handler(trainer, bank, practice, solver, eyes, review):
    class Handler(coach_handler(trainer, bank, review=review)):
        def static(self, path):
            if path in SHELL_ROUTES:
                path = "/index.html"
            full = os.path.realpath(os.path.join(PUBLIC, path.lstrip("/")))
            if not full.startswith(os.path.realpath(PUBLIC) + os.sep) or not os.path.isfile(full):
                return self.send(404, {"error": "not found"})
            kind = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind.endswith(("javascript", "json")):
                kind += "; charset=utf-8"
            with open(full, "rb") as f:
                return self.send(200, f.read(), kind)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            params = dict(urllib.parse.parse_qsl(url.query))
            if url.path.startswith("/api/coach/"):
                self.path = "/api/" + self.path[len("/api/coach/"):]
                return super().do_GET()
            if url.path in ("/review", "/api/hints"):  # the teacher's page, only with --review
                return super().do_GET()
            if url.path == "/api/info":
                name = model_name()
                return self.send(200, {"llm": bool(name), "model": name.replace(".gguf", ""), "ocr": ocr_ready(),
                                       "time_limit": TIME_LIMIT, "practice": len(practice.by_key),
                                       "strategy": pipeline.STRATEGY, "eyes": eyes.last["state"]})
            if url.path == "/api/reason/problems":
                return self.send(200, practice.listing())
            if url.path == "/api/reason/problem":
                if params.get("key") not in practice.by_key:
                    return self.send(404, {"error": "unknown problem"})
                return self.send(200, practice.public(params["key"]))
            if url.path == "/api/reason/job":
                job = solver.jobs.get(params.get("id"))
                return self.send(200, solver.public(job)) if job else self.send(404, {"error": "unknown job"})
            if url.path.startswith("/api/reason/image/"):
                image = practice.image(urllib.parse.unquote(url.path[len("/api/reason/image/"):]))
                if not image:
                    return self.send(404, {"error": "image not found"})
                with open(image, "rb") as f:
                    return self.send(200, f.read(), "image/png")
            if url.path.startswith("/api/"):
                return self.send(404, {"error": "not found"})
            return self.static(url.path)

        def do_POST(self):
            if self.path.startswith("/api/coach/"):
                self.path = "/api/" + self.path[len("/api/coach/"):]
                return super().do_POST()
            if self.path == "/api/review":
                return super().do_POST()
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > MAX_BODY:
                    return self.send(413, {"error": "That's too big: 15 MB at most."})
                body = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self.send(400, {"error": "bad JSON"})
            try:
                return self.send(200, self.route(body))
            except Refused as refused:
                return self.send(refused.code, {"error": str(refused), **refused.extra})

        def route(self, body):
            if self.path == "/api/eyes":
                if body.get("state") not in EYE_STATES:
                    raise Refused(400, "unknown state")
                eyes(body["state"])
                return {"ok": True}
            if self.path == "/api/reason/solve":
                if body.get("key") in practice.by_key:
                    problem = practice.by_key[body["key"]]
                else:
                    given = body.get("problem") if isinstance(body.get("problem"), dict) else {}
                    if not str(given.get("text") or "").strip():
                        raise Refused(400, "Write the problem first.")
                    problem = normalize(given)
                    if len(problem["options"]) < 5:  # the options may be inside the text: "A) 3  B) 4 ..."
                        split = structure(problem["text"], {"language": problem["language"]})
                        if len(split["options"]) == 5:
                            problem.update(text=split["text"], options=split["options"], text_only=True)
                job = solver.start(problem)
                return {**solver.public(job), "problem": {k: v for k, v in problem.items() if k != "label"}}
            if self.path == "/api/structure-text":
                if not str(body.get("raw_text") or "").strip():
                    raise Refused(400, "Paste the problem's text first.")
                return {"problem": structure(body["raw_text"], body), "method": "parser"}
            if self.path == "/api/upload-ocr":
                return ocr(body)
            raise Refused(404, "not found")

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bank", default="data/teach.db", help="written by coach/build_bank.py")
    p.add_argument("--profile", default="data/teach_profile.db", help="the students' progress, kept on the board")
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it to your network")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--led", default="http://127.0.0.1:7000", help="the LED app's address (coach/applab)")
    p.add_argument("--no-coach", action="store_true", help="turn off 'ask the owl'")
    p.add_argument("--no-grounded", action="store_true",
                   help="don't write hints from the board's own solution in the background")
    p.add_argument("--prefer-grounded", action="store_true",
                   help="choose first the problems that already have a grounded hint (coach/warm_grounded.py)")
    p.add_argument("--review", action="store_true", help="also serve /review (it shows the answers)")
    args = p.parse_args()
    os.chdir(ROOT)
    if not os.path.exists(args.bank):
        sys.exit(f"{args.bank} not found. Build it first: python3 coach/build_bank.py")

    eyes = make_eyes(args.led)

    def led(kind, value=0):  # the trainer's events, as owl eyes
        if kind in EYES_FOR:
            eyes(EYES_FOR[kind])

    bank = Bank(args.bank)
    grounder = None if args.no_grounded else Grounder()
    trainer = Trainer(bank, args.profile, led=led, coach=None if args.no_coach else ask_model, grounder=grounder,
                      prefer_grounded=args.prefer_grounded)
    practice = Practice()
    solver = Solver(grounder, eyes)
    print(f"Teach: {len(bank.level)} problems, {bank.hint_count()} model hints, grounded hints "
          f"{'on' if grounder else 'off'}. Reason: {len(practice.by_key)} practice problems, strategy "
          f"'{pipeline.STRATEGY}'. Model {'up' if model_name() else 'DOWN'} on port {CONFIG['LLM_PORT']}. "
          f"OCR {'ready' if ocr_ready() else 'not installed'}.")
    print(f"Open http://{args.host}:{args.port} (Ctrl+C to stop)", flush=True)
    eyes("idle")
    ThreadingHTTPServer((args.host, args.port),
                        make_handler(trainer, bank, practice, solver, eyes, args.review)).serve_forever()


if __name__ == "__main__":
    main()
