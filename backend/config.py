import os


class Config:
    MONGO_URI:     str = os.environ.get("MONGO_URI", "")
    GROQ_API_KEY:  str = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL:    str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    PORT:          int = int(os.environ.get("PORT", 5000))
    DB_NAME:       str = "leads"
    DB_COLLECTION: str = "leads"
