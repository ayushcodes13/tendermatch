import os
from dotenv import load_dotenv

load_dotenv()

# Email
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

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