#!/usr/bin/env python3
"""Read one picture of a problem with RapidOCR, and print {"text", "options"} as JSON.

    python web3/read_picture.py photo.jpg

The parsing is the team's (m3kang/image_to_json.py). What this adds: a photo with
small letters often comes back with the spaces missing ("Marchas9candies"), so the
picture is also read enlarged, with a white margin, and the best reading is kept.
Run it with the Python that has rapidocr_onnxruntime (web3/server.py does).
"""
import json
import os
import sys

import cv2
from rapidocr_onnxruntime import RapidOCR

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "m3kang"))
from image_to_json import extract_text_and_options  # noqa: E402

WIDTHS = (0, 1600, 2200)  # 0 = as it is; the M3Kang pictures are 1600 pixels wide
MARGIN = 0.25             # of the height: letters at the very edge are missed


def sized(image, width):
    if width <= image.shape[1]:
        return None if width else image
    scale = width / image.shape[1]
    big = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    pad = int(MARGIN * big.shape[0])
    return cv2.copyMakeBorder(big, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def main():
    image = cv2.imread(sys.argv[1])
    if image is None:
        sys.exit("can't open the picture")
    ocr = RapidOCR()
    best = None
    for width in WIDTHS:
        picture = sized(image, width)
        if picture is None:
            continue
        boxes = ocr(picture)[0] or []
        text, options = extract_text_and_options(boxes)
        # Five options first, then no lost line, then the most spaces between words
        score = (len(options) == 5, len(boxes), sum(box[1].count(" ") for box in boxes))
        if best is None or score > best[0]:
            best = (score, text, options, width)
    print(json.dumps({"text": best[1], "options": best[2], "width": best[3] or image.shape[1]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
