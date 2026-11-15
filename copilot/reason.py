"""Reason mode: the hybrid that scored best on the 50 Discord practice problems (35/100 rows, chance 20).

For each problem, within one clock:
1. Plain letter: the model reads the problem and we keep its probability for each letter A-E (~10 s on the board).
   This is the answer if nothing better comes.
2. Python: if time is left, the model writes a short program. We run it in a sandbox; if the number it prints
   matches exactly one option, that option is the answer (right 11 times out of 14 on the practice set).
3. Balancing (predict.py, after all problems): the practice answers are balanced by design (10 per letter), and
   the model over-uses A and D. The letters that came from step 1 are re-assigned so each letter is used about
   n/5 times, keeping the most probable assignment. Answers from step 2 are never changed.

Measured on the board (Qwen3.5 0.8B Q8_0): reads ~11 tokens/s, writes ~5.7 tokens/s.
"""
import ast
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from .client import post
from .config import CONFIG
from .llm import SYSTEM, format_problem

LETTERS = "ABCDE"
BASE_URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
WRITE_TPS = float(CONFIG.get("WRITE_TOKENS_PER_SECOND", 5.7))
CODE_INSTRUCTION = ("\nWrite a short Python program that computes the answer and prints only the final value. "
                    "Reply with the code only.")
ALLOWED_IMPORTS = {"math", "itertools", "fractions", "functools", "collections"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "input", "__import__", "globals", "locals", "vars",
                "getattr", "setattr", "delattr", "breakpoint", "help", "exit", "quit"}


def chat_prompt(problem, instruction=""):
    """Qwen chat template with thinking switched off, as llama-server builds it with --reasoning off."""
    user = format_problem(problem) + (instruction or "\nAnswer:")
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def letter_logprobs(prompt, timeout, url=BASE_URL):
    """Log-probability of each letter as the next token (-99 when it's not among the top 50)."""
    r = post(url + "/completion", {"prompt": prompt, "n_predict": 1, "temperature": 0, "n_probs": 50,
                                   "seed": int(CONFIG["SEED"]), "cache_prompt": True}, timeout=timeout)
    lp = {c: -99.0 for c in LETTERS}
    first = (r.get("completion_probabilities") or [{}])[0]
    for t in first.get("top_logprobs") or first.get("probs") or []:
        token = (t.get("token") or t.get("tok_str") or "").strip()
        value = t.get("logprob", t.get("prob"))
        if token in lp and value is not None:
            lp[token] = max(lp[token], value if "logprob" in t else math.log(max(value, 1e-30)))
    return lp


def number(text):
    """'12', '-3.5', '3/4', '12 cm', '$7$' -> float; anything else -> None."""
    m = re.match(r"^\s*\$?\s*([-+−]?\d+(?:[.,]\d+)?)(?:\s*/\s*(\d+))?\s*\$?\s*[^\d\s]{0,8}\s*$", str(text or ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", ".").replace("−", "-"))
    return v / float(m.group(2)) if m.group(2) and float(m.group(2)) else v


def is_safe(src):
    """Only plain computation: imports from a short list, no dunders, no files, no exec."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(n.split(".")[0] not in ALLOWED_IMPORTS for n in names):
                return False
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            return False
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return False
    return True


def run_program(reply, timeout=3.0):
    """Run the model's program in a separate, isolated Python. Returns (value or None, reason)."""
    fence = re.search(r"```(?:python|py)?\s*\n(.*?)(?:```|$)", reply, flags=re.S)
    src = (fence.group(1) if fence else reply).strip()
    if not src:
        return None, "empty"
    try:
        ast.parse(src)
    except SyntaxError:  # small models often write "=" for "==" in a condition: try that one repair
        fixed = re.sub(r"(?<![=!<>:+\-*/%])=(?!=)", "==", src)
        fixed = "\n".join(f if re.search(r"\bif\b|\bwhile\b", f) else o for f, o in zip(fixed.split("\n"), src.split("\n")))
        try:
            ast.parse(fixed)
            src = fixed
        except SyntaxError:
            pass
    if not is_safe(src):
        return None, "syntax or unsafe"
    env = {"PYTHONIOENCODING": "utf-8"}
    if os.name == "nt" and "SYSTEMROOT" in os.environ:  # Windows Python can't start without it
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    try:
        out = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True,
                             timeout=timeout, cwd=tempfile.gettempdir(), env=env)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    lines = out.stdout.strip().splitlines()
    if out.returncode != 0:
        return None, "crash"
    if not lines:
        return None, "no output"
    nums = re.findall(r"[-−]?\d+(?:\.\d+)?(?:/\d+)?", lines[-1])
    return (number(nums[-1]), "ok") if nums else (None, "not a number")


def matching_option(value, options):
    """The one option equal to value, or None (none or several match)."""
    hits = [k for k, v in (options or {}).items()
            if number(v) is not None and math.isclose(number(v), value, rel_tol=1e-6, abs_tol=1e-6)]
    return hits[0] if len(hits) == 1 else None


def solve_hybrid(problem, deadline, url=BASE_URL):
    """Fill and return a dict: answer, how ('letter' or 'code'), lp, code_value, code_reason.

    deadline is a time.perf_counter() value; every request is cut so we finish before it.
    The letter from step 1 is kept whatever happens in step 2.
    """
    out = {"how": "letter", "lp": None, "code_value": None, "code_reason": "", "prompt_tokens": 0}
    left = deadline - time.perf_counter()
    lp = letter_logprobs(chat_prompt(problem), timeout=max(left, 1.0), url=url)
    out.update(lp=lp, answer=max(lp, key=lp.get))

    if not problem.get("options"):  # options are pictures: nothing to compute against
        out["code_reason"] = "no text options"
        return out
    left = deadline - time.perf_counter()
    # The code prompt shares the problem text with step 1, so it reads only the new instruction (~2 s)
    budget = int((left - 4.0) * WRITE_TPS)
    if budget < 40:
        out["code_reason"] = "no time left"
        return out
    try:
        r = post(url + "/completion", {
            "prompt": chat_prompt(problem, CODE_INSTRUCTION), "n_predict": min(budget, 300), "temperature": 0,
            "seed": int(CONFIG["SEED"]), "cache_prompt": True,
            "t_max_predict_ms": int(max(left - 3.0, 1.0) * 1000),
        }, timeout=max(left - 1.0, 1.0))
    except Exception as error:  # timeout or server trouble: keep the letter from step 1
        out["code_reason"] = f"generation: {type(error).__name__}"
        return out
    out["prompt_tokens"] = r.get("timings", {}).get("prompt_n", 0)
    value, reason = run_program(r.get("content", ""), timeout=min(3.0, max(deadline - time.perf_counter() - 0.5, 0.2)))
    out.update(code_value=value, code_reason=reason)
    if value is not None:
        letter = matching_option(value, problem.get("options"))
        if letter:
            out.update(answer=letter, how="code")
        else:
            out["code_reason"] = "no option matches"
    return out


READ_TPS = float(CONFIG.get("READ_TOKENS_PER_SECOND", 11.1))
# Asked after the program, in the same conversation, so llama-server reads only these ~25 new tokens (~3.5 s
# on the board) instead of the whole problem again (~13 s): Qwen3.5 is a hybrid recurrent model, and its
# prompt cache can only be extended, not rewound to where two prompts start to differ.
LETTER_FOLLOW_UP = ("<|im_end|>\n<|im_start|>user\nWhich option is correct? Answer with the letter only.<|im_end|>\n"
                    "<|im_start|>assistant\n<think>\n\n</think>\n\n")
LETTER_RESERVE_S = 6.0  # kept for the letter follow-up and for running the program


def solve_code_first(problem, deadline, url=BASE_URL):
    """Program first, then the letter as a follow-up turn. Same return value as solve_hybrid.

    The program gets the ~13 s that reading the problem a second time used to cost on the board.
    If anything goes wrong before a letter exists, fall back to solve_hybrid's plain letter route.
    """
    if not problem.get("options"):  # options are pictures: nothing to compute against
        return solve_hybrid(problem, deadline, url=url)
    out = {"how": "letter", "lp": None, "code_value": None, "code_reason": "", "prompt_tokens": 0}
    prompt = chat_prompt(problem, CODE_INSTRUCTION)
    try:
        n_prompt = len(post(url + "/tokenize", {"content": prompt}, timeout=5).get("tokens", []))
        left = deadline - time.perf_counter()
        write_s = left - n_prompt / READ_TPS - LETTER_RESERVE_S
        if write_s < 5:  # a very long problem: no time to write a program
            return solve_hybrid(problem, deadline, url=url)
        r = post(url + "/completion", {
            "prompt": prompt, "n_predict": min(int(write_s * WRITE_TPS), 300), "temperature": 0,
            "seed": int(CONFIG["SEED"]), "cache_prompt": True, "t_max_predict_ms": int(write_s * 1000),
        }, timeout=max(deadline - time.perf_counter() - 2.0, 1.0))
    except Exception as error:  # noqa: BLE001 - timeout or server trouble: the plain letter route, if time allows
        out["code_reason"] = f"generation: {type(error).__name__}"
        if deadline - time.perf_counter() > 15:
            return solve_hybrid(problem, deadline, url=url)
        raise
    content = r.get("content", "")
    out["prompt_tokens"] = r.get("timings", {}).get("prompt_n", 0)
    lp = letter_logprobs(prompt + content + LETTER_FOLLOW_UP,
                         timeout=max(deadline + 8.0 - time.perf_counter(), 2.0), url=url)
    out.update(lp=lp, answer=max(lp, key=lp.get))
    value, reason = run_program(content, timeout=min(3.0, max(deadline + 5.0 - time.perf_counter(), 0.2)))
    out.update(code_value=value, code_reason=reason)
    if value is not None:
        letter = matching_option(value, problem.get("options"))
        if letter:
            out.update(answer=letter, how="code")
        else:
            out["code_reason"] = "no option matches"
    return out


# --- The maths model: Qwen2.5-Math 1.5B, fine-tuned by us to write short programs (see machine/NOTES_MATH.md) ---
MATH_URL = f"http://127.0.0.1:{CONFIG.get('MATH_PORT', '8084')}"
MATH_READ_TPS = float(CONFIG.get("MATH_READ_TOKENS_PER_SECOND", 5.1))
MATH_WRITE_TPS = float(CONFIG.get("MATH_WRITE_TOKENS_PER_SECOND", 3.0))
MATH_LETTER_S = 6.0  # kept for the letter question afterwards (it re-reads only its last ~20 tokens)


def math_prompt(problem, instruction, start=""):
    """Qwen2.5 chat format (no thinking block), exactly as in the fine-tuning data."""
    return ("<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n"
            f"{format_problem(problem)}{instruction}<|im_end|>\n<|im_start|>assistant\n{start}")


def math_server_up(url=MATH_URL):
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_math_server(wait_s=90):
    """Make sure the maths model's llama-server is running (it is not a systemd service). True when it's up.

    Started detached, so it stays up after predict.py ends and the next run finds it ready."""
    if math_server_up():
        return True
    binary = os.path.join(os.path.expanduser(CONFIG.get("LLAMA_CPP_DIR", "~/llama.cpp")), "build", "bin", "llama-server")
    model = os.path.join(os.path.expanduser(CONFIG.get("MODELS_DIR", "~/models")), CONFIG.get("MATH_MODEL_FILE", ""))
    if not (os.path.isfile(binary) and os.path.isfile(model)):
        print(f"maths model not started: missing {binary if not os.path.isfile(binary) else model}", file=sys.stderr)
        return False
    log = open(os.path.join(tempfile.gettempdir(), "math-llm.log"), "ab")
    subprocess.Popen([binary, "-m", model, "--host", "127.0.0.1", "--port", CONFIG.get("MATH_PORT", "8084"),
                      "--threads", CONFIG.get("LLM_THREADS", "4"), "--ctx-size", "4096", "--parallel", "1",
                      "--cache-ram", "0"], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    end = time.time() + wait_s
    while time.time() < end:
        if math_server_up():
            return True
        time.sleep(1)
    return False


ON_TEXT = None  # set by the web page to a function(text_so_far): shows the program while it is being written


def _complete(url, payload, until):
    """POST /completion, streamed, and stop reading at `until` (a time.perf_counter() value) whatever the
    server is doing: llama-server's own time limit only acts after a line break. Returns content, timings
    and whether the reply was cut. ON_TEXT, when set, is told the text as it grows."""
    request = urllib.request.Request(url + "/completion", json.dumps({**payload, "stream": True}).encode(),
                                     {"Content-Type": "application/json"})
    content, last, cut = "", {}, False
    with urllib.request.urlopen(request, timeout=max(until - time.perf_counter(), 1.0)) as reply:
        for line in reply:
            if line.startswith(b"data: "):
                last = json.loads(line[6:])
                content += last.get("content", "")
                if ON_TEXT is not None:
                    try:
                        ON_TEXT(content)
                    except Exception:  # noqa: BLE001 - showing progress must never break the answer
                        pass
            if time.perf_counter() > until and not last.get("stop"):
                cut = True
                break  # closing the connection makes the server stop writing
    return {"content": content, "timings": last.get("timings", {}), "cut": cut}


# In M3Kang, when the five options are numbers, the correct one is the smallest only 9% of the time and the
# largest 12% (the middle one 29%): wrong answers are written on both sides of the right one. The organisers'
# practice set does not show it (it changes nothing there), so the weight is low. 0 turns it off.
VALUE_RANK_PRIOR = (0.090, 0.229, 0.290, 0.273, 0.118)
MIDDLE_PRIOR_WEIGHT = float(CONFIG.get("MIDDLE_VALUE_PRIOR", "1.0"))


def with_value_prior(lp, options):
    """Letter log-probabilities plus the prior on where the correct value sits among numeric options."""
    values = {k: number(str(v)) for k, v in (options or {}).items()}
    if MIDDLE_PRIOR_WEIGHT <= 0 or sorted(values) != list(LETTERS) or None in values.values() or len(set(values.values())) < 5:
        return lp
    order = sorted(values, key=values.get)
    return {k: max(lp.get(k, -99.0), -20.0) + MIDDLE_PRIOR_WEIGHT * math.log(VALUE_RANK_PRIOR[order.index(k)]) for k in LETTERS}


def solve_math(problem, deadline, url=MATH_URL):
    """The maths model writes a short program, then gives its letter probabilities. Same return value as
    solve_hybrid. The program is asked first; the letter question shares the problem text, which a plain
    transformer's cache keeps, so it costs ~4 s. Any trouble before a letter exists -> solve_hybrid (0.8B)."""
    out = {"how": "letter", "lp": None, "code_value": None, "code_reason": "", "prompt_tokens": 0}
    content = ""
    if problem.get("options"):
        try:
            prompt = math_prompt(problem, CODE_INSTRUCTION, "```python\n")
            n_prompt = len(post(url + "/tokenize", {"content": prompt}, timeout=5).get("tokens", []))
            write_s = deadline - time.perf_counter() - n_prompt / MATH_READ_TPS - MATH_LETTER_S
            if write_s >= 4:
                r = _complete(url, {
                    "prompt": prompt, "n_predict": min(int(write_s * MATH_WRITE_TPS), 200), "temperature": 0,
                    "seed": int(CONFIG["SEED"]), "cache_prompt": True, "stop": ["```"],
                }, until=deadline - MATH_LETTER_S)
                out["prompt_tokens"] = r.get("timings", {}).get("prompt_n", 0)
                if r["cut"]:
                    out["code_reason"] = "no time left"
                else:
                    content = r["content"]
            else:
                out["code_reason"] = "no time left"
        except Exception as error:  # noqa: BLE001 - no program: the letter question below still answers
            out["code_reason"] = f"generation: {type(error).__name__}"
    else:
        out["code_reason"] = "no text options"
    try:
        lp = letter_logprobs(math_prompt(problem, "\nAnswer with the letter of the correct option only.",
                                         "The answer is "),
                             timeout=max(deadline + 7.0 - time.perf_counter(), 2.0), url=url)
        lp = with_value_prior(lp, problem.get("options"))
        out.update(lp=lp, answer=max(lp, key=lp.get))
    except Exception as error:  # noqa: BLE001 - the maths server is down or slow: the 0.8B route, if time allows
        if deadline - time.perf_counter() > 18:
            fallback = solve_hybrid(problem, deadline)
            fallback["code_reason"] = f"maths model failed ({type(error).__name__}); " + fallback.get("code_reason", "")
            return fallback
        raise
    if content:
        value, reason = run_program("```python\n" + content + "\n```",
                                    timeout=min(3.0, max(deadline + 5.0 - time.perf_counter(), 0.2)))
        out.update(code_value=value, code_reason=reason)
        if value is not None:
            letter = matching_option(value, problem.get("options"))
            if letter:
                out.update(answer=letter, how="code")
            else:
                out["code_reason"] = "no option matches"
    return out


def hungarian(cost):
    """Minimum-cost assignment of every row to a different column (rows <= columns). Pure Python, O(n^2 m)."""
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    rows = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            rows[p[j] - 1] = j - 1
    return rows


def balance(results):
    """Re-assign the 'letter' answers so each letter is used about n/5 times over the batch.

    results: list of dicts with answer, how and lp. Answers with how == 'code' (or without lp) stay.
    Returns the list of balanced letters, in the same order.
    """
    n = len(results)
    final = [r["answer"] for r in results]
    free = [i for i, r in enumerate(results) if r.get("how") == "letter" and r.get("lp")]
    if len(free) < 2:
        return final
    quota = {c: -(-n // 5) for c in LETTERS}  # ceil(n/5) per letter
    for i, r in enumerate(results):
        if i not in free and r["answer"] in quota:
            quota[r["answer"]] = max(0, quota[r["answer"]] - 1)
    slots = [c for c in LETTERS for _ in range(quota[c])]
    while len(slots) < len(free):  # the fixed answers used up the quotas: allow extra slots
        slots += list(LETTERS)
    cost = [[-max(results[i]["lp"].get(c, -99.0), -99.0) for c in slots] for i in free]
    for i, j in zip(free, hungarian(cost)):
        final[i] = slots[j]
    return final
