from groq import Groq

SAMPLE_EMAILS = """
=== EMAIL 1 (Initial Outreach) ===
Subject: Partnership Opportunity | AI-powered exam prep workflow to improve student outcomes

Hi [Name],

I hope this email finds you well.
I'm Ananya, the co-founder of sortmyprep. sortmyprep is a Google and Open-AI backed adaptive AI-exam prep platform that provides students & teachers with unlimited, adaptive questions with step-by-step solutions for the IB & Cambridge curricula.

We currently work with 2,000+ students from across the world from schools like Tanglin Trust School, One World International School, and Raffles International School. We have currently partnered with tutoring academies in Singapore, UAE, India, and Belgium, and are looking to strengthen our partnerships in Singapore, Hong Kong, Vietnam, and Thailand.

Here's what we provide to centres:
1. Unlimited, personalised practice, generated on demand: Every student gets fresh, adaptive questions tailored to their weak topics and target grade. It's not a fixed bank that all tutors across Singapore share, but a resource bank no other centre in Singapore has access to. We maintain 100% content accuracy through our expert-in-the-loop model, by working with 100+ Cambridge & IB examiners that validate our content.
2. AI grading that thinks like a board-certified examiner: Our AI is trained specifically on 700,000+ Cambridge and IBDP marking schemes. It scores student work and provides examiner-level feedback automatically to teachers, students, and parents - so your tutors teach, not mark.
3. A teacher portal that runs your operations: Tutors use sortmyprep to assign tailored problem sets, track every student's performance in real time, and integrate with existing resources. All the admin that eats your tutors' time disappears. What's left is teaching.

What this means practically: your tutors spend their time teaching, not building worksheets or marking papers. Your students get more practice, better feedback, and faster improvement. And your centre gets a measurable, defensible edge in the competitive tutoring market — especially through white-labelling, where sortmyprep becomes your platform.

Here's a demo of how our student and teacher's portal work: https://drive.google.com/drive/folders/1MaRL1F6G4_ZnF9vaYlpn_VG1AYoTc3b_

If this sounds interesting to you, could we get on a call sometime this week to discuss how we can take this forward?

Thanks,
Ananya

=== EMAIL 2 (Follow-up 1) ===
Subject: Following up | sortmyprep x [Company]

Hi [Name],

We are currently working with tutoring academies in India, Singapore, UAE & Belgium that cater to over 2,000 students from schools like Tanglin Trust School, Singapore; One World International School, Singapore; Dhirubai Ambani International School, Mumbai; GEMS School, Dubai; International School of Brussels, Belgium.

Here's what we provide to students & teachers:

We provide unlimited, personalised practice generated on demand. Unlike competitors, our knowledge bank of questions is not limited to a set number of questions that all academies in your region will have access to, but a unique set of questions that gives you an academic edge over other competing centres.
An AI grader that provides instant, examiner-feedback to students & parents to ensure immediate, expert-level examiner feedback.
A teacher portal that allows you to generate and assign tailored problem sets, track every student's performance in real time, and integrate with existing resources.

Attaching the demo link once again for your reference: https://drive.google.com/drive/folders/1MaRL1F6G4_ZnF9vaYlpn_VG1AYoTc3b_

We're currently strengthening our partnerships in the UAE. I would love to speak with you and explore how we can work together. Does sometime next week work for you?

Ananya

=== EMAIL 3 (Follow-up 2 — Social Proof) ===
Subject: What schools are saying about sortmyprep

Hi [Name],

In the last 10 days, we have onboarded 5 centres and 1,000 students across Malaysia, USA, UK, and Hong Kong.

Here's what students from the top global schools have to say about us:
"I love how the platform tracks my performance as I solve past papers. It's giving me a clear, structured way of studying."
Arjun, Tanglin Trust School, Singapore

Here's what teachers are particularly enjoying about sortmyprep:
"Having access to questions that I can directly assign to students saves me over 2 hours / day. Students scores are improving simply because everyone's time is being used more productively"
Shikha, Belgium International School, Belgium

I would love to connect and discuss how we can work together. Does sometime next week work?

Ananya

=== EMAIL 4 (Final Follow-up) ===
Subject: Last note from sortmyprep

Hi [Name],

I know I've followed up a few times, so this is the last time I'll be reaching out.

We're expanding our footprint across Singapore, Hong Kong, Vietnam, and Thailand, and we would love to work together to improve student outcomes.

If this partnership is something that seems interesting to you, you can always reach me at ananya@sortmyprep.com

I wish you and your team good luck!

Ananya
"""

SYSTEM_PROMPT = """You are writing outreach emails on behalf of Ananya, co-founder of sortmyprep — a Google and OpenAI-backed AI exam prep platform for IB & Cambridge students.

Your job is to personalise the given email template for a specific lead. Rules:
- Address them by first name only
- Keep the subject line exactly as provided
- Keep the core content and value propositions intact
- Adjust any regional references to match the lead's location (e.g. if they're in UAE/Sharjah, mention UAE context)
- Keep the tone warm, professional, and concise
- Sign off as Ananya
- Return ONLY the email — subject line first, then a blank line, then the body. No extra commentary."""


def generate_email_script(api_key: str, lead: dict, email_number: int = 1) -> str:
    client = Groq(api_key=api_key)

    first_name = (lead.get("contact_name") or "").split()[0] if lead.get("contact_name") else "there"
    location = lead.get("company_address") or ""
    company  = lead.get("company") or ""
    title    = lead.get("contact_title") or ""

    email_labels = {1: "EMAIL 1", 2: "EMAIL 2", 3: "EMAIL 3", 4: "EMAIL 4"}
    label = email_labels.get(email_number, "EMAIL 1")

    prompt = f"""Here are our 4 outreach email templates:

{SAMPLE_EMAILS}

Now personalise {label} for this lead:
- First name: {first_name}
- Title: {title}
- Company: {company}
- Location: {location}

Return only the personalised email (Subject line, blank line, then body)."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.7,
        max_tokens=1200,
    )
    return response.choices[0].message.content.strip()
