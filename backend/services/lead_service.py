from datetime import datetime, timezone
from typing import Optional

from models.lead import Lead
from repositories.lead_repository import LeadRepository
from services.email_service import EmailService


class LeadService:
    """
    Orchestrates all lead-related business logic.
    Depends on LeadRepository (data) and EmailService (generation) via injection —
    neither is imported or instantiated here.
    """

    def __init__(self, repo: LeadRepository, email_svc: EmailService) -> None:
        self._repo      = repo
        self._email_svc = email_svc

    # ── Bulk insert (from pipeline) ───────────────────────────────────────────

    def bulk_insert(self, raw_leads: list[dict]) -> dict:
        docs = []
        for raw in raw_leads:
            raw.pop("id", None)
            docs.append(Lead.from_dict(raw).to_dict())
        inserted, skipped = self._repo.insert_many(docs)
        return {"inserted": inserted, "skipped": skipped}

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        return [LeadRepository.serialize(d) for d in self._repo.find_all()]

    def get_by_id(self, lead_id: str) -> Optional[dict]:
        doc = self._repo.find_by_id(lead_id)
        return LeadRepository.serialize(doc) if doc else None

    # ── Cell-edit sync ────────────────────────────────────────────────────────

    def update(self, lead_id: str, data: dict) -> dict:
        """Single lead partial update. Filters to editable fields only."""
        allowed = Lead("").EDITABLE_FIELDS
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return {"error": "No valid fields provided"}
        ok = self._repo.update(lead_id, updates)
        return {"success": True} if ok else {"error": "Lead not found"}

    def batch_update(self, raw_updates: list[dict]) -> dict:
        """
        Batch sync from Apps Script — groups changes by lead ID so we make
        one DB write per lead (last-write-wins per field).
        """
        allowed  = Lead("").EDITABLE_FIELDS
        by_id: dict[str, dict] = {}
        for item in raw_updates:
            lid   = item.get("id")
            field = item.get("field")
            value = item.get("value")
            if lid and field in allowed:
                by_id.setdefault(str(lid), {})[field] = value

        count = self._repo.batch_update(by_id)
        return {"updated": count}

    # ── Email generation ──────────────────────────────────────────────────────

    def generate_script(self, lead_id: str, email_number: int = 1) -> dict:
        doc = self._repo.find_by_id(lead_id)
        if not doc:
            return {"error": "Lead not found"}
        script = self._email_svc.generate(dict(doc), email_number)
        self._repo.update(lead_id, {"email_script": script, "generate_script": "Yes"})
        return {"script": script}

    # ── Email send tracking ───────────────────────────────────────────────────

    def mark_sent(self, lead_id: str) -> dict:
        ok = self._repo.update(lead_id, {
            "send_email": "Yes",
            "email_sent": True,
            "sent_at":    datetime.now(timezone.utc).isoformat(),
        })
        return {"success": True} if ok else {"error": "Lead not found"}

    def reset(self, lead_id: str) -> dict:
        ok = self._repo.update(lead_id, {
            "generate_script": "No",
            "send_email":      "No",
            "email_script":    None,
            "email_sent":      False,
            "sent_at":         None,
        })
        return {"success": True} if ok else {"error": "Lead not found"}
