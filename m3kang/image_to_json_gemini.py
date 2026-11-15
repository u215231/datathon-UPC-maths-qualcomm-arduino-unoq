import argparse
import json
import mimetypes
import os
import re
import sys
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

FILENAME_RE = re.compile(
    r"^(?P<id>lvl-(?P<level>\d+)_(?P<year>\d{4})_(?P<num>[^_]+))_(?P<language>[a-z]{2,3})$",
    re.IGNORECASE,
)


class OptionsSchema(BaseModel):
    A: str = Field(description="Option A in clean LaTeX/text without the 'A)' prefix")
    B: str = Field(description="Option B in clean LaTeX/text without the 'B)' prefix")
    C: str = Field(description="Option C in clean LaTeX/text without the 'C)' prefix")
    D: str = Field(description="Option D in clean LaTeX/text without the 'D)' prefix")
    E: str = Field(description="Option E in clean LaTeX/text without the 'E)' prefix")


class ProblemExtraction(BaseModel):
    text: str = Field(
        description="Full problem statement including question number, with math expressions formatted in LaTeX ($...$). Exclude labels inside diagrams."
    )
    options: OptionsSchema
    has_diagram: bool = Field(
        description="True if the image contains a geometric figure, diagram, or visual puzzle beyond the text and options."
    )


EXTRACTION_PROMPT = """Extract the math competition problem from this image into structured JSON.
Rules:
1. Format all mathematical expressions, fractions, square roots, exponents, angles, negative numbers, and variables in valid LaTeX wrapped in single dollar signs (e.g. $6\\sqrt{2}$, $\\frac{p+3q}{4}$, $\\sqrt{(a+b)^2+c^2}$, $45^\\circ$, $-23$).
2. Keep the original language of the statement (e.g. English or Catalan) verbatim.
3. Include the leading problem number in 'text' if visible (e.g. '23. I have a piece...').
4. Do NOT include isolated vertex or dimension labels from the geometric figure (such as X, Y, a, b, c, A, B, C) inside 'text'.
5. Strip the option prefixes 'A)', 'B)', 'C)', 'D)', 'E)' from the option values.
6. Set 'has_diagram' to true if there is a figure, drawing, or blank-box equation diagram."""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a math problem image into a LaTeX JSONL record via Gemini Vision API."
    )
    parser.add_argument("--image", required=True, help="Path to the input problem image")
    parser.add_argument("--out", required=True, help="Path to the output .jsonl file")
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model to use (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--default-language",
        default="eng",
        help="Fallback language if filename does not end with _<lang>",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to --out instead of overwriting",
    )
    return parser.parse_args()


def parse_filename(image_path, default_language="eng"):
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


def extract_with_api(client, model_name, image_path, default_language="eng"):
    meta = parse_filename(image_path, default_language=default_language)
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/png"

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=ProblemExtraction,
        ),
    )

    parsed = ProblemExtraction.model_validate_json(response.text)

    return {
        "id": meta["id"],
        "language": meta["language"],
        "level": meta["level"],
        "year": meta["year"],
        "text_only": not parsed.has_diagram,
        "text": parsed.text.strip(),
        "options": parsed.options.model_dump(),
        "label": "",
    }


def main():
    args = parse_args()
    if not os.path.isfile(args.image):
        sys.exit(f"Image not found: {args.image}")
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Missing GEMINI_API_KEY environment variable.")

    client = genai.Client()
    record = extract_with_api(
        client,
        args.model,
        args.image,
        default_language=args.default_language,
    )

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    mode = "a" if args.append else "w"
    with open(args.out, mode, encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()