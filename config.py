"""
Global configuration for the tender intelligence system.

Pipeline role:
Centralizes environment-dependent variables and static thresholds. 
Used across scrapers (portals), matching logic (thresholds), and the 
scheduler (timing).

Key responsibilities:
- Managing credential retrieval from environment variables.
- Defining the business logic for 'relevance' via MATCH_THRESHOLD.
- Configuring the execution window for the background scheduler.

Notes:
- Relies on a .env file for sensitive information like SMTP credentials.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Email
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Official-document enrichment is disabled unless both reviewed host names
# and a protected persistent directory are explicitly configured.
DOCUMENT_ALLOWED_HOSTS = frozenset(
    host.strip().lower().rstrip(".")
    for host in os.getenv("TENDERMATCH_DOCUMENT_HOSTS", "").split(",")
    if host.strip()
)
DOCUMENT_STORAGE_DIR = os.getenv("TENDERMATCH_DOCUMENT_DIR")

# Matching
MATCH_THRESHOLD = 0.65

# Scheduler
SEND_TIME_HOUR = 21    
SEND_TIME_MINUTE = 0

# Blocklist
BLOCKLIST_KEYWORDS = [
    "road", "civil", "construction", "furniture",
    "food", "catering", "sanitation", "vehicle",
    "parking", "horticulture", "housekeeping"
]
