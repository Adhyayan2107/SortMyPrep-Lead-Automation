"""
Step 2: Use Groq LLM to filter scraped companies — keeps only those relevant
to the configured use case. Resumes by skipping already-processed names.

If a company has a website, the page content is fetched and passed to the LLM
as additional context so it can verify the curriculum (IBDP, IGCSE, A Levels, etc.)
rather than relying on the Google Maps name/description alone.
"""

import html
import logging
import os
import re
from pathlib import Path

import pandas as pd
import requests
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_OUTPUTS    = Path(__file__).parent.parent / "Outputs"
INPUT_PATH  = _OUTPUTS / "scraped_raw.csv"
OUTPUT_PATH = _OUTPUTS / "filtered.csv"

SYSTEM_PROMPT = (
    "You are a data quality analyst. Determine if a business listing is relevant "
    "to the given use case. Reply with ONLY 'YES' or 'NO'.\n"
    "Prefer established organizations (coaching centers, schools, academies, institutes) "
    "that have decision-makers such as owners, directors, or principals who can be "
    "approached for partnerships. "
    "Reject individual freelance tutors, solo home tutors, or listings that appear to be "
    "a single teacher rather than an institution.\n"
    "If website content is provided, use it as the primary source of truth to confirm "
    "whether the business actually teaches IBDP, IGCSE, A Levels, or SAT."
)

_WEBSITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_website_text(url: str, max_chars: int = 2000) -> str:
    """Fetch a website and return stripped plain text. Returns '' on any failure."""
    if not url or not str(url).strip().startswith("http"):
        return ""
    try:
        resp = requests.get(url.strip(), timeout=8, headers=_WEBSITE_HEADERS)
        raw = resp.text
        # Remove script / style blocks entirely
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        # Strip remaining HTML tags
        raw = re.sub(r"<[^>]+>", " ", raw)
        # Decode HTML entities (&amp; etc.)
        raw = html.unescape(raw)
        # Collapse whitespace
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw[:max_chars]
    except Exception:
        return ""


def is_relevant(client, model, use_case, row, website_text: str = "") -> bool:
    details = (
        f"Name: {row.get('name', '')}\n"
        f"Type: {row.get('place_type', '')}\n"
        f"Introduction: {row.get('introduction', '')}\n"
        f"Address: {row.get('address', '')}"
    )
    if website_text:
        details += f"\n\nWebsite content (excerpt):\n{website_text}"

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
    client   = Groq(api_key=config["groq_api_key"])
    model    = config.get("groq_model", "llama-3.3-70b-versatile")
    use_case = config["use_case_description"]

    if not os.path.exists(INPUT_PATH):
        logging.error(f"Input file not found: {INPUT_PATH} — did Step 1 produce any results?")
        return

    df = pd.read_csv(INPUT_PATH)
    logging.info(f"Loaded {len(df)} rows from '{INPUT_PATH}'")

    if os.path.exists(OUTPUT_PATH):
        existing        = pd.read_csv(OUTPUT_PATH)
        processed_names = set(existing["name"].astype(str).str.strip().str.lower())
        logging.info(f"Resuming — {len(processed_names)} already processed")
    else:
        existing        = pd.DataFrame()
        processed_names = set()

    kept = []
    for _, row in df.iterrows():
        name_key = str(row.get("name", "")).strip().lower()
        if name_key in processed_names:
            continue

        # Fetch website for richer context — silent fallback if unavailable
        website_url  = str(row.get("website", "")).strip()
        website_text = _fetch_website_text(website_url)
        if website_text:
            logging.info(f"  Fetched website for '{row.get('name', '')}' ({len(website_text)} chars)")
        else:
            logging.info(f"  No website content for '{row.get('name', '')}' — using Maps data only")

        relevant = is_relevant(client, model, use_case, row, website_text)
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
