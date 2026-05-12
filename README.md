# SortMyPrep Lead Generation Pipeline

An end-to-end automated system that scrapes Google Maps for IB/IGCSE/A Level/SAT coaching centres across the UAE, filters them with an LLM, enriches them with decision-maker contacts via RocketReach, and pushes them to a Google Sheet for outreach — all from a single command.

---

## How It Works

```
Google Maps (Playwright)
        ↓  Step 1 — Grid scrape
  scraped_raw.csv
        ↓  Step 2 — LLM filter (Groq)
    filtered.csv
        ↓  Step 3 — Contact lookup (RocketReach)
  with_contacts.csv
        ↓  Step 4 — Export + backend sync
  final_leads.xlsx  +  MongoDB (via Flask backend)
        ↓
  Google Sheet (Apps Script)
```

---

## Project Structure

```
Google-Maps-Scrapper/
├── pipeline/                   # Core scraping + processing pipeline
│   ├── pipeline.py             # Master orchestrator (entry point)
│   ├── main.py                 # Playwright scraper (Google Maps)
│   ├── step1_matrix.py         # Grid generation + scrape queue
│   ├── step2_llm_filter.py     # LLM relevance filter (Groq)
│   ├── step3_rocketreach.py    # Contact enrichment (RocketReach API)
│   ├── step4_export.py         # Excel export + backend push
│   ├── normalize_names.py      # Name normalisation utility
│   ├── remove_duplicates.py    # Deduplication utility
│   └── requirements.txt
│
├── backend/                    # Flask REST API (deployed on Render)
│   ├── app.py                  # App factory + dependency wiring
│   ├── config.py               # Env var config
│   ├── controllers/
│   │   ├── lead_controller.py  # Lead CRUD endpoints
│   │   └── health_controller.py
│   ├── services/
│   │   ├── lead_service.py     # Business logic
│   │   └── email_service.py    # Groq-powered email script generator
│   ├── repositories/
│   │   └── lead_repository.py  # MongoDB data access
│   ├── models/
│   │   └── lead.py             # Lead data model
│   ├── requirements.txt
│   └── render.yaml             # Render deployment config
│
├── apps_script/
│   ├── google_apps_script.js   # Google Sheets integration
│   └── appsscript.json
│
├── Outputs/                    # All pipeline outputs (gitignored)
│   ├── scraped_raw.csv         # Raw Google Maps data
│   ├── filtered.csv            # After LLM filter
│   ├── with_contacts.csv       # After RocketReach enrichment
│   ├── final_leads.xlsx        # Final styled Excel export
│   ├── pipeline_state.json     # Per-zone progress tracker
│   └── queue_<zone>.csv        # Per-zone scrape queue
│
├── config.json                 # Your config (gitignored)
├── config.example.json         # Config template
└── README.md
```

---

## Prerequisites

- Python 3.11+
- A Groq API key — [console.groq.com](https://console.groq.com) (free tier: 100k tokens/day)
- A RocketReach API key — [rocketreach.co](https://rocketreach.co) (paid)
- MongoDB Atlas URI (free tier works)
- Google Chrome installed (used by Playwright)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd "Google-Maps-Scrapper"
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
```

### 2. Install pipeline dependencies

```bash
pip install -r pipeline/requirements.txt
playwright install chromium
```

### 3. Create your config file

```bash
cp config.example.json config.json
```

Edit `config.json` with your API keys and settings (see Configuration section below).

### 4. Install backend dependencies (only needed if running locally)

```bash
pip install -r backend/requirements.txt
```

---

## Configuration (`config.json`)

```json
{
  "zones": {
    "dubai":     {"lat_min": 24.85, "lat_max": 25.40, "lng_min": 54.95, "lng_max": 55.65, "step_km": 25, "location": "Dubai",         "country": "UAE"},
    "sharjah":   {"lat_min": 25.20, "lat_max": 25.60, "lng_min": 55.30, "lng_max": 55.90, "step_km": 15, "location": "Sharjah",        "country": "UAE"},
    "abu_dhabi": {"lat_min": 24.10, "lat_max": 24.55, "lng_min": 54.20, "lng_max": 54.75, "step_km": 15, "location": "Abu Dhabi",      "country": "UAE"},
    "ajman":     {"lat_min": 25.35, "lat_max": 25.53, "lng_min": 55.43, "lng_max": 55.57, "step_km":  7, "location": "Ajman",          "country": "UAE"},
    "rak":       {"lat_min": 25.55, "lat_max": 25.90, "lng_min": 55.70, "lng_max": 56.10, "step_km": 15, "location": "Ras Al Khaimah", "country": "UAE"},
    "fujairah":  {"lat_min": 25.00, "lat_max": 25.40, "lng_min": 56.15, "lng_max": 56.45, "step_km": 15, "location": "Fujairah",       "country": "UAE"},
    "uaq":       {"lat_min": 25.50, "lat_max": 25.65, "lng_min": 55.50, "lng_max": 55.65, "step_km":  8, "location": "Umm Al Quwain",  "country": "UAE"}
  },
  "zoom": 13,
  "searches": ["IB coaching", "IGCSE coaching", "A Level coaching", "SAT coaching"],
  "total_per_search": 10,
  "groq_api_key": "YOUR_GROQ_API_KEY",
  "groq_model": "llama-3.3-70b-versatile",
  "use_case_description": "Coaching centers that EXPLICITLY prepare students for IB, IGCSE, A Levels, or SAT",
  "rocketreach_api_key": "YOUR_ROCKETREACH_API_KEY",
  "rocketreach_max_contacts_per_level": 2,
  "backend_url": "https://your-backend.onrender.com"
}
```

| Key | Description |
|-----|-------------|
| `zones` | Geographic zones — each defines a bounding box and a `step_km` grid spacing |
| `step_km` | Distance between grid points in km. Smaller = more coverage, more scraping time |
| `zoom` | Google Maps zoom level (13 recommended) |
| `searches` | Search queries to run at each grid point |
| `total_per_search` | Max results to collect per query per grid point |
| `groq_api_key` | Groq API key for LLM filtering and email generation |
| `groq_model` | Groq model to use (`llama-3.3-70b-versatile` recommended) |
| `use_case_description` | Plain-English description of what counts as a relevant lead — the LLM uses this to filter |
| `rocketreach_api_key` | RocketReach API key for contact lookup |
| `rocketreach_max_contacts_per_level` | Max contacts to fetch per level (L1 and L2) per company |
| `backend_url` | Your deployed Flask backend URL |

---

## Running the Pipeline

All commands are run from inside the `pipeline/` directory:

```bash
cd pipeline
```

### See all zones and their status

```bash
python pipeline.py --list-zones
```

Shows each zone with grid count, estimated leads, and how many grids have already been scraped.

### Run a zone (full pipeline)

```bash
python pipeline.py --zone dubai
```

Runs all 4 steps in sequence. Skips any step already marked as done. Safe to re-run after interruption — it resumes from where it left off.

### Run only up to a specific step

```bash
python pipeline.py --zone dubai --only-step 2
```

Useful for checking the LLM filter results before spending RocketReach credits on step 3.

| `--only-step` value | Stops after |
|---|---|
| `1` | Google Maps scrape only |
| `2` | LLM filter (no RocketReach yet) |
| `3` | Contact enrichment (no export/backend push yet) |
| `4` | Full pipeline (same as no flag) |

### Limit scraping to N grid points

```bash
python pipeline.py --zone dubai --max-grids 3
```

Scrapes only 3 grid points this run. Run again to continue from where it stopped. Good for testing or spreading a large zone across multiple sessions.

### Reset a zone and start from scratch

```bash
python pipeline.py --zone dubai --reset
```

Clears the zone's queue file and state. Step 1 will re-scrape everything.

### Reset ALL zones

```bash
python pipeline.py --reset
```

---

## Pipeline Steps in Detail

### Step 1 — Google Maps Scrape

- Generates a lat/lng grid over the zone's bounding box using `step_km`
- Launches a Chromium browser via Playwright with **geolocation spoofed** to each grid point so Google Maps returns local results (not results biased toward the user's real IP location)
- Searches each query at each grid point via direct URL: `google.com/maps/search/{query}/@{lat},{lng},{zoom}z`
- Scrolls the results list and collects: name, address, website, phone, reviews, place type, opening hours, description
- Deduplicates at scrape time — places already in `scraped_raw.csv` are skipped, saving time and avoiding repeat RocketReach lookups downstream
- Progress is saved per zone in `Outputs/queue_<zone>.csv`

### Step 2 — LLM Filter (Groq)

- For each scraped business, fetches its website and extracts plain text (up to 2000 characters)
- Sends the business details + website content to the Groq LLM with a strict system prompt
- The LLM answers YES or NO: does this business **explicitly** serve students preparing for IB, IGCSE, A Levels, or SAT?
- Website content is treated as the **primary source of truth** — if the website doesn't mention these curricula, it's rejected
- Automatically resumes if interrupted — already-processed companies are skipped
- **Note:** Groq free tier has a 100k tokens/day limit (~200 companies per day). Use `--only-step 2` to verify results before proceeding to step 3

### Step 3 — Contact Enrichment (RocketReach)

- For each company that passed the LLM filter, searches RocketReach for decision-makers
- Fetches up to `rocketreach_max_contacts_per_level` contacts per level:
  - **Level 1 (L1):** CEO, Founder, Co-Founder, Director, Principal, President, Owner
  - **Level 2 (L2):** Head of, VP, Vice President, Manager, Dean
- Skips teaching staff (tutor, teacher, instructor, lecturer, faculty) and back-office roles (HR, Finance, IT, Accountant)
- Resumes from the last processed company if interrupted

### Step 4 — Export and Backend Sync

- Writes a styled Excel file (`Outputs/final_leads.xlsx`) with:
  - Metadata banner (zone, generated date)
  - Formatted table with column widths, row colouring by contact level, hyperlinks for email/LinkedIn/website
- Pushes all leads to the Flask backend via `POST /api/leads/bulk`
- Stamps each lead with `country` and `generated_at`

---

## Google Sheets Integration

The Google Apps Script syncs leads from the backend to a Google Sheet and enables outreach actions directly from the sheet.

### Setup (one time)

1. Open your Google Sheet
2. Go to **Extensions → Apps Script**
3. Paste the contents of `apps_script/google_apps_script.js`
4. Save, then run the `setup` function to install triggers
5. Run `authorizeAll` to grant all required permissions
6. Open your Google Sheet → **SortMyPrep menu → Sync Leads**

### Sheet columns

| Column | Description |
|--------|-------------|
| Lead ID | MongoDB document ID |
| Contact Name | Person's full name |
| Title | Job title |
| Level | L1 (decision maker) or L2 (senior) |
| Email | Work email |
| LinkedIn | Profile URL |
| Company | Company name |
| Website | Company website |
| Address | Full address |
| Country | Country (e.g. UAE) |
| Phone | Company phone |
| Avg Rating | Google Maps rating |
| Review Count | Number of Google reviews |
| Generated At | When this lead was created |
| Generate Script | Set to `Yes` to trigger AI email generation |
| Send Email | Set to `Yes` to mark as sent |
| Email Script | AI-generated outreach email (auto-filled) |
| Sent At | Timestamp when email was marked sent |

### Usage

- **Sync leads:** SortMyPrep menu → Sync Leads (pulls latest from backend into the sheet)
- **Generate email:** Set "Generate Script" to `Yes` in any row — the email script is generated and filled in within a few seconds
- **Mark as sent:** Set "Send Email" to `Yes` — logs the sent timestamp
- Any cell edit syncs back to the database automatically via an onEdit trigger

---

## Backend API

The Flask backend is deployed on Render at `https://sortmyprep-lead-automation.onrender.com`.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/leads` | Get all leads |
| POST | `/api/leads/bulk` | Insert leads in bulk (called by step 4) |
| POST | `/api/leads/clear-all` | Delete all leads from the database |
| PATCH | `/api/leads/batch-update` | Batch update fields (called by Apps Script) |
| GET | `/api/leads/<id>` | Get a single lead |
| PATCH | `/api/leads/<id>` | Update a lead's fields |
| POST | `/api/leads/<id>/generate` | Generate outreach email script via Groq |
| POST | `/api/leads/<id>/send` | Mark lead as email sent |
| POST | `/api/leads/<id>/reset` | Reset lead to unsent state |

### Running locally

```bash
cd backend
MONGO_URI="your-mongodb-uri" GROQ_API_KEY="your-key" python app.py
```

### Environment variables (set in Render dashboard)

| Variable | Description |
|----------|-------------|
| `MONGO_URI` | MongoDB Atlas connection string |
| `GROQ_API_KEY` | Groq API key for email generation |
| `GROQ_MODEL` | Model name (default: `llama-3.3-70b-versatile`) |
| `DB_NAME` | MongoDB database name |
| `DB_COLLECTION` | MongoDB collection name |
| `PORT` | Server port (default: 5000) |

---

## Adding a New Zone / Country

1. Find the bounding box coordinates (lat/lng min/max) for the target city on Google Maps
2. Add an entry to `config.json` under `"zones"`:
   ```json
   "singapore": {
     "lat_min": 1.22, "lat_max": 1.47,
     "lng_min": 103.60, "lng_max": 104.05,
     "step_km": 10,
     "location": "Singapore",
     "country": "Singapore"
   }
   ```
3. Run `python pipeline.py --list-zones` to verify it appears with the correct grid count
4. Run `python pipeline.py --zone singapore`

**Choosing `step_km`:**
- Large city (Dubai, Singapore): 10–25 km
- Small emirate (Ajman, UAQ): 5–8 km
- Smaller step = more grid points = more coverage but longer runtime and more API calls

---

## Outputs

| File | Description |
|------|-------------|
| `Outputs/scraped_raw.csv` | All scraped Google Maps listings (pre-filter) |
| `Outputs/filtered.csv` | Listings that passed the LLM relevance check |
| `Outputs/with_contacts.csv` | Filtered listings enriched with contact details |
| `Outputs/final_leads.xlsx` | Final styled Excel export ready for review |
| `Outputs/pipeline_state.json` | Tracks which steps are done per zone |
| `Outputs/queue_<zone>.csv` | Tracks which grid points have been scraped per zone |

All files in `Outputs/` are gitignored.

---

## Tips and Gotchas

**Groq daily token limit:** The free tier allows ~100k tokens/day (~200 companies). If step 2 hits the limit mid-run, it auto-keeps unverified rows to avoid data loss and marks step 2 as done. Use a second Groq account's API key and re-run `--only-step 2` to process the remainder.

**RocketReach credits:** Credits are consumed in step 3. Always run `--only-step 2` first and review `Outputs/filtered.csv` before running the full pipeline — you want to be sure the LLM filter quality is good before spending credits.

**Resuming after interruption:** Every step is idempotent. Re-running `pipeline.py --zone <zone>` safely skips completed steps and resumes from the last checkpoint.

**Duplicate results across grid points:** The scraper deduplicates at collection time using place names extracted from Google Maps URLs. A place seen at one grid point is skipped at all subsequent grid points, saving RocketReach credits.

**Google Maps location bias:** The browser's geolocation is spoofed to each grid point's coordinates AND the city name is appended to each search query (e.g. "IB coaching in Dubai"). Both are needed — geolocation alone is not enough to override IP-based location bias on Playwright.
