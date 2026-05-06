from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError


class LeadRepository:
    """
    Owns all MongoDB interactions for the leads collection.
    No business logic lives here — only data access.
    """

    def __init__(self, collection: Collection) -> None:
        self._col = collection

    # ── Write ─────────────────────────────────────────────────────────────────

    def insert(self, document: dict) -> bool:
        """Insert one lead. Returns False if it already exists."""
        try:
            self._col.insert_one(document)
            return True
        except DuplicateKeyError:
            return False

    def update(self, lead_id: str, fields: dict) -> bool:
        """Partial update by ID. Returns False if ID is invalid or not found."""
        oid = self._to_object_id(lead_id)
        if not oid:
            return False
        result = self._col.update_one({"_id": oid}, {"$set": fields})
        return result.matched_count > 0

    def batch_update(self, updates_by_id: dict[str, dict]) -> int:
        """
        Apply multiple partial updates grouped by lead ID.
        Returns the number of leads successfully updated.
        """
        updated = 0
        for lead_id, fields in updates_by_id.items():
            if self.update(lead_id, fields):
                updated += 1
        return updated

    # ── Read ──────────────────────────────────────────────────────────────────

    def find_all(self) -> list[dict]:
        """Return all leads ordered by company, then contact level."""
        return list(
            self._col.find({}, sort=[("company", 1), ("contact_level", 1)])
        )

    def find_by_id(self, lead_id: str) -> Optional[dict]:
        """Return one lead by ID, or None if not found."""
        oid = self._to_object_id(lead_id)
        if not oid:
            return None
        return self._col.find_one({"_id": oid})

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_object_id(lead_id: str) -> Optional[ObjectId]:
        try:
            return ObjectId(str(lead_id))
        except (InvalidId, TypeError):
            return None

    @staticmethod
    def serialize(document: dict) -> dict:
        """Convert a MongoDB document to a JSON-safe dict (ObjectId → string id)."""
        doc = dict(document)
        doc["id"] = str(doc.pop("_id"))
        return doc
