"""
Step 2: Use Groq LLM to filter scraped companies — keeps only those relevant
to the configured use case. Resumes by skipping already-processed names.
"""

import logging
import os
from pathlib import Path

import pandas as pd
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_OUTPUTS    = Path(__file__).parent.parent / "Outputs"
INPUT_PATH  = _OUTPUTS / "scraped_raw.csv"
OUTPUT_PATH = _OUTPUTS / "filtered.csv"

SYSTEM_PROMPT = (
    "You are a data quality analyst. Determine if a business listing is relevant "
    "to the given use case. Reply with ONLY 'YES' or 'NO'."
)


def is_relevant(client, model, use_case, row):
    details = (
        f"Name: {row.get('name', '')}\n"
        f"Type: {row.get('place_type', '')}\n"
        f"Introduction: {row.get('introduction', '')}\n"
        f"Address: {row.get('address', '')}"
    )
    user_msg = (
        f"Use case: {use_case}\n\nBusiness listing:\n{details}\n\n"
        "Is this business relevant to the use case? Reply ONLY 'YES' or 'NO'."
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=5,
            temperature=0,
        )
        answer = response.choices[0].message.content.strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logging.warning(f"LLM call failed for '{row.get('name', '')}': {e} — keeping row")
        return True  # keep on error to avoid silent data loss


def run(config):
    client = Groq(api_key=config["groq_api_key"])
    model = config.get("groq_model", "llama-3.3-70b-versatile")
    use_case = config["use_case_description"]

    if not os.path.exists(INPUT_PATH):
        logging.error(f"Input file not found: {INPUT_PATH} — did Step 1 produce any results?")
        return

    df = pd.read_csv(INPUT_PATH)
    logging.info(f"Loaded {len(df)} rows from '{INPUT_PATH}'")

    if os.path.exists(OUTPUT_PATH):
        existing = pd.read_csv(OUTPUT_PATH)
        processed_names = set(existing["name"].astype(str).str.strip().str.lower())
        logging.info(f"Resuming — {len(processed_names)} already processed")
    else:
        existing = pd.DataFrame()
        processed_names = set()

    kept = []
    for _, row in df.iterrows():
        name_key = str(row.get("name", "")).strip().lower()
        if name_key in processed_names:
            continue
        relevant = is_relevant(client, model, use_case, row)
        logging.info(f"{'KEEP' if relevant else 'DROP'}: {row.get('name', '')}")
        if relevant:
            kept.append(row.to_dict())

    result = (
        pd.concat([existing, pd.DataFrame(kept)], ignore_index=True)
        if not existing.empty
        else pd.DataFrame(kept)
    )
    result.to_csv(OUTPUT_PATH, index=False)
    logging.info(f"Step 2 complete. Kept {len(result)} rows → {OUTPUT_PATH}")
