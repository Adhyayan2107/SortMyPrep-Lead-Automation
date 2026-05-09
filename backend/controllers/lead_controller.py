from flask import Blueprint, jsonify, request

from services.lead_service import LeadService


def create_lead_blueprint(lead_service: LeadService) -> Blueprint:
    """
    Blueprint factory — receives LeadService via injection so controllers
    never instantiate their own dependencies (Dependency Inversion).
    """
    bp = Blueprint("leads", __name__, url_prefix="/api/leads")

    # ── Collection endpoints ──────────────────────────────────────────────────

    @bp.route("", methods=["GET"])
    def get_all():
        return jsonify(lead_service.get_all())

    @bp.route("/clear-all", methods=["POST"])
    def clear_all():
        return jsonify(lead_service.clear_all())

    @bp.route("/bulk", methods=["POST"])
    def bulk_insert():
        leads = (request.json or {}).get("leads", [])
        return jsonify(lead_service.bulk_insert(leads))

    @bp.route("/batch-update", methods=["PATCH"])
    def batch_update():
        updates = (request.json or {}).get("updates", [])
        return jsonify(lead_service.batch_update(updates))

    # ── Single lead endpoints ─────────────────────────────────────────────────

    @bp.route("/<lead_id>", methods=["GET"])
    def get_one(lead_id):
        lead = lead_service.get_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404
        return jsonify(lead)

    @bp.route("/<lead_id>", methods=["PATCH"])
    def update(lead_id):
        result = lead_service.update(lead_id, request.json or {})
        status = 400 if "error" in result else 200
        return jsonify(result), status

    @bp.route("/<lead_id>/generate", methods=["POST"])
    def generate(lead_id):
        email_number = (request.json or {}).get("email_number", 1)
        result = lead_service.generate_script(lead_id, email_number)
        status = 404 if "error" in result else 200
        return jsonify(result), status

    @bp.route("/<lead_id>/send", methods=["POST"])
    def mark_sent(lead_id):
        result = lead_service.mark_sent(lead_id)
        status = 404 if "error" in result else 200
        return jsonify(result), status

    @bp.route("/<lead_id>/reset", methods=["POST"])
    def reset(lead_id):
        result = lead_service.reset(lead_id)
        status = 404 if "error" in result else 200
        return jsonify(result), status

    return bp
