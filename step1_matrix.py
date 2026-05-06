"""
Step 1: Generate city x search combos, scrape each one, then normalize and deduplicate.
Resumes from where it left off — queue.csv tracks which combos are done.
"""

import logging
import os
from itertools import product

import pandas as pd

from main import scrape_places, save_places_to_csv
from normalize_names import normalize_csv
from remove_duplicates import remove_duplicates

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

QUEUE_PATH = "Outputs/queue.csv"
RAW_OUTPUT = "Outputs/scraped_raw.csv"


def generate_queue(cities, searches):
    combos = [
        {"city": c, "search": s, "query": f"{s} in {c}", "processed": False}
        for c, s in product(cities, searches)
    ]
    df = pd.DataFrame(combos)
    df.to_csv(QUEUE_PATH, index=False)
    logging.info(f"Generated {len(df)} search combinations → {QUEUE_PATH}")
    return df


def run(config):
    os.makedirs("Outputs", exist_ok=True)

    if os.path.exists(QUEUE_PATH):
        df = pd.read_csv(QUEUE_PATH)
        done = int(df["processed"].sum())
        logging.info(f"Resuming from existing queue ({done}/{len(df)} already done)")
    else:
        df = generate_queue(config["cities"], config["searches"])

    total_per_search = config.get("total_per_search", 20)

    for idx, row in df.iterrows():
        if row["processed"]:
            continue
        query = row["query"]
        logging.info(f"[{idx + 1}/{len(df)}] Scraping: {query}")
        try:
            places = scrape_places(query, total_per_search)
            if places:
                append = os.path.exists(RAW_OUTPUT)
                save_places_to_csv(places, RAW_OUTPUT, append=append)
            df.at[idx, "processed"] = True
            df.to_csv(QUEUE_PATH, index=False)
        except Exception as e:
            logging.error(f"Failed to scrape '{query}': {e}")
            # Leave as unprocessed so it retries on resume

    if os.path.exists(RAW_OUTPUT):
        logging.info("Normalizing names...")
        normalize_csv(RAW_OUTPUT, RAW_OUTPUT)
        logging.info("Removing duplicates...")
        remove_duplicates(RAW_OUTPUT, RAW_OUTPUT)

    logging.info(f"Step 1 complete → {RAW_OUTPUT}")
