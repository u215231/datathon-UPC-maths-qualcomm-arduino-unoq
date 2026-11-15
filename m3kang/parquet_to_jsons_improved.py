import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from image_to_json_improved import ImageOptionReader, OCR_TYPES
except ImportError:
    from image_to_json import ImageOptionReader, OCR_TYPES

DATASET = "qualcomm/M3Kang"
SHARD = "data/{split}-{index:05d}-of-{total:05d}.parquet"
SHARDS = {"high_quality": 4, "standard": 10}


def parse_args():
    p = argparse.ArgumentParser(
        description="Prepare M3Kang JSONL splits with LaTeX option extraction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--split", default="high_quality", choices=sorted(SHARDS))
    p.add_argument(
        "--shards",
        default="0",
        help="comma-separated shard numbers, or 'all'. Shard 0 of high_quality has "
             "eng, cat, fra, esp, ind, deu, swh, vie, tur, zho, kor, arb, jpn, lit",
    )
    p.add_argument("--parquet", nargs="*", help="use local parquet files instead of downloading")
    p.add_argument("--languages", default="eng,cat", help="M3Kang language codes, e.g. eng,cat,esp")
    p.add_argument("--val-fraction", type=float, default=0.15, help="share of problem IDs held out")
    p.add_argument("--val-years", default="", help="hold out these years instead, e.g. 2023,2024")
    p.add_argument("--out", default="data", help="output folder")
    p.add_argument(
        "--ocr-type",
        default="rapidocr-enhanced",
        choices=OCR_TYPES,
        help="OCR engine to use for reading options (default: rapidocr-enhanced)",
    )
    p.add_argument("--no-ocr", action="store_true", help="skip OCR; options will be empty")
    p.add_argument("--no-cache", action="store_true", help="ignore .ocr_cache.jsonl and re-run OCR")
    p.add_argument("--save-images", action="store_true", help="also save problem images as PNG")
    p.add_argument("--limit", type=int, default=0, help="only process the first N rows (for testing)")
    return p.parse_args()


def shard_paths(args):
    if args.parquet:
        return args.parquet
    from huggingface_hub import hf_hub_download

    total = SHARDS[args.split]
    indexes = range(total) if args.shards == "all" else [int(s) for s in args.shards.split(",")]
    paths = []
    for i in indexes:
        name = SHARD.format(split=args.split, index=i, total=total)
        print(f"Downloading {name} (cached after the first time)...", flush=True)
        paths.append(hf_hub_download(DATASET, name, repo_type="dataset"))
    return paths


def main():
    args = parse_args()
    import pyarrow.parquet as pq

    languages = {l.strip() for l in args.languages.split(",") if l.strip()}
    val_years = {y.strip() for y in args.val_years.split(",") if y.strip()}
    os.makedirs(args.out, exist_ok=True)
    if args.save_images:
        os.makedirs(os.path.join(args.out, "images"), exist_ok=True)

    reader = None
    if not args.no_ocr:
        reader = ImageOptionReader(ocr_type=args.ocr_type)

    cache_path = os.path.join(args.out, ".ocr_cache.jsonl")
    cache = {}
    if os.path.exists(cache_path) and not args.no_cache:
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    if row.get("options"):
                        cache[row["key"]] = {
                            "options": row.get("options", {}),
                            "options_type": row.get("options_type", "text"),
                        }
    cache_file = open(cache_path, "a", encoding="utf-8")

    rows = []
    t0 = time.time()
    for path in shard_paths(args):
        table = pq.read_table(path, columns=["language"])
        wanted = [i for i, lang in enumerate(table.column(0).to_pylist()) if lang in languages]
        if not wanted:
            continue
        full = pq.read_table(path).take(wanted)
        for i in range(full.num_rows):
            if args.limit and len(rows) >= args.limit:
                break
            r = {c: full.column(c)[i].as_py() for c in ("id", "language", "level", "text_only", "label", "text")}
            key = f"{r['id']}|{r['language']}"
            cache_key = f"{key}|{args.ocr_type}"
            image = full.column("image")[i].as_py()["bytes"]

            if args.save_images:
                img_out = os.path.join(args.out, "images", key.replace("|", "_") + ".png")
                with open(img_out, "wb") as f:
                    f.write(image)

            if args.no_ocr:
                options = {}
                options_type = "empty"
            elif cache_key in cache:
                options = cache[cache_key]["options"]
                options_type = cache[cache_key]["options_type"]
            else:
                res = reader.read_image(image)
                options = res["options"]
                options_type = res["options_type"]
                if options:
                    cache[cache_key] = {"options": options, "options_type": options_type}
                    cache_file.write(
                        json.dumps(
                            {"key": cache_key, "options": options, "options_type": options_type},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

            year = r["id"].split("_")[1]
            if val_years:
                split = "val" if year in val_years else "train"
            else:
                bucket = int(hashlib.sha256(r["id"].encode()).hexdigest(), 16) % 1000
                split = "val" if bucket < args.val_fraction * 1000 else "train"

            rows.append({
                "id": r["id"],
                "language": r["language"],
                "level": r["level"],
                "year": int(year),
                "text_only": r["text_only"],
                "options_type": options_type,
                "text": r["text"].strip(),
                "options": options,
                "label": r["label"],
                "split": split,
            })
            if len(rows) % 100 == 0:
                rate = len(rows) / max(time.time() - t0, 1e-6)
                print(f"  [{args.ocr_type}] {len(rows)} rows, {rate:.1f} rows/s", flush=True)
    cache_file.close()

    for split in ("train", "val"):
        out = os.path.join(args.out, f"{split}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for r in rows:
                if r["split"] == split:
                    f.write(json.dumps({k: v for k, v in r.items() if k != "split"}, ensure_ascii=False) + "\n")

    report(rows, args.out, args.ocr_type)


def report(rows, out, ocr_type):
    if not rows:
        sys.exit("No rows matched. Check --languages and --shards.")
    by = Counter((r["split"], r["language"]) for r in rows)
    by_opt_type = Counter(r.get("options_type", "empty") for r in rows)
    with_options = sum(1 for r in rows if r["options"])
    text_only = [r for r in rows if r["text_only"]]
    labels = Counter(r["label"] for r in rows if r["split"] == "train")
    print()
    print(f"Wrote {out}/train.jsonl and {out}/val.jsonl (ocr-type: {ocr_type})")
    for (split, lang), n in sorted(by.items()):
        print(f"  {split:5} {lang}: {n}")
    print(f"Options read from the image: {with_options}/{len(rows)} ({100 * with_options / len(rows):.0f}%)")
    print(f"  breakdown: {dict(by_opt_type)}")
    if text_only:
        ok = sum(1 for r in text_only if r["options"])
        print(f"  of which text-only problems: {ok}/{len(text_only)} ({100 * ok / len(text_only):.0f}%)")
    if labels:
        top, count = labels.most_common(1)[0]
        print(
            f"Most common answer in train: {top} ({100 * count / sum(labels.values()):.1f}%). "
            f"Always answering {top} is the floor to beat."
        )


if __name__ == "__main__":
    main()