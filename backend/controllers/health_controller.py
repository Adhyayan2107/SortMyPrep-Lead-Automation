from flask import Blueprint, jsonify


def create_health_blueprint() -> Blueprint:
    bp = Blueprint("health", __name__)

    @bp.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return bp
