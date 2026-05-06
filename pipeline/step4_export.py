"""
Step 4: Clean up and export the final lead list.
Outputs an Excel file — one row per lead, styled header, auto-width columns.
"""

import logging
from pathlib import Path

import pandas as pd
import requests
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_OUTPUTS    = Path(__file__).parent.parent / "Outputs"
INPUT_PATH  = _OUTPUTS / "with_contacts.csv"
OUTPUT_PATH = _OUTPUTS / "final_leads.xlsx"

COLUMN_ORDER = [
    "contact_name", "contact_title", "contact_level",
    "email", "linkedin",
    "company", "company_website", "company_address",
    "company_phone", "company_reviews_avg", "company_reviews_count",
]

COLUMN_LABELS = {
    "contact_name":          "Contact Name",
    "contact_title":         "Title",
    "contact_level":         "Level",
    "email":                 "Email",
    "linkedin":              "LinkedIn",
    "company":               "Company",
    "company_website":       "Website",
    "company_address":       "Address",
    "company_phone":         "Phone",
    "company_reviews_avg":   "Avg Rating",
    "company_reviews_count": "Review Count",
}

LEVEL_SORT   = {"level1": 0, "level2": 1}
HEADER_COLOR = "1F4E79"   # dark blue
LEVEL1_COLOR = "D6E4F0"   # light blue  — Level 1 rows
LEVEL2_COLOR = "FFFFFF"   # white       — Level 2 rows


def _col_width(series, header):
    max_data = series.astype(str).str.len().max() if len(series) else 0
    return min(max(max_data, len(header)) + 4, 60)


def run(config):
    df = pd.read_csv(INPUT_PATH)

    # Drop placeholder rows (no contact found)
    df = df[df["contact_name"].notna() & (df["contact_name"].astype(str).str.strip() != "")].copy()

    # Keep only known columns in order
    cols = [c for c in COLUMN_ORDER if c in df.columns]
    df = df[cols].copy()

    # Sort: company name A→Z, then Level 1 before Level 2
    df["_sort"] = df["contact_level"].map(LEVEL_SORT).fillna(2)
    df = df.sort_values(["company", "_sort"]).drop(columns=["_sort"])
    df = df.reset_index(drop=True)

    # ── Write Excel ──────────────────────────────────────────────────
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.rename(columns=COLUMN_LABELS).to_excel(writer, index=False, sheet_name="Leads")

        ws = writer.sheets["Leads"]

        # Header row styling
        header_font  = Font(bold=True, color="FFFFFF", size=11)
        header_fill  = PatternFill("solid", fgColor=HEADER_COLOR)
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=False)
        thin_border  = Border(
            bottom=Side(style="thin", color="BBBBBB"),
            right=Side(style="thin", color="BBBBBB"),
        )

        for cell in ws[1]:
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = header_align
            cell.border    = thin_border

        ws.row_dimensions[1].height = 22

        # Data row styling — alternate shading by level
        l1_fill = PatternFill("solid", fgColor=LEVEL1_COLOR)
        l2_fill = PatternFill("solid", fgColor=LEVEL2_COLOR)
        data_align = Alignment(vertical="center", wrap_text=False)

        level_col_idx = cols.index("contact_level") + 1  # 1-based

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
            level_val = ws.cell(row=row_idx, column=level_col_idx).value or ""
            fill = l1_fill if level_val == "level1" else l2_fill
            for cell in row:
                cell.fill      = fill
                cell.alignment = data_align
                cell.border    = thin_border
            ws.row_dimensions[row_idx].height = 18

        # Auto-width columns
        for col_idx, col_key in enumerate(cols, start=1):
            label  = COLUMN_LABELS.get(col_key, col_key)
            width  = _col_width(df[col_key], label)
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        # Freeze header row
        ws.freeze_panes = "A2"

    logging.info(f"Step 4 complete. {len(df)} leads exported → {OUTPUT_PATH}")

    # Push leads to backend if configured
    backend_url = config.get("backend_url", "").strip()
    if backend_url:
        _push_to_backend(df, backend_url)


def _push_to_backend(df: pd.DataFrame, backend_url: str):
    # Use pandas JSON serialiser — it converts NaN → null correctly
    import json
    leads = json.loads(df.to_json(orient="records"))
    try:
        resp = requests.post(
            f"{backend_url.rstrip('/')}/api/leads/bulk",
            json={"leads": leads},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        logging.info(f"Backend sync: {result.get('inserted', 0)} new, {result.get('skipped', 0)} already existed")
    except Exception as e:
        logging.warning(f"Backend sync failed (leads still saved locally): {e}")
