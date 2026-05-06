from groq import Groq

_SAMPLE_EMAILS = """
=== EMAIL 1 (Initial Outreach) ===
Subject: Partnership Opportunity | AI-powered exam prep workflow to improve student outcomes

Hi [Name],

I hope this email finds you well.
I'm Ananya, the co-founder of sortmyprep. sortmyprep is a Google and Open-AI backed adaptive
AI-exam prep platform that provides students & teachers with unlimited, adaptive questions with
step-by-step solutions for the IB & Cambridge curricula.

We currently work with 2,000+ students from across the world from schools like Tanglin Trust
School, One World International School, and Raffles International School. We have currently
partnered with tutoring academies in Singapore, UAE, India, and Belgium, and are looking to
strengthen our partnerships in Singapore, Hong Kong, Vietnam, and Thailand.

Here's what we provide to centres:
1. Unlimited, personalised practice, generated on demand.
2. AI grading that thinks like a board-certified examiner.
3. A teacher portal that runs your operations.

Here's a demo: https://drive.google.com/drive/folders/1MaRL1F6G4_ZnF9vaYlpn_VG1AYoTc3b_

If this sounds interesting to you, could we get on a call sometime this week?

Thanks,
Ananya

=== EMAIL 2 (Follow-up 1) ===
Subject: Following up | sortmyprep x [Company]

Hi [Name],

We are currently working with tutoring academies in India, Singapore, UAE & Belgium that cater
to over 2,000 students from schools like Tanglin Trust School, Singapore; GEMS School, Dubai;
International School of Brussels, Belgium.

Demo link: https://drive.google.com/drive/folders/1MaRL1F6G4_ZnF9vaYlpn_VG1AYoTc3b_

We're currently strengthening our partnerships in the UAE. I would love to speak with you.
Does sometime next week work?

Ananya

=== EMAIL 3 (Follow-up 2 — Social Proof) ===
Subject: What schools are saying about sortmyprep

Hi [Name],

In the last 10 days, we have onboarded 5 centres and 1,000 students across Malaysia, USA, UK,
and Hong Kong.

Student: "I love how the platform tracks my performance." — Arjun, Tanglin Trust School
Teacher: "Having access to questions saves me over 2 hours/day." — Shikha, Belgium Int'l School

Does sometime next week work to connect?

Ananya

=== EMAIL 4 (Final Follow-up) ===
Subject: Last note from sortmyprep

Hi [Name],

I know I've followed up a few times, so this is the last time I'll be reaching out.

We're expanding across Singapore, Hong Kong, Vietnam, and Thailand, and would love to work
together. If interested, reach me at ananya@sortmyprep.com

Wishing you and your team all the best!

Ananya
"""

_SYSTEM_PROMPT = (
    "You are writing outreach emails on behalf of Ananya, co-founder of sortmyprep — "
    "a Google and OpenAI-backed AI exam prep platform for IB & Cambridge students. "
    "Personalise the given template for a specific lead. Rules: address by first name only, "
    "keep the subject line exactly as given, adjust regional references to match the lead's "
    "location, keep tone warm and professional, sign off as Ananya. "
    "Return ONLY the email — subject line first, blank line, then body. No extra commentary."
)

_EMAIL_LABELS = {1: "EMAIL 1", 2: "EMAIL 2", 3: "EMAIL 3", 4: "EMAIL 4"}


class EmailService:
    """Generates personalised outreach emails using the Groq LLM API."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        self._client = Groq(api_key=api_key)
        self._model  = model

    def generate(self, lead: dict, email_number: int = 1) -> str:
        first_name = self._first_name(lead.get("contact_name", ""))
        label      = _EMAIL_LABELS.get(email_number, "EMAIL 1")

        prompt = (
            f"Here are our 4 outreach email templates:\n\n{_SAMPLE_EMAILS}\n\n"
            f"Now personalise {label} for this lead:\n"
            f"- First name: {first_name}\n"
            f"- Title: {lead.get('contact_title', '')}\n"
            f"- Company: {lead.get('company', '')}\n"
            f"- Location: {lead.get('company_address', '')}\n\n"
            "Return only the personalised email (Subject line, blank line, then body)."
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1200,
        )
        return response.choices[0].message.content.strip()

    @staticmethod
    def _first_name(full_name: str) -> str:
        parts = (full_name or "").strip().split()
        return parts[0] if parts else "there"
