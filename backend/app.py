from flask import Flask
from flask_cors import CORS
from pymongo import MongoClient, ASCENDING

from config import Config
from repositories.lead_repository import LeadRepository
from services.email_service import EmailService
from services.lead_service import LeadService
from controllers.health_controller import create_health_blueprint
from controllers.lead_controller import create_lead_blueprint


def create_app(config: Config | None = None) -> Flask:
    """
    App factory — builds and wires all dependencies top-down.
    Nothing below this function knows about anything above it.

    Dependency flow:
        Config
          └── MongoClient → Collection → LeadRepository ──┐
          └── Groq API key → EmailService                  ├─► LeadService → LeadController
                                                           └─┘
    """
    if config is None:
        config = Config()

    app = Flask(__name__)
    CORS(app)

    # ── Database ──────────────────────────────────────────────────────────────
    client     = MongoClient(config.MONGO_URI)
    collection = client[config.DB_NAME][config.DB_COLLECTION]
    collection.create_index(
        [("contact_name", ASCENDING), ("company", ASCENDING)],
        unique=True,
        name="unique_contact_company",
    )

    # ── Dependency injection ──────────────────────────────────────────────────
    repo      = LeadRepository(collection)
    email_svc = EmailService(config.GROQ_API_KEY, config.GROQ_MODEL)
    lead_svc  = LeadService(repo, email_svc)

    # ── Register blueprints ───────────────────────────────────────────────────
    app.register_blueprint(create_health_blueprint())
    app.register_blueprint(create_lead_blueprint(lead_svc))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
