"""
Remove duplicate entries from result.csv.

Two passes:
  1. Name duplicates  — case-insensitive, whitespace-stripped name match.
  2. Website duplicates — if multiple rows share the same domain (e.g. cioaltutors.com),
     keep only the first occurrence. Rows with no website are never dropped by this pass.

In both passes the first occurrence is kept and later ones are dropped.

Usage:
    python remove_duplicates.py                      # uses result.csv
    python remove_duplicates.py -i data.csv          # custom input
    python remove_duplicates.py -i data.csv -o clean.csv  # custom output
"""

import argparse
import logging
import re
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _normalise_domain(url: str) -> str:
    """Return bare domain (e.g. 'cioaltutors.com') or '' if url is empty/invalid."""
    url = str(url).strip().lower()
    if not url or url in ("nan", "none", ""):
        return ""
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    domain = url.split("/")[0].split("?")[0]
    return domain


def remove_duplicates(input_path: str, output_path: str) -> None:
    df = pd.read_csv(input_path)
    original_count = len(df)
    logging.info(f"Loaded {original_count} rows from '{input_path}'")

    if "name" not in df.columns:
        logging.error("CSV does not contain a 'name' column — cannot deduplicate.")
        return

    # Pass 1: deduplicate by name
    df["_name_key"] = df["name"].astype(str).str.strip().str.lower()
    df.drop_duplicates(subset="_name_key", keep="first", inplace=True)
    df.drop(columns=["_name_key"], inplace=True)
    after_name = len(df)
    logging.info(f"Pass 1 (name):    removed {original_count - after_name}, {after_name} remain")

    # Pass 2: deduplicate by website domain — skip rows with no website
    if "website" in df.columns:
        df["_domain_key"] = df["website"].apply(_normalise_domain)
        has_site  = df["_domain_key"] != ""
        site_dupes = df[has_site].duplicated(subset="_domain_key", keep="first")
        drop_idx  = df[has_site][site_dupes].index
        df.drop(index=drop_idx, inplace=True)
        df.drop(columns=["_domain_key"], inplace=True)
        after_site = len(df)
        logging.info(f"Pass 2 (website): removed {after_name - after_site}, {after_site} remain")

    df.reset_index(drop=True, inplace=True)
    removed = original_count - len(df)
    logging.info(f"Total removed: {removed}. {len(df)} unique rows remain.")

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
