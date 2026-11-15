"""Convert a single M3Kang problem image into a JSONL record using RapidOCR.

Usage:
    python problem_to_jsonl.py --image ../data/images/lvl-7_2024_23_eng.png --out output.jsonl
    python problem_to_jsonl.py --image ../data/images/lvl-7_2024_17_cat.png --out output.jsonl --append
"""
import argparse
import json
import os
import re
import sys

LETTERS = "ABCDE"

FILENAME_RE = re.compile(
    r"^(?P<id>lvl-(?P<level>\d+)_(?P<year>\d{4})_(?P<num>[^_]+))_(?P<language>[a-z]{2,3})$",
    re.IGNORECASE,
)

MARKER_RE = re.compile(r"^\s*([A-E])\s*([\)）\]:.]?)\s*(.*)$")
PURE_SYMBOL_RE = re.compile(r"^[\W\d_]+$")


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to the input problem image",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to the output .jsonl file",
    )
    parser.add_argument(
        "--default-language",
        default="eng",
        help="Fallback language if filename does not end with _<lang> (default: eng)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append record to --out instead of overwriting the file",
    )
    return parser.parse_args()


def parse_filename(image_path, default_language="eng"):
    """Extract id, language, level, and year from <id>_<language>.<ext>."""
    stem = os.path.splitext(os.path.basename(image_path))[0]
    match = FILENAME_RE.match(stem)
    if match:
        return {
            "id": match.group("id"),
            "language": match.group("language").lower(),
            "level": int(match.group("level")),
            "year": int(match.group("year")),
        }

    if "_" in stem:
        maybe_id, maybe_lang = stem.rsplit("_", 1)
        if 2 <= len(maybe_lang) <= 3 and maybe_lang.isalpha():
            parts = maybe_id.split("_")
            level = (
                int(parts[0].replace("lvl-", ""))
                if parts[0].startswith("lvl-") and parts[0][4:].isdigit()
                else 0
            )
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


def build_items(boxes):
    """Convert raw RapidOCR boxes into normalized geometry dictionaries."""
    items = []
    for idx, (box, text, _score) in enumerate(boxes):
        cleaned = text.strip()
        if not cleaned:
            continue
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        items.append({
            "idx": idx,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "xc": 0.5 * (x1 + x2),
            "yc": 0.5 * (y1 + y2),
            "w": max(x2 - x1, 1.0),
            "h": max(y2 - y1, 1.0),
            "text": cleaned,
        })
    return items


def is_marker(text, letter, strict):
    """Check if text starts with an option marker (A..E) and return trailing text."""
    match = MARKER_RE.match(text)
    if not match or match.group(1) != letter:
        return None
    punct, rest = match.group(2), match.group(3)
    if punct:
        return rest.strip()
    if strict:
        return None
    if rest == "" or re.match(r"^[-+−\d]", rest):
        return rest.strip()
    return None


def median(values, default=16.0):
    if not values:
        return default
    s = sorted(values)
    return s[len(s) // 2]


def join_option_fragments(fragments):
    """Join OCR fragments inside a single option cell (handles 2-line fractions)."""
    if not fragments:
        return ""
    med_h = median([f["h"] for f in fragments])
    ordered = sorted(fragments, key=lambda f: (f["yc"], f["x1"]))

    rows = []
    for frag in ordered:
        if rows and abs(frag["yc"] - rows[-1][-1]["yc"]) <= 0.65 * med_h:
            rows[-1].append(frag)
        else:
            rows.append([frag])

    line_texts = []
    for row in rows:
        row.sort(key=lambda f: f["x1"])
        line_texts.append(" ".join(f["text"] for f in row if f["text"]).strip())

    line_texts = [t for t in line_texts if t]
    if len(line_texts) == 2:
        return f"{line_texts[0]} / {line_texts[1]}"
    return " ".join(line_texts).strip()


def find_option_markers(items):
    """Locate the A..E marker items in either horizontal or vertical layout."""
    a_candidates = [
        it for it in items if is_marker(it["text"], "A", strict=True) is not None
    ]
    a_candidates.sort(key=lambda it: it["yc"], reverse=True)

    for a_item in a_candidates:
        h_ref = a_item["h"]

        # Try horizontal alignment first (all A..E on roughly the same Y band)
        horiz = [a_item]
        for letter in LETTERS[1:]:
            prev = horiz[-1]
            matches = [
                it for it in items
                if it["idx"] != prev["idx"]
                and it["x1"] > prev["x1"]
                and abs(it["yc"] - a_item["yc"]) <= 1.8 * h_ref
                and is_marker(it["text"], letter, strict=False) is not None
            ]
            if not matches:
                break
            matches.sort(key=lambda it: it["x1"])
            horiz.append(matches[0])

        if len(horiz) == 5:
            return horiz, "horizontal"

        # Try vertical alignment (A..E stacked in a column)
        vert = [a_item]
        for letter in LETTERS[1:]:
            prev = vert[-1]
            matches = [
                it for it in items
                if it["idx"] != prev["idx"]
                and it["y1"] > prev["y1"]
                and abs(it["x1"] - a_item["x1"]) <= 2.5 * h_ref
                and is_marker(it["text"], letter, strict=False) is not None
            ]
            if not matches:
                break
            matches.sort(key=lambda it: it["y1"])
            vert.append(matches[0])

        if len(vert) == 5:
            return vert, "vertical"

    return None, None


def extract_options(items):
    """Extract options A..E and return (options_dict, options_top_y)."""
    markers, layout = find_option_markers(items)
    if not markers:
        return {}, float("inf")

    med_h = median([m["h"] for m in markers])
    marker_indices = {m["idx"] for m in markers}
    options = {}

    if layout == "horizontal":
        y_top = min(m["y1"] for m in markers) - 1.6 * med_h
        for i, letter in enumerate(LETTERS):
            m = markers[i]
            x_left = m["x1"]
            x_right = markers[i + 1]["x1"] if i + 1 < 5 else float("inf")

            fragments = []
            inline_rest = is_marker(m["text"], letter, strict=(letter == "A"))
            if inline_rest:
                fragments.append({
                    "x1": m["x1"],
                    "yc": m["yc"],
                    "h": m["h"],
                    "text": inline_rest.lstrip(")）] ").strip(),
                })

            for it in items:
                if it["idx"] in marker_indices:
                    continue
                if it["yc"] >= y_top and x_left <= it["xc"] < x_right:
                    fragments.append(it)

            options[letter] = join_option_fragments(fragments)

    else:  # vertical layout
        y_top = markers[0]["y1"] - 1.2 * med_h
        for i, letter in enumerate(LETTERS):
            m = markers[i]
            band_top = y_top if i == 0 else 0.5 * (markers[i - 1]["yc"] + m["yc"])
            band_bot = (
                0.5 * (m["yc"] + markers[i + 1]["yc"])
                if i + 1 < 5
                else float("inf")
            )

            fragments = []
            inline_rest = is_marker(m["text"], letter, strict=(letter == "A"))
            if inline_rest:
                fragments.append({
                    "x1": m["x1"],
                    "yc": m["yc"],
                    "h": m["h"],
                    "text": inline_rest.lstrip(")）] ").strip(),
                })

            for it in items:
                if it["idx"] in marker_indices:
                    continue
                if band_top <= it["yc"] < band_bot and it["xc"] >= m["x1"]:
                    fragments.append(it)

            options[letter] = join_option_fragments(fragments)

    if not all(options.values()):
        return {}, y_top
    return options, y_top


def is_diagram_label(text):
    """Heuristic for short isolated labels inside geometry/math diagrams."""
    t = text.strip()
    if len(t) <= 3 and re.match(r"^[A-Za-z0-9°′″]+$", t):
        return True
    if PURE_SYMBOL_RE.match(t):
        return True
    return False


def extract_statement_text(items, options_y_top):
    """Reconstruct clean problem statement lines above the options band."""
    candidates = [it for it in items if it["yc"] < options_y_top]
    if not candidates:
        return ""

    img_width = max(it["x2"] for it in items)
    med_h = median([it["h"] for it in candidates])

    # Group boxes into horizontal lines (top to bottom)
    candidates.sort(key=lambda it: it["yc"])
    rows = []
    for it in candidates:
        if rows and abs(it["yc"] - rows[-1][-1]["yc"]) <= 0.6 * max(it["h"], rows[-1][-1]["h"]):
            rows[-1].append(it)
        else:
            rows.append([it])

    for row in rows:
        row.sort(key=lambda it: it["x1"])

    # Determine left margin from rows that contain actual words
    prose_rows = [
        row for row in rows
        if any(re.search(r"[A-Za-zÀ-ÿ]{2,}", it["text"]) for it in row)
    ]
    if not prose_rows:
        return ""

    left_margin = min(row[0]["x1"] for row in prose_rows)
    gap_threshold = max(0.08 * img_width, 3.5 * med_h)

    clean_lines = []
    for row in rows:
        # Skip orphan figure rows indented far from the left margin
        if row[0]["x1"] - left_margin > 0.12 * img_width:
            if all(is_diagram_label(it["text"]) for it in row):
                continue

        # Trim trailing diagram labels separated by a wide horizontal whitespace gap
        kept = [row[0]]
        for prev, curr in zip(row, row[1:]):
            gap = curr["x1"] - prev["x2"]
            if gap > gap_threshold and is_diagram_label(curr["text"]):
                break
            kept.append(curr)

        line = " ".join(it["text"] for it in kept).strip()
        if line and not PURE_SYMBOL_RE.match(line):
            clean_lines.append(line)

    return "\n".join(clean_lines)


def image_to_record(ocr, image_path, default_language="eng"):
    """Run RapidOCR on a single problem image and return the structured dictionary."""
    meta = parse_filename(image_path, default_language=default_language)
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    boxes, _ = ocr(img_bytes)
    items = build_items(boxes or [])
    options, options_y_top = extract_options(items)
    text = extract_statement_text(items, options_y_top)

    return {
        "id": meta["id"],
        "language": meta["language"],
        "level": meta["level"],
        "year": meta["year"],
        "text_only": bool(options),
        "text": text,
        "options": options,
        "label": "",
    }


def main():
    args = parse_args()
    if not os.path.isfile(args.image):
        sys.exit(f"Image not found: {args.image}")

    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    record = image_to_record(ocr, args.image, default_language=args.default_language)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    mode = "a" if args.append else "w"
    with open(args.out, mode, encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()