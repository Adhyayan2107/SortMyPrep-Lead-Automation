from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Lead:
    """Represents a scraped lead with contact and company information."""
    contact_name:          str  = ""
    contact_title:         str  = ""
    contact_level:         str  = ""
    email:                 str  = ""
    linkedin:              str  = ""
    company:               str  = ""
    company_website:       str  = ""
    company_address:       str  = ""
    country:               str  = ""
    zone_name:             str  = ""
    company_phone:         str  = ""
    company_reviews_avg:   str  = ""
    company_reviews_count: str  = ""
    generated_at:          str  = ""
    generate_script:       str  = "No"
    send_email:            str  = "No"
    email_script:          Optional[str] = None
    email_sent:            bool = False
    sent_at:               Optional[str] = None
    created_at:            str  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Fields that Apps Script is allowed to update via PATCH
    EDITABLE_FIELDS: frozenset = field(default_factory=lambda: frozenset({
        "contact_name", "contact_title", "contact_level",
        "email", "linkedin", "company", "company_website",
        "company_address", "company_phone", "company_reviews_avg",
        "company_reviews_count", "generate_script", "send_email",
        "email_script", "sent_at",
    }), repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "contact_name":          self.contact_name,
            "contact_title":         self.contact_title,
            "contact_level":         self.contact_level,
            "email":                 self.email,
            "linkedin":              self.linkedin,
            "company":               self.company,
            "company_website":       self.company_website,
            "company_address":       self.company_address,
            "country":               self.country,
            "zone_name":             self.zone_name,
            "company_phone":         self.company_phone,
            "company_reviews_avg":   self.company_reviews_avg,
            "company_reviews_count": self.company_reviews_count,
            "generated_at":          self.generated_at,
            "generate_script":       self.generate_script,
            "send_email":            self.send_email,
            "email_script":          self.email_script,
            "email_sent":            self.email_sent,
            "sent_at":               self.sent_at,
            "created_at":            self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        data = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**data)
