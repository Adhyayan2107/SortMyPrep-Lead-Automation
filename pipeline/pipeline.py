"""
Master pipeline orchestrator.

Usage:
    python pipeline.py --list-zones              # show all zones and grid point counts
    python pipeline.py --zone dubai              # run full pipeline for dubai
    python pipeline.py --zone dubai --reset      # clear dubai state and restart
    python pipeline.py --zone dubai --max-grids 3  # scrape only 3 grid points this run
    python pipeline.py --reset                   # clear ALL zone state and restart
"""

import argparse
import json
import logging
import math
import os
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_ROOT    = Path(__file__).parent.parent
_OUTPUTS = _ROOT / "Outputs"

CONFIG_PATH = _ROOT / "config.json"
STATE_PATH  = _OUTPUTS / "pipeline_state.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"zones": {}}


def save_state(state):
    os.makedirs(_OUTPUTS, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ── Per-zone queue helpers ────────────────────────────────────────────────────

def _queue_path(zone_name):
    return _OUTPUTS / f"queue_{zone_name}.csv"


def _grids_status(zone_name):
    """Returns (done_count, total_count) from zone's queue file. (0, 0) if not yet created."""
    path = _queue_path(zone_name)
    if not path.exists():
        return 0, 0
    df    = pd.read_csv(path)
    if "lat" not in df.columns:
        return int(df["processed"].sum()), len(df)
    total = len(df[["lat", "lng"]].drop_duplicates())
    done  = len(df[df["processed"] == True][["lat", "lng"]].drop_duplicates())
    return done, total


def _has_pending_grids(zone_name):
    done, total = _grids_status(zone_name)
    return total == 0 or done < total  # total==0 means queue not created yet


# ── Grid point estimator (for --list-zones) ──────────────────────────────────

def count_grid_points(bounds, step_km, n_searches):
    lat_step   = step_km / 111.0
    center_lat = (bounds["lat_min"] + bounds["lat_max"]) / 2
    lng_step   = step_km / (111.0 * math.cos(math.radians(center_lat)))
    n_lat = round((bounds["lat_max"] - bounds["lat_min"]) / lat_step) + 1
    n_lng = round((bounds["lng_max"] - bounds["lng_min"]) / lng_step) + 1
    return n_lat * n_lng * n_searches


# ── Commands ──────────────────────────────────────────────────────────────────

def list_zones(config, state):
    zones    = config.get("zones", {})
    searches = config.get("searches", [])

    print(f"\n{'Zone':<12}  {'Step':>6}  {'Grids':>8}  {'Est. leads':>10}  Status")
    print("-" * 62)
    for name, bounds in zones.items():
        step_km    = bounds.get("step_km", config.get("step_km", 10))
        total_pts  = count_grid_points(bounds, step_km, len(searches))
        est_leads  = total_pts * config.get("total_per_search", 10)
        done, _    = _grids_status(name)
        zone_state = state.get("zones", {}).get(name, {})

        if zone_state.get("step4_done") and done >= total_pts:
            status = "fully done"
        elif done > 0:
            status = f"{done}/{total_pts} grids scraped"
        else:
            status = "pending"

        print(f"  {name:<10}  {step_km:>5}km  {total_pts:>8}  {est_leads:>10}  {status}")
    print()


def reset_zone(zone_name, state):
    for fname in ["scraped_raw.csv", "filtered.csv", "with_contacts.csv"]:
        p = _OUTPUTS / fname
        if p.exists():
            p.unlink()
            logging.info(f"Deleted {fname}")

    qp = _queue_path(zone_name)
    if qp.exists():
        qp.unlink()
        logging.info(f"Deleted queue_{zone_name}.csv")

    state.setdefault("zones", {}).pop(zone_name, None)
    logging.info(f"Zone '{zone_name}' reset — will restart from Step 1.")
    return state


def reset_all(state):
    for fname in ["pipeline_state.json", "scraped_raw.csv", "filtered.csv", "with_contacts.csv"]:
        p = _OUTPUTS / fname
        if p.exists():
            p.unlink()
            logging.info(f"Deleted {fname}")

    for qf in _OUTPUTS.glob("queue_*.csv"):
        qf.unlink()
        logging.info(f"Deleted {qf.name}")

    logging.info("Full pipeline reset — all zone state cleared.")
    return {"zones": {}}


def _build_zone_config(config, zone_name):
    zone_bounds = config["zones"][zone_name]
    location    = zone_bounds.get("location", zone_name)
    country     = zone_bounds.get("country", "")
    step_km     = zone_bounds.get("step_km", config.get("step_km", 10))
    return {
        **config,
        "zone_location": location,
        "zone_country":  country,
        "grid": {
            "bounds":  zone_bounds,
            "step_km": step_km,
            "zoom":    config.get("zoom", 13),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Google Maps → contacts pipeline")
    parser.add_argument("--list-zones", action="store_true", help="List all zones with grid counts and status")
    parser.add_argument("--zone",       type=str,            help="Zone to run (e.g. dubai, sharjah)")
    parser.add_argument("--reset",      action="store_true", help="Clear state before running")
    parser.add_argument("--max-grids",  type=int, default=None, help="Limit scraping to N grid points this run")
    args = parser.parse_args()

    config = load_config()
    state  = load_state()

    if args.list_zones:
        list_zones(config, state)
        return

    if args.reset and not args.zone:
        state = reset_all(state)
        save_state(state)
        return

    zones = config.get("zones", {})

    if args.zone:
        zone_name = args.zone.lower()
        if zone_name not in zones:
            logging.error(f"Unknown zone '{zone_name}'. Run --list-zones to see options.")
            return
        if args.reset:
            state = reset_zone(zone_name, state)
            save_state(state)
        zone_config = _build_zone_config(config, zone_name)
    else:
        pending = [z for z in zones if _has_pending_grids(z)]
        if not pending:
            logging.info("All zones fully scraped. Use --reset to start over.")
            return
        zone_name   = pending[0]
        zone_config = _build_zone_config(config, zone_name)
        logging.info(f"No zone specified — running first pending zone: '{zone_name}'")

    import step1_matrix
    import step2_llm_filter
    import step3_rocketreach
    import step4_export

    zone_state = state.setdefault("zones", {}).setdefault(zone_name, {})

    done, total = _grids_status(zone_name)
    logging.info(f"\n{'='*60}\nZone: {zone_name.upper()}  ({done}/{total} grids done)\n{'='*60}")

    # ── Step 1: always runs if any grids are still pending ───────────────────
    if _has_pending_grids(zone_name):
        max_grids = args.max_grids
        done, total = _grids_status(zone_name)
        suffix = f" — scraping up to {max_grids} more grid(s)" if max_grids else ""
        logging.info(f"STEP 1: Scraping Google Maps ({done}/{total if total else '?'} done){suffix}")
        step1_matrix.run(zone_config, zone_name, max_grids=max_grids)

        # New data scraped — downstream steps need to re-run
        zone_state.pop("step2_done", None)
        zone_state.pop("step3_done", None)
        zone_state.pop("step4_done", None)
        save_state(state)
    else:
        logging.info("[SKIP] STEP 1: all grid points already scraped for this zone.")

    # ── Steps 2–4: resume from last completed step ────────────────────────────
    for key, label, fn in [
        ("step2_done", "STEP 2: LLM Filtering (Groq)",        step2_llm_filter.run),
        ("step3_done", "STEP 3: Contact Lookup (RocketReach)", step3_rocketreach.run),
        ("step4_done", "STEP 4: Final Export",                 step4_export.run),
    ]:
        if zone_state.get(key):
            logging.info(f"[SKIP] {label} already done.")
            continue
        logging.info(f"\n{'='*60}\n{label}\n{'='*60}")
        fn(zone_config)
        zone_state[key] = True
        save_state(state)

    logging.info(f"\nPipeline complete! Final output → {_ROOT / 'Outputs' / 'final_leads.xlsx'}")


if __name__ == "__main__":
    main()
