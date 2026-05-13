import os

from dotenv import load_dotenv

load_dotenv()

QUICKBOOKS_BASE_URL: str = os.getenv("QUICKBOOKS_BASE_URL", "http://localhost:4000")
WORKER_POLL_INTERVAL: int = int(os.getenv("WORKER_POLL_INTERVAL", "15"))
