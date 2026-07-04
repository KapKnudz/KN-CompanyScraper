import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

COMPANIES_TO_TRACK = [
    "norsk-titanium",
    "volvo-cars",
    "ericsson",
]

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))