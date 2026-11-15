"""Convert M3Kang problem images into JSON/JSONL using enhanced multi-engine OCR & VLM vision.

Addresses common M3Kang OCR failures:
  - Visual options (shapes, graphs, figures) via visual-option detection & VLM fallback
  - Garbled fractions/formulas (e.g. 1/2 read as 12) via 3x upscaling & 2D column fraction reconstruction
  - Duplicate options via high-contrast retry & strict uniqueness validation
  - Dates (e.g. 11/10/2020) via slash preservation and DD/MM/YYYY repair

Usage:
    python image_to_json.py --ocr-type rapidocr-enhanced
    python image_to_json.py --ocr-type hybrid --vlm-url http://127.0.0.1:8083
    python image_to_json.py --update-jsonl ../data/val.jsonl --only-empty-options --ocr-type hybrid
    python image_to_json.py --image path/to/problem.png --ocr-type rapidocr-enhanced
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

LETTERS = "ABCDE"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
OCR_TYPES = (
    "rapidocr-enhanced",
    "rapidocr",
    "paddleocr",
    "easyocr",
    "tesseract",
    "vlm",
    "hybrid",
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
DEFAULT_IMAGES_DIR = os.path.join(DEFAULT_DATA_DIR, "images")
DEFAULT_OUT_FILE = os.path.join(DEFAULT_DATA_DIR, "ocr_problems.jsonl")

FILENAME_RE = re.compile(
    r"^(?P<id>lvl-(?P<level>\d+)_(?P<year>\d{4})_(?P<num>[^_]+))_(?P<language>[a-z]{2,3})$",
    re.IGNORECASE,
)

MARKER = re.compile(r"^\s*[\(\[]?([A-E])\s*([\)）\]:.]?)\s*(.*)$")

UNICODE_FRACTIONS = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--ocr-type",
        default="rapidocr-enhanced",
        choices=OCR_TYPES,
        help=(
            "OCR / vision backend to use (default: rapidocr-enhanced). "
            "Use 'hybrid' to combine enhanced OCR with VLM fallback for pictures/formulas."
        ),
    )
    p.add_argument(
        "--vlm-url",
        default="http://127.0.0.1:8083",
        help="OpenAI-compatible VLM server URL for --ocr-type vlm or hybrid (default: http://127.0.0.1:8083)",
    )
    p.add_argument(
        "--vlm-timeout",
        type=int,
        default=60,
        help="timeout in seconds per VLM request (default: 60)",
    )
    p.add_argument(
        "--images-dir",
        default=DEFAULT_IMAGES_DIR,
        help="folder containing problem images (default: ..\\data\\images)",
    )
    p.add_argument(
        "--image",
        default="",
        help="process a single image file instead of scanning --images-dir",
    )
    p.add_argument(
        "--out",
        default=DEFAULT_OUT_FILE,
        help="output .jsonl or .json path (default: ..\\data\\ocr_problems.jsonl)",
    )
    p.add_argument(
        "--update-jsonl",
        default="",
        help="existing JSONL file (e.g. ..\\data\\val.jsonl) to enrich with OCR options from --images-dir",
    )
    p.add_argument(
        "--only-empty-options",
        action="store_true",
        help="with --update-jsonl, only run OCR on rows that currently have empty options",
    )
    p.add_argument(
        "--languages",
        default="",
        help="optional comma-separated language filter, e.g. eng,cat",
    )
    p.add_argument(
        "--default-language",
        default="eng",
        help="fallback language if filename does not end with _<lang> (default: eng)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore .ocr_cache.jsonl and re-run OCR on every image",
    )
    p.add_argument(
        "--save-option-crops",
        action="store_true",
        help="save bottom option-strip crops for problems whose options are visual or empty",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="only process the first N images/records",
    )
    return p.parse_args()


def normalize_math_text(text):
    """Clean OCR noise in fractions, formulas, operators, and dates."""
    if not text:
        return ""
    s = str(text).strip()
    for uf, ascii_frac in UNICODE_FRACTIONS.items():
        s = s.replace(uf, f" {ascii_frac} ")

    s = (
        s.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("⁄", "/")
        .replace("∕", "/")
    )
    s = re.sub(r"(?<=\d)\s*[\|lI]\s*(?=\d)", "/", s)
    s = re.sub(r"\s*/\s*", "/", s)

    def _repair_date(m):
        d, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= yr <= 2100:
            return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        return m.group(0)

    s = re.sub(r"\b(\d{1,2})\s+(\d{1,2})\s+((?:19|20)\d{2})\b", _repair_date, s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def options_are_valid(options):
    """Return True if options has all 5 non-empty, non-duplicate values."""
    if not isinstance(options, dict) or len(options) != 5:
        return False
    vals = [str(options.get(l, "")).strip() for l in LETTERS]
    if not all(vals):
        return False
    normalized_vals = [v.lower().replace(" ", "") for v in vals]
    if len(set(normalized_vals)) < 5:
        return False
    return True


def _preprocess_bytes(img_bytes, scale=2.5, crop_bottom_ratio=0.0, binarize=False, pad=24):
    """Upscale, optionally crop bottom options band, enhance contrast, and pad."""
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError:
        return img_bytes, 0

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    crop_y = 0
    if 0.0 < crop_bottom_ratio < 1.0:
        crop_y = int(h * (1.0 - crop_bottom_ratio))
        img = img.crop((0, crop_y, w, h))
        w, h = img.size

    if scale and scale != 1.0:
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
        img = img.resize((new_w, new_h), resample=resample)

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Sharpness(gray).enhance(1.6)
    if binarize:
        gray = gray.point(lambda p: 255 if p > 175 else 0)

    rgb = gray.convert("RGB")
    if pad > 0:
        rgb = ImageOps.expand(rgb, border=pad, fill=(255, 255, 255))

    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    return buf.getvalue(), crop_y


def _boxes_to_items(boxes):
    items = []
    for box, text, score in boxes:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        items.append({
            "x0": x0,
            "x1": x1,
            "y0": y0,
            "y1": y1,
            "x": x0,
            "cx": (x0 + x1) / 2.0,
            "y": (y0 + y1) / 2.0,
            "w": max(1.0, x1 - x0),
            "h": max(1.0, y1 - y0),
            "text": str(text).strip(),
            "score": float(score) if score is not None else 1.0,
        })
    return items


def group_rows(boxes):
    """Group OCR boxes into horizontal rows (top to bottom), sorted left to right."""
    items = _boxes_to_items(boxes)
    items.sort(key=lambda it: it["y"])
    rows, current = [], []
    for it in items:
        if current and abs(it["y"] - current[-1]["y"]) > 0.6 * max(it["h"], current[-1]["h"]):
            rows.append(current)
            current = []
        current.append(it)
    if current:
        rows.append(current)
    return [sorted(row, key=lambda it: it["x"]) for row in rows]


def reading_order(boxes):
    """Sort OCR boxes into rows (top to bottom), then left to right."""
    return [it for row in group_rows(boxes) for it in row]


def is_marker(text, letter, strict):
    m = MARKER.match(text)
    if not m or m.group(1) != letter:
        return None
    paren, rest = m.group(2), m.group(3)
    if paren:
        return rest
    if strict:
        return None
    if rest == "" or re.match(r"^[-+−\d/]", rest):
        return rest
    return None


def parse_options_with_start(boxes):
    """Baseline linear parser: return (options_dict, start_item_index, saw_five_markers)."""
    items = reading_order(boxes)
    starts = [i for i, it in enumerate(items) if is_marker(it["text"], "A", strict=True) is not None]
    saw_five = False
    for start in reversed(starts):
        options, current, i = {}, None, start
        expected = iter(LETTERS)
        letter = next(expected)
        while i < len(items):
            text = items[i]["text"]
            rest = is_marker(text, letter, strict=(letter == "A")) if letter else None
            if rest is not None:
                current = letter
                options[current] = rest
                letter = next(expected, None)
            elif current:
                options[current] = (options[current] + " " + text).strip()
            i += 1
        if len(options) == 5:
            saw_five = True
            cleaned = {k: normalize_math_text(v.lstrip(")）] ").strip()) for k, v in options.items()}
            if options_are_valid(cleaned):
                return cleaned, start, True
            return {}, start, True
    return {}, len(items), saw_five


def _reconstruct_slot_tokens(tokens):
    """Assemble tokens inside a single option slot (A..E), reconstructing vertical fractions."""
    if not tokens:
        return ""
    if len(tokens) == 1:
        return normalize_math_text(tokens[0]["text"])

    by_y = sorted(tokens, key=lambda t: (t["y"], t["x0"]))
    used = [False] * len(by_y)
    parts = []

    for i, top in enumerate(by_y):
        if used[i]:
            continue
        best_j = None
        for j in range(i + 1, len(by_y)):
            if used[j]:
                continue
            bot = by_y[j]
            dy = bot["y"] - top["y"]
            if dy < 0.35 * min(top["h"], bot["h"]) or dy > 2.8 * max(top["h"], bot["h"]):
                continue
            x_overlap = min(top["x1"], bot["x1"]) - max(top["x0"], bot["x0"])
            horiz_close = abs(top["cx"] - bot["cx"]) <= max(top["w"], bot["w"]) * 0.9
            if (x_overlap > 0 or horiz_close) and re.match(r"^[+-]?\d+$", top["text"]) and re.match(r"^\d+$", bot["text"]):
                best_j = j
                break

        if best_j is not None:
            used[i] = True
            used[best_j] = True
            parts.append((top["x0"], f"{top['text']}/{by_y[best_j]['text']}"))
        else:
            used[i] = True
            parts.append((top["x0"], top["text"]))

    parts.sort(key=lambda p: p[0])
    return normalize_math_text(" ".join(p[1] for p in parts))


def parse_options_spatial(boxes):
    """2D column-aware parser for options A..E (handles 1-row, 2-row, vertical, and stacked fractions)."""
    items = _boxes_to_items(boxes)
    if not items:
        return {}, False

    candidates_by_letter = {l: [] for l in LETTERS}
    for idx, it in enumerate(items):
        m = MARKER.match(it["text"])
        if not m:
            continue
        letter, punct, rest = m.group(1), m.group(2), m.group(3)
        if punct or rest == "" or re.match(r"^[-+−\d/]", rest):
            candidates_by_letter[letter].append((idx, it, punct, rest))

    if not all(candidates_by_letter[l] for l in LETTERS):
        return {}, False

    best_markers = None
    for _, a_it, a_punct, a_rest in reversed(candidates_by_letter["A"]):
        if not a_punct:
            continue
        seq = {"A": (a_it, a_rest)}
        prev = a_it
        ok = True
        for letter in "BCDE":
            valid_next = [
                (it, rest)
                for _, it, punct, rest in candidates_by_letter[letter]
                if (punct or rest == "" or re.match(r"^[-+−\d/]", rest))
                and it["y"] >= prev["y"] - prev["h"] * 0.75
                and not (abs(it["y"] - prev["y"]) <= prev["h"] * 0.75 and it["x0"] <= prev["x0"])
            ]
            if not valid_next:
                ok = False
                break
            valid_next.sort(key=lambda pair: (round(pair[0]["y"] / max(prev["h"], 1.0)), pair[0]["x0"]))
            seq[letter] = valid_next[0]
            prev = valid_next[0][0]
        if ok:
            best_markers = seq
            break

    if not best_markers:
        return {}, False

    marker_ids = {id(best_markers[l][0]) for l in LETTERS}
    min_marker_y = min(best_markers[l][0]["y0"] for l in LETTERS)

    ordered_markers = [(l, best_markers[l][0], best_markers[l][1]) for l in LETTERS]
    visual_rows = []
    for entry in ordered_markers:
        if not visual_rows:
            visual_rows.append([entry])
        else:
            ref_m = visual_rows[-1][-1][1]
            if abs(entry[1]["y"] - ref_m["y"]) <= max(entry[1]["h"], ref_m["h"]) * 0.95:
                visual_rows[-1].append(entry)
            else:
                visual_rows.append([entry])

    slots = {}
    for r_idx, row in enumerate(visual_rows):
        row.sort(key=lambda e: e[1]["x0"])
        row_y_center = sum(e[1]["y"] for e in row) / len(row)
        row_h = max(e[1]["h"] for e in row)
        y_top = (
            min_marker_y - row_h * 0.9
            if r_idx == 0
            else (sum(e[1]["y"] for e in visual_rows[r_idx - 1]) / len(visual_rows[r_idx - 1]) + row_y_center) / 2.0
        )
        y_bot = (
            float("inf")
            if r_idx == len(visual_rows) - 1
            else (row_y_center + sum(e[1]["y"] for e in visual_rows[r_idx + 1]) / len(visual_rows[r_idx + 1])) / 2.0
        )
        for c_idx, (letter, m_it, inline_rest) in enumerate(row):
            x_left = m_it["x0"] - m_it["w"] * 0.25
            x_right = row[c_idx + 1][1]["x0"] - 2.0 if c_idx + 1 < len(row) else float("inf")
            slots[letter] = {
                "x0": x_left,
                "x1": x_right,
                "y0": y_top,
                "y1": y_bot,
                "inline": inline_rest.lstrip(")）] ").strip(),
                "tokens": [],
            }

    for it in items:
        if id(it) in marker_ids:
            continue
        if it["y"] < min_marker_y - it["h"] * 0.8:
            continue
        for letter in LETTERS:
            sl = slots[letter]
            if sl["x0"] <= it["cx"] < sl["x1"] and sl["y0"] <= it["y"] < sl["y1"]:
                sl["tokens"].append(it)
                break

    options = {}
    for letter in LETTERS:
        sl = slots[letter]
        extra = _reconstruct_slot_tokens(sl["tokens"])
        combined = " ".join(p for p in (sl["inline"], extra) if p).strip()
        options[letter] = normalize_math_text(combined)

    return options, True


def extract_text_and_options(boxes):
    """Extract both statement text (above options) and A..E options."""
    rows = group_rows(boxes)
    items = [it for row in rows for it in row]
    linear_opts, start_idx, saw_five_linear = parse_options_with_start(boxes)
    spatial_opts, saw_five_spatial = parse_options_spatial(boxes)

    options = spatial_opts if options_are_valid(spatial_opts) else linear_opts
    saw_five = saw_five_spatial or saw_five_linear

    item_to_row = {}
    flat_idx = 0
    for row_idx, row in enumerate(rows):
        for _ in row:
            item_to_row[flat_idx] = row_idx
            flat_idx += 1

    statement_rows = {}
    for idx in range(start_idx):
        r_idx = item_to_row[idx]
        statement_rows.setdefault(r_idx, []).append(items[idx]["text"].strip())

    lines = [" ".join(tok for tok in statement_rows[r] if tok) for r in sorted(statement_rows)]
    text = "\n".join(line for line in lines if line).strip()
    return text, options, saw_five


class ImageOptionReader:
    """Unified image reader supporting multiple OCR engines and VLM vision fallback."""

    def __init__(self, ocr_type="rapidocr-enhanced", vlm_url="http://127.0.0.1:8083", vlm_timeout=60):
        self.ocr_type = ocr_type
        self.vlm_url = vlm_url.rstrip("/")
        self.vlm_timeout = vlm_timeout
        self._rapid = None
        self._paddle = None
        self._easy = None
        self._tesseract = None

    def _get_rapid(self):
        if self._rapid is None:
            from rapidocr_onnxruntime import RapidOCR
            self._rapid = RapidOCR()
        return self._rapid

    def _get_paddle(self):
        if self._paddle is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise SystemExit("PaddleOCR not installed. Install with: pip install paddleocr paddlepaddle") from exc
            self._paddle = PaddleOCR(use_angle_cls=True, show_log=False)
        return self._paddle

    def _get_easy(self):
        if self._easy is None:
            try:
                import easyocr
            except ImportError as exc:
                raise SystemExit("EasyOCR not installed. Install with: pip install easyocr") from exc
            self._easy = easyocr.Reader(["en", "es"], gpu=False, verbose=False)
        return self._easy

    def _get_tesseract(self):
        if self._tesseract is None:
            try:
                import pytesseract
            except ImportError as exc:
                raise SystemExit("pytesseract not installed. Install with: pip install pytesseract") from exc
            self._tesseract = pytesseract
        return self._tesseract

    def _detect_boxes(self, img_bytes, backend):
        """Return standard [(box_4pts, text, score), ...] list for the requested OCR engine."""
        if backend in ("rapidocr", "rapidocr-enhanced"):
            ocr = self._get_rapid()
            boxes, _ = ocr(img_bytes)
            return boxes or []

        if backend == "paddleocr":
            import numpy as np
            from PIL import Image
            arr = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
            res = self._get_paddle().ocr(arr, cls=True)
            boxes = []
            for page in res or []:
                for line in page or []:
                    boxes.append((line[0], line[1][0], line[1][1]))
            return boxes

        if backend == "easyocr":
            import numpy as np
            from PIL import Image
            arr = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
            res = self._get_easy().readtext(arr)
            return [(box, text, score) for box, text, score in (res or [])]

        if backend == "tesseract":
            from PIL import Image
            pytesseract = self._get_tesseract()
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            data = pytesseract.image_to_data(img, config="--psm 6", output_type=pytesseract.Output.DICT)
            boxes = []
            for i, txt in enumerate(data.get("text", [])):
                txt = str(txt).strip()
                if not txt:
                    continue
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                conf = float(data["conf"][i]) if str(data["conf"][i]) != "-1" else 0.0
                box = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
                boxes.append((box, txt, conf / 100.0))
            return boxes

        raise ValueError(f"Unsupported OCR backend: {backend}")

    def _query_vlm(self, img_bytes):
        """Query local multimodal server (e.g. Qwen3.5-0.8B + mmproj) to extract options A..E."""
        b64 = base64.b64encode(img_bytes).decode("ascii")
        prompt = (
            "Look at this math competition problem image. Extract the five answer options A, B, C, D, and E "
            "at the bottom. If options are numbers, fractions (like 1/2), formulas, or dates (like 11/10/2020), "
            "write their exact text. If options are pictures, shapes, clocks, or graphs, briefly describe each "
            "option A to E in 2-5 words so they can be distinguished. "
            'Reply ONLY with valid JSON: {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}'
        )
        payload = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 220,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.vlm_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.vlm_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            m = re.search(r"\{[\s\S]*\}", content)
            if not m:
                return {}
            parsed = json.loads(m.group(0))
            cleaned = {
                l: normalize_math_text(str(parsed.get(l, "")).strip())
                for l in LETTERS
            }
            return cleaned if options_are_valid(cleaned) else {}
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"  [VLM warning] {exc}", file=sys.stderr, flush=True)
            return {}

    def read_image(self, img_bytes):
        """Return dict: {'text': str, 'options': dict, 'options_type': 'text'|'visual'|'empty', 'crop_bytes': bytes|None}."""
        if self.ocr_type == "rapidocr":
            boxes = self._detect_boxes(img_bytes, "rapidocr")
            text, options, saw_five = extract_text_and_options(boxes)
            opt_type = "text" if options else ("visual" if saw_five else "empty")
            return {"text": text, "options": options, "options_type": opt_type, "crop_bytes": None}

        if self.ocr_type == "vlm":
            text = ""
            try:
                boxes = self._detect_boxes(img_bytes, "rapidocr")
                text, _, _ = extract_text_and_options(boxes)
            except Exception:
                pass
            vlm_opts = self._query_vlm(img_bytes)
            opt_type = "vlm" if vlm_opts else "empty"
            return {"text": text, "options": vlm_opts, "options_type": opt_type, "crop_bytes": None}

        backend = "rapidocr-enhanced" if self.ocr_type == "hybrid" else self.ocr_type

        full_scaled, _ = _preprocess_bytes(img_bytes, scale=2.0, crop_bottom_ratio=0.0, binarize=False, pad=20)
        full_boxes = self._detect_boxes(full_scaled, backend)
        text, options, saw_five = extract_text_and_options(full_boxes)

        crop_bytes, _ = _preprocess_bytes(img_bytes, scale=3.0, crop_bottom_ratio=0.45, binarize=False, pad=28)
        if not options_are_valid(options):
            crop_boxes = self._detect_boxes(crop_bytes, backend)
            crop_opts, saw_five_crop = parse_options_spatial(crop_boxes)
            if not options_are_valid(crop_opts):
                crop_opts, _, saw_five_linear = parse_options_with_start(crop_boxes)
                saw_five_crop = saw_five_crop or saw_five_linear
            saw_five = saw_five or saw_five_crop
            if options_are_valid(crop_opts):
                options = crop_opts

        if not options_are_valid(options):
            bin_crop, _ = _preprocess_bytes(img_bytes, scale=3.2, crop_bottom_ratio=0.45, binarize=True, pad=28)
            bin_boxes = self._detect_boxes(bin_crop, backend)
            bin_opts, _ = parse_options_spatial(bin_boxes)
            if not options_are_valid(bin_opts):
                bin_opts, _, _ = parse_options_with_start(bin_boxes)
            if options_are_valid(bin_opts):
                options = bin_opts

        if not options_are_valid(options) and self.ocr_type == "hybrid":
            vlm_opts = self._query_vlm(img_bytes)
            if options_are_valid(vlm_opts):
                return {"text": text, "options": vlm_opts, "options_type": "vlm", "crop_bytes": crop_bytes}

        if options_are_valid(options):
            return {"text": text, "options": options, "options_type": "text", "crop_bytes": None}

        opt_type = "visual" if saw_five else "empty"
        return {"text": text, "options": {}, "options_type": opt_type, "crop_bytes": crop_bytes}


def parse_filename(filename, default_language="eng"):
    """Extract id, language, level, and year from <id>_<language>.png."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = FILENAME_RE.match(stem)
    if m:
        return {
            "id": m.group("id"),
            "language": m.group("language").lower(),
            "level": int(m.group("level")),
            "year": int(m.group("year")),
        }
    if "_" in stem:
        maybe_id, maybe_lang = stem.rsplit("_", 1)
        if 2 <= len(maybe_lang) <= 3 and maybe_lang.isalpha():
            parts = maybe_id.split("_")
            level = int(parts[0].replace("lvl-", "")) if parts[0].startswith("lvl-") and parts[0][4:].isdigit() else 0
            year = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            return {
                "id": maybe_id,
                "language": maybe_lang.lower(),
                "level": level,
                "year": year,
            }
    return {
        "id": stem,
        "language": default_language,
        "level": 0,
        "year": None,
    }


def load_cache(cache_path):
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    cache[row["key"]] = {
                        "options": row.get("options", {}),
                        "text": row.get("text", ""),
                        "options_type": row.get("options_type", "text" if row.get("options") else "empty"),
                    }
    return cache


def write_records(records, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if out_path.lower().endswith(".json"):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_ocr_on_image(reader, img_path, crops_dir=None, crop_name=None):
    with open(img_path, "rb") as f:
        img_bytes = f.read()
    res = reader.read_image(img_bytes)
    if crops_dir and crop_name and not res["options"] and res.get("crop_bytes"):
        os.makedirs(crops_dir, exist_ok=True)
        with open(os.path.join(crops_dir, crop_name), "wb") as cf:
            cf.write(res["crop_bytes"])
    return res["text"], res["options"], res["options_type"]


def main():
    args = parse_args()
    languages = {l.strip().lower() for l in args.languages.split(",") if l.strip()}
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)

    crops_dir = os.path.join(out_dir, "option_crops") if args.save_option_crops else None
    cache_path = os.path.join(out_dir, ".ocr_cache.jsonl")
    cache = {} if args.no_cache else load_cache(cache_path)
    cache_file = open(cache_path, "a", encoding="utf-8")

    reader = ImageOptionReader(
        ocr_type=args.ocr_type,
        vlm_url=args.vlm_url,
        vlm_timeout=args.vlm_timeout,
    )
    records = []
    t0 = time.time()

    if args.update_jsonl:
        if not os.path.exists(args.update_jsonl):
            sys.exit(f"Input JSONL not found: {args.update_jsonl}")
        with open(args.update_jsonl, encoding="utf-8") as f:
            source_rows = [json.loads(line) for line in f if line.strip()]

        missing_images = 0
        for row in source_rows:
            if args.limit and len(records) >= args.limit:
                break
            if languages and row.get("language", "").lower() not in languages:
                continue

            cache_key = f"{row['id']}|{row['language']}|{args.ocr_type}"
            img_filename = f"{row['id']}_{row['language']}.png"
            img_path = os.path.join(args.images_dir, img_filename)

            if args.only_empty_options and options_are_valid(row.get("options")):
                records.append(row)
                continue

            if cache_key in cache and not args.no_cache:
                options = cache[cache_key]["options"]
                ocr_text = cache[cache_key]["text"]
                options_type = cache[cache_key]["options_type"]
            elif os.path.exists(img_path):
                ocr_text, options, options_type = run_ocr_on_image(
                    reader, img_path, crops_dir=crops_dir, crop_name=img_filename
                )
                cache[cache_key] = {"options": options, "text": ocr_text, "options_type": options_type}
                cache_file.write(
                    json.dumps(
                        {"key": cache_key, "options": options, "text": ocr_text, "options_type": options_type},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            else:
                missing_images += 1
                options = row.get("options", {})
                ocr_text = ""
                options_type = "text" if options else "empty"

            updated = dict(row)
            updated["options"] = options
            updated["options_type"] = options_type
            if not updated.get("text") and ocr_text:
                updated["text"] = ocr_text
            records.append(updated)

            if len(records) % 100 == 0:
                rate = len(records) / max(time.time() - t0, 1e-6)
                print(f"  [{args.ocr_type}] {len(records)} rows processed, {rate:.1f} rows/s", flush=True)

        cache_file.close()
        out_path = args.out if args.out != DEFAULT_OUT_FILE else args.update_jsonl
        write_records(records, out_path)
        report(records, out_path, args.ocr_type, missing_images)
        return

    if args.image:
        if not os.path.exists(args.image):
            sys.exit(f"Image not found: {args.image}")
        image_paths = [args.image]
    else:
        if not os.path.isdir(args.images_dir):
            sys.exit(f"Images directory not found: {args.images_dir}")
        image_paths = [
            os.path.join(args.images_dir, name)
            for name in sorted(os.listdir(args.images_dir))
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS
        ]

    for img_path in image_paths:
        if args.limit and len(records) >= args.limit:
            break
        meta = parse_filename(img_path, default_language=args.default_language)
        if languages and meta["language"] not in languages:
            continue

        cache_key = f"{meta['id']}|{meta['language']}|{args.ocr_type}"
        if cache_key in cache and not args.no_cache:
            options = cache[cache_key]["options"]
            text = cache[cache_key]["text"]
            options_type = cache[cache_key]["options_type"]
        else:
            text, options, options_type = run_ocr_on_image(
                reader, img_path, crops_dir=crops_dir, crop_name=os.path.basename(img_path)
            )
            cache[cache_key] = {"options": options, "text": text, "options_type": options_type}
            cache_file.write(
                json.dumps(
                    {"key": cache_key, "options": options, "text": text, "options_type": options_type},
                    ensure_ascii=False,
                )
                + "\n"
            )

        rec = {
            "id": meta["id"],
            "language": meta["language"],
            "level": meta["level"],
        }
        if meta["year"] is not None:
            rec["year"] = meta["year"]
        rec.update({
            "text_only": bool(options) and options_type == "text",
            "options_type": options_type,
            "text": text,
            "options": options,
            "label": "",
        })
        records.append(rec)

        if len(records) % 100 == 0:
            rate = len(records) / max(time.time() - t0, 1e-6)
            print(f"  [{args.ocr_type}] {len(records)} images processed, {rate:.1f} img/s", flush=True)

    cache_file.close()
    write_records(records, args.out)
    report(records, args.out, args.ocr_type, missing_images=0)


def report(records, out_path, ocr_type, missing_images):
    if not records:
        sys.exit("No images/records matched. Check --images-dir or --languages.")
    by_lang = Counter(r.get("language", "?") for r in records)
    by_opt_type = Counter(r.get("options_type", "text" if r.get("options") else "empty") for r in records)
    with_options = sum(1 for r in records if r.get("options"))
    print()
    print(f"Wrote {len(records)} records to {os.path.abspath(out_path)} (ocr-type: {ocr_type})")
    for lang, n in sorted(by_lang.items()):
        print(f"  {lang}: {n}")
    print(f"Options read from image: {with_options}/{len(records)} ({100 * with_options / len(records):.0f}%)")
    print(f"  breakdown: {dict(by_opt_type)}")
    if missing_images:
        print(f"Missing image files: {missing_images}")


if __name__ == "__main__":
    main()