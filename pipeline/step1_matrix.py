"""
Step 1: Build a search queue and scrape Google Maps.

Grid mode  (config has "grid" key):
  Generates a lat/lng grid over the bounding box and navigates Google Maps
  directly to each coordinate — gives complete, non-overlapping coverage.

Legacy mode (config has "cities" key):
  Generates city × search combos as before (kept for backward compatibility).

Each zone gets its own queue file (queue_dubai.csv, queue_sharjah.csv, etc.)
so progress is tracked independently per zone.
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
RAW_OUTPUT = _OUTPUTS / "scraped_raw.csv"


def _queue_path(zone_name=None):
    name = f"queue_{zone_name}.csv" if zone_name else "queue.csv"
    return _OUTPUTS / name


def generate_grid(bounds, step_km, searches, queue_path, location=""):
    lat_step   = step_km / 111.0
    center_lat = (bounds["lat_min"] + bounds["lat_max"]) / 2
    lng_step   = step_km / (111.0 * math.cos(math.radians(center_lat)))

    rows = []
    lat = bounds["lat_min"]
    while lat <= bounds["lat_max"] + 1e-9:
        lng = bounds["lng_min"]
        while lng <= bounds["lng_max"] + 1e-9:
            for s in searches:
                # Append city name to query so Google returns results in the
                # right city regardless of the user's IP location.
                query = f"{s} in {location}" if location else s
                rows.append({
                    "lat":       round(lat, 6),
                    "lng":       round(lng, 6),
                    "search":    s,
                    "query":     query,
                    "processed": False,
                })
            lng += lng_step
        lat += lat_step

    df = pd.DataFrame(rows)
    df.to_csv(queue_path, index=False)
    logging.info(
        f"Grid: {len(df)} points "
        f"({round((bounds['lat_max']-bounds['lat_min'])/lat_step)+1} lat × "
        f"{round((bounds['lng_max']-bounds['lng_min'])/lng_step)+1} lng) "
        f"× {len(searches)} search(es) → {queue_path}"
    )
    return df


def generate_city_queue(cities, searches, queue_path):
    combos = [
        {"city": c, "search": s, "query": f"{s} in {c}", "processed": False}
        for c, s in product(cities, searches)
    ]
    df = pd.DataFrame(combos)
    df.to_csv(queue_path, index=False)
    logging.info(f"Generated {len(df)} city × search combinations → {queue_path}")
    return df


def run(config, zone_name=None, max_grids=None):
    os.makedirs(_OUTPUTS, exist_ok=True)

    queue_path = _queue_path(zone_name)
    zoom       = config.get("grid", {}).get("zoom", 13)

    if queue_path.exists():
        df         = pd.read_csv(queue_path)
        is_grid    = "lat" in df.columns
        done_grids = len(df[df["processed"] == True][["lat", "lng"]].drop_duplicates()) if is_grid else int(df["processed"].sum())
        total_grids = len(df[["lat", "lng"]].drop_duplicates()) if is_grid else len(df)
        logging.info(f"Resuming from existing queue ({done_grids}/{total_grids} grid points done)")
    elif "grid" in config:
        g        = config["grid"]
        location = config.get("zone_location", "")
        df       = generate_grid(g["bounds"], g["step_km"], config["searches"], queue_path, location)
        is_grid  = True
    else:
        df      = generate_city_queue(config["cities"], config["searches"], queue_path)
        is_grid = False

    total_per_search = config.get("total_per_search", 20)

    # Build set of already-scraped names so each grid fetches only new places
    known_names: set = set()
    if RAW_OUTPUT.exists():
        try:
            existing = pd.read_csv(RAW_OUTPUT)
            if "name" in existing.columns:
                known_names = set(existing["name"].dropna().str.lower().str.strip())
            logging.info(f"Loaded {len(known_names)} known place names to skip duplicates")
        except Exception:
            pass

    # How many new grid points have been scraped this session
    new_grids_scraped = 0

    for idx, row in df.iterrows():
        if row["processed"]:
            continue

        # Stop if we've hit the per-run grid limit
        if max_grids is not None and is_grid and new_grids_scraped >= max_grids:
            logging.info(f"Reached --max-grids limit ({max_grids}). Stopping scrape early.")
            break

        query = row["query"]

        if is_grid:
            lat, lng = float(row["lat"]), float(row["lng"])
            label = f"{query} @{lat},{lng}"
        else:
            lat = lng = None
            label = query

        logging.info(f"[{idx + 1}/{len(df)}] Scraping: {label}")
        try:
            places = scrape_places(query, total_per_search, lat=lat, lng=lng, zoom=zoom, known_names=known_names)
            if places:
                append = RAW_OUTPUT.exists()
                save_places_to_csv(places, str(RAW_OUTPUT), append=append)
                # Grow known set so subsequent grids don't re-fetch these
                known_names.update(p.name.lower().strip() for p in places if p.name)
            df.at[idx, "processed"] = True
            df.to_csv(queue_path, index=False)
        except Exception as e:
            logging.error(f"Failed to scrape '{label}': {e}")
        finally:
            # Count every attempt (success or fail) toward the per-run limit
            if is_grid:
                new_grids_scraped += 1

    if RAW_OUTPUT.exists():
        logging.info("Normalizing names...")
        normalize_csv(str(RAW_OUTPUT), str(RAW_OUTPUT))
        logging.info("Removing duplicates...")
        remove_duplicates(str(RAW_OUTPUT), str(RAW_OUTPUT))

    # Log final progress
    df_final    = pd.read_csv(queue_path)
    done_final  = len(df_final[df_final["processed"] == True][["lat", "lng"]].drop_duplicates()) if is_grid else int(df_final["processed"].sum())
    total_final = len(df_final[["lat", "lng"]].drop_duplicates()) if is_grid else len(df_final)
    logging.info(f"Step 1 complete — {done_final}/{total_final} grid points scraped → {RAW_OUTPUT}")
