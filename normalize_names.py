"""
Normalize company names in result.csv.

Cleans up scraped names by:
  1. Splitting on common separators (–, -, |, l) and taking the first token
  2. Stripping marketing buzzwords (Best, Top, Leading, No.1, #1)
  3. Removing trailing location phrases ("in Dubai", "in UAE", etc.)
  4. Removing legal suffixes (LLC, FZC, FZE, FZCO, Ltd, Pvt, DMCC, etc.)
  5. Title-casing the result

Usage:
    python normalize_names.py                           # uses result.csv
    python normalize_names.py -i data.csv               # custom input
    python normalize_names.py -i data.csv -o clean.csv  # custom output
"""

import argparse
import logging
import re

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def normalize_name(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return raw

    # 1. Split on common separators, take the first meaningful token
    #    Handles  –  -  |  and the letter 'l' used as separator (case-sensitive single char)
    name = re.split(r'\s*[–|]\s*|\s+-\s+|\s+l\s+', raw)[0].strip()

    # 2. Remove marketing / superlative prefixes & suffixes
    suffixes = [
        r'\b(best|top|leading|no\.?\s*1|#1)\b.*',          # "Best Career Counselors …"
        r'\bin\s+\w+(\s+\w+){0,3}\s*$',                    # "in Dubai", "in UAE", "in Al Barsha"
        r'\b(llc|fzc|fze|fzco|ltd|pvt|dmcc|inc)\b\.?\s*',  # legal suffixes
        r'\bpowered\s+by\b.*',                              # "powered by Amourion Group"
    ]
    for pattern in suffixes:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()

    # 3. Clean leftover punctuation artefacts
    name = re.sub(r'^[\s,\-–|]+|[\s,\-–|]+$', '', name)

    # 4. Collapse multiple spaces
    name = re.sub(r'\s{2,}', ' ', name).strip()

    # 5. Title case normalise (preserving common acronyms)
    acronyms = {"ib", "uae", "uk", "us", "usa", "sat", "ielts", "pte", "lnat",
                "gmat", "gre", "ucat", "ems", "idp", "hr", "hric", "difc", "dmcc"}
    words = name.title().split()
    normalised_words = [w.upper() if w.lower() in acronyms else w for w in words]
    name = " ".join(normalised_words)

    return name


def normalize_csv(input_path: str, output_path: str) -> None:
    df = pd.read_csv(input_path)
    logging.info(f"Loaded {len(df)} rows from '{input_path}'")

    if "name" not in df.columns:
        logging.error("CSV does not contain a 'name' column — nothing to normalise.")
        return

    # Show a few before/after examples
    sample = df["name"].head(10)
    for raw in sample:
        logging.info(f"  '{raw}'  →  '{normalize_name(raw)}'")

    df["name"] = df["name"].apply(normalize_name)
    df.to_csv(output_path, index=False)
    logging.info(f"Saved normalised data ({len(df)} rows) to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(description="Normalize company names in a scraped CSV")
    parser.add_argument("-i", "--input", type=str, default="result.csv", help="Input CSV path")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output CSV path (defaults to overwriting input)")
    args = parser.parse_args()

    output = args.output or args.input
    normalize_csv(args.input, output)


if __name__ == "__main__":
    main()
