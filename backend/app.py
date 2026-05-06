import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS

from email_gen import generate_email_script

app = Flask(__name__)
CORS(app)

DB_PATH = os.environ.get("DB_PATH", "leads.db")


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_name         TEXT,
            contact_title        TEXT,
            contact_level        TEXT,
            email                TEXT,
            linkedin             TEXT,
            company              TEXT,
            company_website      TEXT,
            company_address      TEXT,
            company_phone        TEXT,
            company_reviews_avg  TEXT,
            company_reviews_count TEXT,
            generate_script      TEXT    DEFAULT 'No',
            send_email           TEXT    DEFAULT 'No',
            email_script         TEXT,
            email_sent           INTEGER DEFAULT 0,
            sent_at              TEXT,
            created_at           TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/leads/bulk", methods=["POST"])
def bulk_insert():
    """Receives a list of leads from the pipeline and inserts new ones."""
    leads = request.json.get("leads", [])
    conn  = get_db()
    inserted = 0
    for lead in leads:
        existing = conn.execute(
            "SELECT id FROM leads WHERE contact_name = ? AND company = ?",
            (lead.get("contact_name"), lead.get("company")),
        ).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO leads
                    (contact_name, contact_title, contact_level, email, linkedin,
                     company, company_website, company_address, company_phone,
                     company_reviews_avg, company_reviews_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead.get("contact_name"),   lead.get("contact_title"),
                lead.get("contact_level"),  lead.get("email"),
                lead.get("linkedin"),       lead.get("company"),
                lead.get("company_website"),lead.get("company_address"),
                lead.get("company_phone"),  lead.get("company_reviews_avg"),
                lead.get("company_reviews_count"),
            ))
            inserted += 1
    conn.commit()
    conn.close()
    return jsonify({"inserted": inserted, "skipped": len(leads) - inserted})


@app.route("/api/leads", methods=["GET"])
def get_leads():
    """Returns all leads ordered by company then level."""
    conn  = get_db()
    rows  = conn.execute(
        "SELECT * FROM leads ORDER BY company, contact_level"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/leads/<int:lead_id>", methods=["GET"])
def get_lead(lead_id):
    conn = get_db()
    row  = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/leads/<int:lead_id>/generate", methods=["POST"])
def generate(lead_id):
    """Generates a personalised email script for the lead and stores it."""
    conn = get_db()
    row  = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    lead         = dict(row)
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    email_number = request.json.get("email_number", 1) if request.is_json else 1

    try:
        script = generate_email_script(groq_api_key, lead, email_number)
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

    conn.execute(
        "UPDATE leads SET email_script = ?, generate_script = 'Yes' WHERE id = ?",
        (script, lead_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"script": script})


@app.route("/api/leads/<int:lead_id>/send", methods=["POST"])
def mark_sent(lead_id):
    """Marks a lead as emailed (actual send happens in Apps Script via Gmail)."""
    conn = get_db()
    conn.execute(
        "UPDATE leads SET send_email = 'Yes', email_sent = 1, sent_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), lead_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/leads/<int:lead_id>/reset", methods=["POST"])
def reset_lead(lead_id):
    """Resets generate/send flags so a lead can be re-processed."""
    conn = get_db()
    conn.execute("""
        UPDATE leads
        SET generate_script = 'No', send_email = 'No',
            email_script = NULL, email_sent = 0, sent_at = NULL
        WHERE id = ?
    """, (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
