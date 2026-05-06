"""
Remove duplicate entries from result.csv.

Duplicates are detected by matching on the 'name' column (case-insensitive,
after stripping whitespace). When duplicates are found, the first occurrence
is kept and later ones are dropped.

Usage:
    python remove_duplicates.py                      # uses result.csv
    python remove_duplicates.py -i data.csv          # custom input
    python remove_duplicates.py -i data.csv -o clean.csv  # custom output
"""

import argparse
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def remove_duplicates(input_path: str, output_path: str) -> None:
    df = pd.read_csv(input_path)
    original_count = len(df)
    logging.info(f"Loaded {original_count} rows from '{input_path}'")

    if "name" not in df.columns:
        logging.error("CSV does not contain a 'name' column — cannot deduplicate.")
        return

    # Build a normalised key for duplicate detection
    df["_dedup_key"] = df["name"].astype(str).str.strip().str.lower()

    df.drop_duplicates(subset="_dedup_key", keep="first", inplace=True)
    df.drop(columns=["_dedup_key"], inplace=True)

    removed = original_count - len(df)
    logging.info(f"Removed {removed} duplicate(s). {len(df)} unique rows remain.")

    df.to_csv(output_path, index=False)
    logging.info(f"Saved deduplicated data to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(description="Remove duplicate entries from a scraped CSV")
    parser.add_argument("-i", "--input", type=str, default="result.csv", help="Input CSV path")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output CSV path (defaults to overwriting input)")
    args = parser.parse_args()

    output = args.output or args.input
    remove_duplicates(args.input, output)


if __name__ == "__main__":
    main()
