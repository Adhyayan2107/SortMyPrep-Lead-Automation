"""
Step 3: For each filtered company, look up Level 1 and Level 2 contacts via RocketReach.
Resumes by skipping companies already written to with_contacts.csv.

Level 1: CXO, Founder, Co-Founder, Director, Principal, President, Owner
Level 2: Head of, VP, Vice President, Manager, Dean
Skip:    Associate, Intern, Coordinator, Assistant, Analyst, Junior, Trainee
"""

import logging
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_OUTPUTS    = Path(__file__).parent.parent / "Outputs"
INPUT_PATH  = _OUTPUTS / "filtered.csv"
OUTPUT_PATH = _OUTPUTS / "with_contacts.csv"

ROCKETREACH_SEARCH_URL = "https://api.rocketreach.co/api/v2/person/search"
ROCKETREACH_LOOKUP_URL = "https://api.rocketreach.co/api/v2/person/lookup"

LEVEL1_KEYWORDS = {"ceo", "coo", "cto", "cfo", "cmo", "cso", "chief", "founder",
                   "co-founder", "cofounder", "director", "principal", "president", "owner"}
LEVEL2_KEYWORDS = {"head", "vp", "vice president", "manager", "dean"}
SKIP_KEYWORDS   = {
    # Non-decision-maker roles — teaching staff
    "instructor", "teacher", "tutor", "lecturer", "faculty", "professor",
    "teaching assistant", "subject lead",
    # Functional / back-office managers who can't decide on partnerships
    "hr manager", "hr director", "finance manager", "finance director",
    "finance and hr", "accountant", "accounts manager", "accounts",
    "payroll", "it manager", "it support",
    # Junior / support roles
    "associate", "intern", "coordinator", "assistant", "analyst",
    "junior", "trainee", "support", "executive assistant",
}

CONTACT_COLUMNS = [
    "contact_name", "contact_title", "contact_level", "email", "linkedin",
    "company", "company_website", "company_address", "company_phone",
    "company_reviews_avg", "company_reviews_count", "zone_name",
]


def get_domain(url):
    if not url or str(url).strip() in ("", "nan"):
        return ""
    url = str(url).strip()
    if not url.startswith("http"):
        url = "https://" + url
    match = re.search(r'(?:https?://)?(?:www\.)?([^/\s]+)', url)
    return match.group(1) if match else ""


def classify(title):
    if not title:
        return "skip"
    t = title.lower()
    if any(kw in t for kw in SKIP_KEYWORDS):
        return "skip"
    if any(kw in t for kw in LEVEL1_KEYWORDS):
        return "level1"
    if any(kw in t for kw in LEVEL2_KEYWORDS):
        return "level2"
    return "skip"


def lookup_email(headers, profile_id):
    """Fetch full profile to get actual email address."""
    try:
        resp = requests.get(ROCKETREACH_LOOKUP_URL, headers=headers,
                            params={"id": profile_id}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            emails = data.get("emails") or []
            return emails[0].get("email", "") if emails else ""
    except Exception as e:
        logging.warning(f"Lookup failed for profile {profile_id}: {e}")
    return ""


def employer_matches(profile_employer, target_company):
    """
    Check if the profile's current_employer is the same company we searched for.
    Uses word-overlap so parent/subsidiary domains don't bleed across companies.
    """
    if not profile_employer:
        return True  # can't verify, keep it
    # Ignore generic words that appear in many school/company names
    noise = {"the", "and", "for", "of", "in", "at", "by", "a", "an",
             "school", "international", "academy", "institute", "college",
             "center", "centre", "group", "global", "education", "learning"}
    def key_words(s):
        return {w.lower() for w in re.split(r'\W+', s) if len(w) > 2 and w.lower() not in noise}

    target_words  = key_words(target_company)
    employer_words = key_words(profile_employer)
    if not target_words:
        return True
    overlap = target_words & employer_words
    return len(overlap) / len(target_words) >= 0.40


def lookup_by_linkedin(headers, linkedin_url):
    """Look up full profile (including email) directly by LinkedIn URL.
    Uses the lookup endpoint with linkedin_url param — skips the intermediate
    search step that was causing 400 errors with the search endpoint."""
    try:
        resp = requests.get(
            ROCKETREACH_LOOKUP_URL,
            headers=headers,
            params={"linkedin_url": linkedin_url},
            timeout=30,
        )
        if resp.status_code == 200:
            data   = resp.json()
            emails = data.get("emails") or []
            return emails[0].get("email", "") if emails else ""
        logging.warning(
            f"LinkedIn lookup {resp.status_code} for '{linkedin_url}': {resp.text[:200]}"
        )
    except Exception as e:
        logging.warning(f"LinkedIn lookup failed for '{linkedin_url}': {e}")
    return ""


def search_profiles(headers, employer_value, page_size=25):
    payload = {"query": {"employer": [employer_value]}, "start": 1, "page_size": page_size}
    try:
        resp = requests.post(ROCKETREACH_SEARCH_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("profiles", [])
    except Exception as e:
        logging.warning(f"RocketReach search error for '{employer_value}': {e}")
        return []


def fetch_contacts(api_key, company_name, domain, max_per_level):
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    profiles = []
    if domain:
        raw = search_profiles(headers, domain)
        # Keep only profiles actually employed at this company, not a parent/sibling
        profiles = [p for p in raw if employer_matches(p.get("current_employer", ""), company_name)]
        if not profiles and raw:
            # Domain returned results but none match — fall back to name search
            logging.info(f"  Domain '{domain}' returned unrelated profiles; falling back to name search")
            profiles = search_profiles(headers, company_name)

    if not profiles:
        profiles = search_profiles(headers, company_name)

    level1, level2 = [], []
    for p in profiles:
        title = p.get("current_title", "") or ""
        level = classify(title)
        if level == "skip":
            continue

        # Skip if we already have enough contacts at this level — don't spend a credit
        if level == "level1" and len(level1) >= max_per_level:
            continue
        if level == "level2" and len(level2) >= max_per_level:
            continue

        # Primary email lookup
        email = ""
        if p.get("status") == "complete":
            email = lookup_email(headers, p["id"])
            time.sleep(0.5)

        # Fallback: look up directly by LinkedIn URL if primary lookup missed
        if not email:
            li_url = p.get("linkedin_url", "")
            if li_url:
                email = lookup_by_linkedin(headers, li_url)
                if email:
                    logging.info(f"  LinkedIn fallback got email for {p.get('name', '')}")
                time.sleep(0.5)

        contact = {
            "contact_name":  p.get("name", ""),
            "contact_title": title,
            "contact_level": level,
            "email":         email,
            "linkedin":      p.get("linkedin_url", ""),
        }
        if level == "level1":
            level1.append(contact)
        elif level == "level2":
            level2.append(contact)

        if len(level1) >= max_per_level and len(level2) >= max_per_level:
            break

    return level1, level2


def run(config):
    api_key       = config["rocketreach_api_key"]
    max_per_level = config.get("rocketreach_max_contacts_per_level", 2)
    zone          = config.get("zone_name", "")

    df = pd.read_csv(INPUT_PATH)
    logging.info(f"Loaded {len(df)} companies from '{INPUT_PATH}'")

    if os.path.exists(OUTPUT_PATH):
        existing = pd.read_csv(OUTPUT_PATH)
        done_companies = set(existing["company"].astype(str).str.strip().str.lower())
        logging.info(f"Resuming — {len(done_companies)} companies already processed")
        all_rows = existing.to_dict("records")
    else:
        done_companies = set()
        all_rows = []

    for _, company_row in df.iterrows():
        company_name = str(company_row.get("name", "")).strip()
        if company_name.lower() in done_companies:
            continue

        website = str(company_row.get("website", ""))
        domain  = get_domain(website)
        logging.info(f"Looking up: {company_name} ({domain or 'no domain'})")

        level1, level2 = fetch_contacts(api_key, company_name, domain, max_per_level)
        contacts = level1 + level2

        if not contacts:
            logging.info(f"  No contacts found for {company_name}")
            # Still record the company so we don't retry it on resume
            contacts = [{
                "contact_name": "", "contact_title": "",
                "contact_level": "", "email": "", "linkedin": "",
            }]

        for contact in contacts:
            all_rows.append({
                **contact,
                "company":               company_name,
                "company_website":       website,
                "company_address":       company_row.get("address", ""),
                "company_phone":         company_row.get("phone_number", ""),
                "company_reviews_avg":   company_row.get("reviews_average", ""),
                "company_reviews_count": company_row.get("reviews_count", ""),
                "zone_name":             zone,
            })

        done_companies.add(company_name.lower())

        # Save after every company so a crash loses at most 1 entry
        pd.DataFrame(all_rows, columns=CONTACT_COLUMNS).to_csv(OUTPUT_PATH, index=False)
        time.sleep(1)  # stay inside RocketReach rate limits

    logging.info(f"Step 3 complete. {len(all_rows)} contact rows → {OUTPUT_PATH}")
