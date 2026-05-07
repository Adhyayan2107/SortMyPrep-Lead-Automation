"""
Step 1: Build a search queue and scrape Google Maps.

Grid mode  (config has "grid" key):
  Generates a lat/lng grid over the bounding box and navigates Google Maps
  directly to each coordinate — gives complete, non-overlapping coverage.

Legacy mode (config has "cities" key):
  Generates city × search combos as before (kept for backward compatibility).

Resumes from where it left off — queue.csv tracks which points are done.
"""

import logging
import math
import os
from itertools import product
from pathlib import Path

import pandas as pd

from main import scrape_places, save_places_to_csv
from normalize_names import normalize_csv
from remove_duplicates import remove_duplicates

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_OUTPUTS   = Path(__file__).parent.parent / "Outputs"
QUEUE_PATH = _OUTPUTS / "queue.csv"
RAW_OUTPUT = _OUTPUTS / "scraped_raw.csv"


def generate_grid(bounds, step_km, searches):
    """
    Generate a uniform lat/lng grid over the bounding box.
    Each point × each search term becomes one queue row.
    """
    lat_step = step_km / 111.0
    center_lat = (bounds["lat_min"] + bounds["lat_max"]) / 2
    lng_step = step_km / (111.0 * math.cos(math.radians(center_lat)))

    rows = []
    lat = bounds["lat_min"]
    while lat <= bounds["lat_max"] + 1e-9:
        lng = bounds["lng_min"]
        while lng <= bounds["lng_max"] + 1e-9:
            for s in searches:
                rows.append({
                    "lat":       round(lat, 6),
                    "lng":       round(lng, 6),
                    "search":    s,
                    "query":     s,
                    "processed": False,
                })
            lng += lng_step
        lat += lat_step

    df = pd.DataFrame(rows)
    df.to_csv(QUEUE_PATH, index=False)
    logging.info(
        f"Grid: {len(df)} points "
        f"({round((bounds['lat_max']-bounds['lat_min'])/lat_step)+1} lat × "
        f"{round((bounds['lng_max']-bounds['lng_min'])/lng_step)+1} lng) "
        f"× {len(searches)} search(es) → {QUEUE_PATH}"
    )
    return df


def generate_city_queue(cities, searches):
    combos = [
        {"city": c, "search": s, "query": f"{s} in {c}", "processed": False}
        for c, s in product(cities, searches)
    ]
    df = pd.DataFrame(combos)
    df.to_csv(QUEUE_PATH, index=False)
    logging.info(f"Generated {len(df)} city × search combinations → {QUEUE_PATH}")
    return df


def run(config):
    os.makedirs(_OUTPUTS, exist_ok=True)

    zoom = config.get("grid", {}).get("zoom", 13)

    if os.path.exists(QUEUE_PATH):
        df   = pd.read_csv(QUEUE_PATH)
        done = int(df["processed"].sum())
        logging.info(f"Resuming from existing queue ({done}/{len(df)} already done)")
    elif "grid" in config:
        g  = config["grid"]
        df = generate_grid(g["bounds"], g["step_km"], config["searches"])
    else:
        df = generate_city_queue(config["cities"], config["searches"])

    total_per_search = config.get("total_per_search", 20)
    is_grid = "lat" in df.columns

    for idx, row in df.iterrows():
        if row["processed"]:
            continue

        query = row["query"]

        if is_grid:
            lat, lng = float(row["lat"]), float(row["lng"])
            label = f"{query} @{lat},{lng}"
        else:
            lat = lng = None
            label = query

        logging.info(f"[{idx + 1}/{len(df)}] Scraping: {label}")
        try:
            places = scrape_places(query, total_per_search, lat=lat, lng=lng, zoom=zoom)
            if places:
                append = os.path.exists(RAW_OUTPUT)
                save_places_to_csv(places, str(RAW_OUTPUT), append=append)
            df.at[idx, "processed"] = True
            df.to_csv(QUEUE_PATH, index=False)
        except Exception as e:
            logging.error(f"Failed to scrape '{label}': {e}")
            # Leave as unprocessed — will retry on resume

    if os.path.exists(RAW_OUTPUT):
        logging.info("Normalizing names...")
        normalize_csv(str(RAW_OUTPUT), str(RAW_OUTPUT))
        logging.info("Removing duplicates...")
        remove_duplicates(str(RAW_OUTPUT), str(RAW_OUTPUT))

    logging.info(f"Step 1 complete → {RAW_OUTPUT}")
