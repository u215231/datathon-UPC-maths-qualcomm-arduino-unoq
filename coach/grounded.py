"""Hints grounded in the board's own solution, written in the background while the student reads.

When a problem opens, one worker thread asks the board's model for a Python program that solves it
(the Reason copilot's route, copilot/reason.py), and runs it in the sandbox. If the result matches
an option, and that option is the answer key's, the program is trusted. The model then explains
that program in words: the method (one sentence) and the first step (up to two). Explaining a
working program is much easier for a 0.8B model than solving the problem (see copilot/teach.py).

Measured on the board, this takes minutes (solve about 40 s, method 84 s, first step 41 s), so:

- it never runs while the student waits: Trainer.hint() takes what is ready, or falls back;
- one problem at a time, the newest one; opening another problem cancels the old work;
- pause() stops it at once, so the Reason page has the model's single slot to itself;
- results are kept in data/teach_grounded.json, so a problem opened before a demo is instant.

Every sentence passes copilot.teach.leaks (no answer, no option value, not the program's result),
coach.core.leaks, and a filter for words about code, before it is stored.
"""
import json
import os
import re
import threading
import urllib.request

from copilot import reason, teach
from copilot.config import CONFIG

from .core import leaks as answer_leaks

URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
KEEP = {2: 1, 3: 2}  # sentences kept per level: the first ones are the reliable ones


class Cancelled(Exception):
    pass


class _Solved:
    """What copilot.teach.grounded_prompt needs to know about a solved problem."""
    def __init__(self, problem, program):
        self.problem, self.program = problem, program


def sentences(text):
    """Complete sentences only: a cut-off last one is dropped."""
    parts = re.findall(r"[^.!?]+[.!?]+(?=\s|$)", text.strip())
    return [" ".join(part.split()) for part in parts]


class Grounder:
    def __init__(self, url=URL, cache_path="data/teach_grounded.json", solve_seconds=None):
        self.url, self.cache_path = url, cache_path
        self.solve_seconds = teach.SOLVE_SECONDS if solve_seconds is None else solve_seconds
        self.records = {}  # "id|language" -> {status, program, value, method, step, reason}
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    self.records = {k: v for k, v in json.load(f).items() if v.get("status") != "thinking"}
            except (OSError, ValueError):
                self.records = {}
        self.cond = threading.Condition()
        self.want = None      # (key, problem): the newest problem a student opened
        self.active = None    # the key being worked on
        self.paused = 0
        self.cancel = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    # -- what the Trainer and the server call --

    @staticmethod
    def key(pid, language):
        return f"{pid}|{language}"

    def open(self, problem):
        """A student opened this problem: start (or carry on) thinking about it."""
        key = self.key(problem["id"], problem["language"])
        with self.cond:
            if self.records.get(key, {}).get("status") in ("ready", "none"):
                return
            self.want = (key, problem)
            if self.active and self.active != key:
                self.cancel.set()
            self.cond.notify_all()

    def get(self, pid, language):
        """{'status': 'thinking' | 'ready' | 'none', 'method': str, 'step': str}. Never blocks."""
        with self.cond:
            record = self.records.get(self.key(pid, language))
            if not record:
                wanted = self.want and self.want[0] == self.key(pid, language)
                return {"status": "thinking" if wanted else "none", "method": "", "step": ""}
            return {"status": record["status"], "method": record.get("method") or "",
                    "step": record.get("step") or ""}

    def pause(self, wait=25.0):
        """Free the model's slot for someone else. Returns True once the worker has stopped."""
        with self.cond:
            self.paused += 1
            self.cancel.set()
            return self.cond.wait_for(lambda: self.active is None, timeout=wait)

    def resume(self):
        with self.cond:
            self.paused = max(self.paused - 1, 0)
            self.cond.notify_all()

    # -- the worker --

    def _ready(self):
        return self.want is not None and not self.paused

    def _loop(self):
        while True:
            with self.cond:
                self.cond.wait_for(self._ready)
                key, problem = self.want
                self.active = key
                self.cancel.clear()
                record = self.records.setdefault(key, {"status": "thinking"})
            try:
                self._work(problem, record)
            except Cancelled:
                pass  # the stages already done stay in the record
            except Exception as error:  # noqa: BLE001 - no grounded hint: the other rungs still work
                record.update(status="none", reason=f"error: {type(error).__name__}")
            with self.cond:
                self.active = None
                if record["status"] != "thinking":
                    self._save()
                    if self.want and self.want[0] == key:
                        self.want = None
                self.cond.notify_all()

    def _work(self, problem, record):
        if "program" not in record:
            reply = self._complete(reason.chat_prompt(problem, reason.CODE_INSTRUCTION),
                                   int(self.solve_seconds * reason.WRITE_TPS), self.solve_seconds)
            value, why = reason.run_program(reply)
            letter = reason.matching_option(value, problem.get("options")) if value is not None else None
            found = re.search(r"```(?:python|py)?\s*\n(.*?)(?:```|$)", reply, flags=re.S)
            record.update(program=(found.group(1) if found else reply).strip(), value=value)
            if not letter or letter != problem.get("label"):
                record.update(status="none", reason=why if value is None else
                              "no option matches" if not letter else "the program's answer isn't the key's")
                return
        solved = _Solved(problem, record["program"])
        value = record.get("value")
        results = () if value is None else tuple({f"{value:g}", str(int(value)) if float(value).is_integer() else f"{value:g}"})
        for level, field in ((2, "method"), (3, "step")):
            if field in record:
                continue
            _instruction, starts, max_tokens = teach.GROUNDED[level]
            start = starts[teach.lang_of(problem)] + " "
            text = start + self._complete(teach.grounded_prompt(solved, level), max_tokens, 120,
                                          stop=["<|im_end|>", "\n\n"]).lstrip()
            kept = []
            for sentence in sentences(text):
                if (teach.CODE_WORDS.search(sentence) or teach.leaks(sentence, problem, results)
                        or answer_leaks(sentence, problem)):
                    break  # what follows a bad sentence leans on it
                kept.append(sentence)
                if len(kept) >= KEEP[level]:
                    break
            record[field] = " ".join(kept)
        record["status"] = "ready" if record.get("method") or record.get("step") else "none"

    def _complete(self, prompt, max_tokens, seconds, stop=None):
        """One streamed completion. Closing the stream when cancelled stops llama-server's generation."""
        payload = {"prompt": prompt, "n_predict": max_tokens, "temperature": 0, "seed": int(CONFIG["SEED"]),
                   "cache_prompt": True, "stream": True, "t_max_predict_ms": int(seconds * 1000)}
        if stop:
            payload["stop"] = stop
        request = urllib.request.Request(self.url + "/completion", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        text = ""
        with urllib.request.urlopen(request, timeout=seconds + 60) as response:
            for raw in response:
                if self.cancel.is_set():
                    raise Cancelled
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                chunk = json.loads(line[5:])
                text += chunk.get("content", "")
                if chunk.get("stop"):
                    break
        if self.cancel.is_set():
            raise Cancelled
        return text

    def _save(self):
        if not self.cache_path:
            return
        try:
            done = {k: v for k, v in self.records.items() if v.get("status") != "thinking"}
            with open(self.cache_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(done, f, ensure_ascii=False)
            os.replace(self.cache_path + ".tmp", self.cache_path)
        except OSError:
            pass  # the cache is a convenience
