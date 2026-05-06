import os
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError

from email_gen import generate_email_script

app = Flask(__name__)
CORS(app)

# ── MongoDB connection ─────────────────────────────────────────────────────────

MONGO_URI = os.environ.get("MONGO_URI", "")
_client   = MongoClient(MONGO_URI)
_db       = _client.get_default_database()
leads_col = _db["leads"]

# Unique compound index so duplicate scrape runs don't create duplicate leads
leads_col.create_index(
    [("contact_name", ASCENDING), ("company", ASCENDING)],
    unique=True,
    name="unique_contact_company",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def to_dict(doc):
    """Convert a MongoDB document to a JSON-serialisable dict."""
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def parse_oid(lead_id: str):
    """Return ObjectId or raise 400."""
    try:
        return ObjectId(lead_id)
    except InvalidId:
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/leads/bulk", methods=["POST"])
def bulk_insert():
    """Receive a list of leads from the pipeline and insert new ones."""
    leads    = request.json.get("leads", [])
    inserted = 0
    for lead in leads:
        lead.pop("id", None)          # strip any leftover id field
        lead["generate_script"] = "No"
        lead["send_email"]      = "No"
        lead["email_script"]    = None
        lead["email_sent"]      = False
        lead["sent_at"]         = None
        lead["created_at"]      = datetime.now(timezone.utc).isoformat()
        try:
            leads_col.insert_one(lead)
            inserted += 1
        except DuplicateKeyError:
            pass   # already exists — skip silently
    return jsonify({"inserted": inserted, "skipped": len(leads) - inserted})


@app.route("/api/leads", methods=["GET"])
def get_leads():
    """Return all leads ordered by company then level."""
    docs = leads_col.find({}, sort=[("company", ASCENDING), ("contact_level", ASCENDING)])
    return jsonify([to_dict(d) for d in docs])


@app.route("/api/leads/<lead_id>", methods=["GET"])
def get_lead(lead_id):
    oid = parse_oid(lead_id)
    if not oid:
        return jsonify({"error": "Invalid ID"}), 400
    doc = leads_col.find_one({"_id": oid})
    if not doc:
        return jsonify({"error": "Not found"}), 404
    return jsonify(to_dict(doc))


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def update_lead(lead_id):
    """Partial update for a single lead (used by Apps Script cell edits)."""
    oid = parse_oid(lead_id)
    if not oid:
        return jsonify({"error": "Invalid ID"}), 400

    ALLOWED = {
        "contact_name", "contact_title", "contact_level",
        "email", "linkedin", "company", "company_website",
        "company_address", "company_phone", "company_reviews_avg",
        "company_reviews_count", "generate_script", "send_email",
        "email_script", "sent_at",
    }
    updates = {k: v for k, v in (request.json or {}).items() if k in ALLOWED}
    if not updates:
        return jsonify({"error": "No valid fields"}), 400

    leads_col.update_one({"_id": oid}, {"$set": updates})
    return jsonify({"success": True})


@app.route("/api/leads/batch-update", methods=["PATCH"])
def batch_update():
    """
    Batch update from Apps Script flush.
    Body: { "updates": [ {id, field, value}, ... ] }
    Groups by id so we make one DB write per lead.
    """
    raw = request.json.get("updates", [])

    ALLOWED = {
        "contact_name", "contact_title", "contact_level",
        "email", "linkedin", "company", "company_website",
        "company_address", "company_phone", "company_reviews_avg",
        "company_reviews_count", "generate_script", "send_email",
        "email_script", "sent_at",
    }

    # Group by lead id (last-write-wins per field)
    by_id: dict = {}
    for item in raw:
        lid   = item.get("id")
        field = item.get("field")
        value = item.get("value")
        if lid and field in ALLOWED:
            by_id.setdefault(lid, {})[field] = value

    updated = 0
    for lid, fields in by_id.items():
        oid = parse_oid(lid)
        if oid:
            leads_col.update_one({"_id": oid}, {"$set": fields})
            updated += 1

    return jsonify({"updated": updated})


@app.route("/api/leads/<lead_id>/generate", methods=["POST"])
def generate(lead_id):
    """Generate a personalised email script via Groq and store it."""
    oid = parse_oid(lead_id)
    if not oid:
        return jsonify({"error": "Invalid ID"}), 400

    doc = leads_col.find_one({"_id": oid})
    if not doc:
        return jsonify({"error": "Not found"}), 404

    email_number = (request.json or {}).get("email_number", 1)
    try:
        script = generate_email_script(
            os.environ.get("GROQ_API_KEY", ""), dict(doc), email_number
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    leads_col.update_one(
        {"_id": oid},
        {"$set": {"email_script": script, "generate_script": "Yes"}},
    )
    return jsonify({"script": script})


@app.route("/api/leads/<lead_id>/send", methods=["POST"])
def mark_sent(lead_id):
    """Mark a lead as emailed (actual send happens in Apps Script via Gmail)."""
    oid = parse_oid(lead_id)
    if not oid:
        return jsonify({"error": "Invalid ID"}), 400

    leads_col.update_one(
        {"_id": oid},
        {"$set": {
            "send_email": "Yes",
            "email_sent": True,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return jsonify({"success": True})


@app.route("/api/leads/<lead_id>/reset", methods=["POST"])
def reset_lead(lead_id):
    """Reset generate/send flags so a lead can be re-processed."""
    oid = parse_oid(lead_id)
    if not oid:
        return jsonify({"error": "Invalid ID"}), 400

    leads_col.update_one(
        {"_id": oid},
        {"$set": {
            "generate_script": "No",
            "send_email":      "No",
            "email_script":    None,
            "email_sent":      False,
            "sent_at":         None,
        }},
    )
    return jsonify({"success": True})


# ── Boot ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
