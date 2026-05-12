"""
Step 2: Use Groq LLM to filter scraped companies — keeps only those relevant
to the configured use case. Resumes by skipping already-processed names.

If a company has a website, the page content is fetched and passed to the LLM
as additional context so it can verify the curriculum (IBDP, IGCSE, A Levels, etc.)
rather than relying on the Google Maps name/description alone.

Supports multiple Groq API keys: set groq_api_key to a list in config.json and
the pipeline automatically rotates to the next key when the daily limit is hit.
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
    "You are a strict lead qualification analyst for SortMyPrep, an ed-tech platform "
    "that helps students prepare for IB, IGCSE, A Level, and SAT exams.\n\n"

    "Answer YES only if the business is an established coaching centre, tutoring institute, "
    "or school that EXPLICITLY and SPECIFICALLY serves school-age students (ages 10-18) "
    "preparing for one or more of: IB (International Baccalaureate / IBDP / MYP), "
    "IGCSE (Cambridge), A Levels, or SAT.\n\n"

    "Answer NO for ALL of the following — be strict:\n"
    "- Adult career training, professional development, or corporate training centres\n"
    "- General subject tutors (math-only, science-only, English-only) with NO mention "
    "of IB / IGCSE / A Level / SAT curriculum\n"
    "- Language schools or English language institutes\n"
    "- Vocational or skill-based training (IT, coding bootcamps, driving, etc.)\n"
    "- Early childhood / kindergarten / primary-only schools\n"
    "- University or college prep centres not focused on these specific exams\n"
    "- Individual freelance tutors or solo home tutors (not an institution)\n"
    "- Businesses whose website or description gives NO evidence of IB/IGCSE/A Level/SAT\n\n"

    "If website content is provided, treat it as the PRIMARY source of truth. "
    "If the website does not mention IB, IGCSE, A Level, or SAT anywhere, answer NO. "
    "Reply with ONLY 'YES' or 'NO'."
)

_WEBSITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _is_daily_limit_error(exc: Exception) -> bool:
    """Returns True if this exception is a Groq daily token limit error (not per-minute)."""
    msg = str(exc).lower()
    return "tokens per day" in msg or "tpd" in msg


def _fetch_website_text(url: str, max_chars: int = 2000) -> str:
    """Fetch a website and return stripped plain text. Returns '' on any failure."""
    if not url or not str(url).strip().startswith("http"):
        return ""
    try:
        resp = requests.get(url.strip(), timeout=8, headers=_WEBSITE_HEADERS)
        raw = resp.text
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = html.unescape(raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw[:max_chars]
    except Exception:
        return ""


def is_relevant(client, model, use_case, row, website_text: str = "") -> bool:
    """
    Ask the LLM whether this business is relevant.
    Raises the original exception if the daily token limit is hit (so the
    caller can rotate to the next API key). Other errors return True (keep row).
    """
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
        if _is_daily_limit_error(e):
            raise  # let the caller handle key rotation
        logging.warning(f"LLM call failed for '{row.get('name', '')}': {e} — keeping row")
        return True  # keep on non-limit errors to avoid silent data loss


def run(config):
    # Support a single key (string) or multiple keys (list)
    raw_keys = config.get("groq_api_key", "")
    if isinstance(raw_keys, str):
        raw_keys = [raw_keys]
    raw_keys = [k for k in raw_keys if k]

    if not raw_keys:
        logging.error("No Groq API keys configured.")
        return

    clients     = [Groq(api_key=k) for k in raw_keys]
    client_idx  = 0
    model       = config.get("groq_model", "llama-3.3-70b-versatile")
    use_case    = config["use_case_description"]

    logging.info(f"Groq key pool: {len(clients)} key(s) available")

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
    processed_this_run = 0
    for _, row in df.iterrows():
        name_key = str(row.get("name", "")).strip().lower()
        if name_key in processed_names:
            continue

        website_url  = str(row.get("website", "")).strip()
        website_text = _fetch_website_text(website_url)
        if website_text:
            logging.info(f"  Fetched website for '{row.get('name', '')}' ({len(website_text)} chars)")
        else:
            logging.info(f"  No website content for '{row.get('name', '')}' — using Maps data only")

        relevant = None
        while client_idx < len(clients):
            try:
                relevant = is_relevant(clients[client_idx], model, use_case, row, website_text)
                break
            except Exception as e:
                if _is_daily_limit_error(e):
                    logging.warning(
                        f"Key {client_idx + 1}/{len(clients)} daily limit hit — "
                        f"{'rotating to next key' if client_idx + 1 < len(clients) else 'all keys exhausted'}"
                    )
                    client_idx += 1
                else:
                    logging.warning(f"LLM call failed for '{row.get('name', '')}': {e} — keeping row")
                    break

        if relevant is None:
            # All keys exhausted
            logging.warning(f"All {len(clients)} API key(s) exhausted — keeping remaining rows unverified")
            relevant = True

        logging.info(f"{'KEEP' if relevant else 'DROP'}: {row.get('name', '')}")
        if relevant:
            kept.append(row.to_dict())

        processed_this_run += 1
        # ── checkpoint every 50 rows ──────────────────────────────────────────
        if processed_this_run % 50 == 0:
            logging.info(
                f"── {processed_this_run} processed this run "
                f"({len(kept)} kept so far) ──────────────────────────────"
            )

    result = (
        pd.concat([existing, pd.DataFrame(kept)], ignore_index=True)
        if not existing.empty
        else pd.DataFrame(kept)
    )
    result.to_csv(OUTPUT_PATH, index=False)
    logging.info(f"Step 2 complete. Kept {len(result)} rows → {OUTPUT_PATH}")
